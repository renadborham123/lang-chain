"""Nodes for the CV-to-jobs LangGraph workflow."""

from __future__ import annotations

import json
import re
from typing import Any

import requests
from langchain_core.prompts import ChatPromptTemplate

from config import settings
from memory_store import memory
from model_provider import invoke_prompt
from scrape_jobs import scrape_jobs_for_queries, stable_job_id
from state import CVProfile, JobPosting, JobSearchState, MatchedJob


PROFILE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Extract a factual candidate profile from this CV. Return JSON only with keys: full_name, email, phone, links, "
            "job_titles, seniority, primary_skills, domains, years_experience, preferred_location, is_student, "
            "education_level, graduation_year, opportunity_types. Arrays: links, job_titles, primary_skills, domains, "
            "opportunity_types. opportunity_types can contain internship, graduate, part_time, or full_time. "
            "Treat a current university or college learner as a student even if they have projects or internships. "
            "Do not infer a completed degree or paid experience that is not stated.",
        ),
        ("human", "CV:\n{cv_text}"),
    ]
)

QUERY_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Create 4 to 6 concise vacancy search queries. Return one query per line without numbering. "
            "Use distinct role titles. If is_student is true, at least half the queries must explicitly target "
            "internship, intern, trainee, graduate, or student opportunities. Keep target roles but adapt them to "
            "the candidate's career stage.",
        ),
        ("human", "Profile:\n{profile}\n\nPreferred target roles: {target_roles}"),
    ]
)

SEMANTIC_MATCH_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Rank each job against the candidate using role meaning, career stage, opportunity type, transferable projects, "
            "and tools. Student candidates should prefer relevant internships, trainee roles, and graduate programs over "
            "ordinary full-time roles with similar skill overlap. Penalize roles whose seniority is unrealistic. "
            "Return JSON only: an array with one object per job containing id, score from 0 to 1, matched_keywords (only "
            "skills explicitly present in the profile), and reasons (up to 3 short factual reasons). "
            "A loosely related role must score below 0.20. Never invent candidate facts.",
        ),
        ("human", "Candidate profile:\n{profile}\n\nJobs:\n{jobs}"),
    ]
)

_STUDENT_TERMS = (
    "student", "undergraduate", "university", "college", "bachelor", "b.sc",
    "expected graduation", "graduating", "طالب", "جامعة", "بكالوريوس",
)
_INTERNSHIP_TERMS = ("internship", "intern", "trainee", "training", "co-op", "summer program")
_GRADUATE_TERMS = ("graduate program", "graduate programme", "new grad", "entry level", "entry-level")
_SENIOR_TERMS = ("mid-level", "mid level", "senior", "lead", "principal", "manager", "director", "head of")


def _json_from_model(content: Any) -> Any:
    text = content if isinstance(content, str) else str(content)
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    return json.loads(text)


def _normalise_profile_data(profile_data: dict[str, Any], cv_text: str = "") -> dict[str, Any]:
    list_value_keys = {
        "job_titles": ("title", "name", "value"),
        "primary_skills": ("skill", "name", "value"),
        "domains": ("domain", "name", "value"),
        "opportunity_types": ("type", "name", "value"),
    }
    for key, candidate_keys in list_value_keys.items():
        raw_values = profile_data.get(key)
        if not isinstance(raw_values, list):
            raw_values = [raw_values] if isinstance(raw_values, str) and raw_values.strip() else []
        normalized_values: list[str] = []
        for value in raw_values:
            if isinstance(value, str) and value.strip():
                normalized_values.append(value.strip())
            elif isinstance(value, dict):
                extracted = next(
                    (value.get(candidate) for candidate in candidate_keys if isinstance(value.get(candidate), str)),
                    "",
                )
                if extracted.strip():
                    normalized_values.append(extracted.strip())
        profile_data[key] = list(dict.fromkeys(normalized_values))

    raw_links = profile_data.get("links")
    if not isinstance(raw_links, list):
        raw_links = [raw_links] if isinstance(raw_links, (str, dict)) else []
    links: list[str] = []
    for link in raw_links:
        if isinstance(link, str) and link.strip():
            links.append(link.strip())
        elif isinstance(link, dict):
            url = next(
                (link.get(key) for key in ("url", "href", "link", "value") if isinstance(link.get(key), str)),
                "",
            )
            if url.strip():
                links.append(url.strip())
    profile_data["links"] = list(dict.fromkeys(links))

    for key in ("full_name", "email", "phone", "preferred_location", "education_level"):
        value = profile_data.get(key)
        if isinstance(value, list):
            value = next((item for item in value if isinstance(item, str) and item.strip()), None)
        elif isinstance(value, dict):
            value = next(
                (value.get(item) for item in ("value", "name", "text") if isinstance(value.get(item), str)),
                None,
            )
        profile_data[key] = value.strip() if isinstance(value, str) and value.strip() else None
    if not isinstance(profile_data.get("seniority"), str) or not profile_data["seniority"].strip():
        profile_data["seniority"] = "Student" if profile_data.get("is_student") else "Not specified"
    try:
        profile_data["years_experience"] = float(profile_data.get("years_experience") or 0)
    except (TypeError, ValueError):
        profile_data["years_experience"] = 0.0
    try:
        year = int(profile_data.get("graduation_year")) if profile_data.get("graduation_year") else None
        profile_data["graduation_year"] = year if year and 2000 <= year <= 2100 else None
    except (TypeError, ValueError):
        profile_data["graduation_year"] = None
    explicit_student = any(term in cv_text.casefold() for term in _STUDENT_TERMS)
    profile_data["is_student"] = bool(profile_data.get("is_student") or explicit_student)
    if profile_data["is_student"]:
        profile_data["seniority"] = "Student"
        preferred = [str(item).casefold() for item in profile_data["opportunity_types"]]
        for item in ("internship", "graduate"):
            if item not in preferred:
                profile_data["opportunity_types"].append(item)
    elif not profile_data["opportunity_types"]:
        profile_data["opportunity_types"] = ["full_time"]
    return profile_data


def extract_profile_node(state: JobSearchState) -> dict:
    if not state.get("refresh_profile"):
        cached = memory.get_profile(state["user_id"])
        if cached:
            return {"profile": cached}
    cv_text = state.get("cv_text", "").strip()
    if not cv_text:
        raise ValueError("A readable CV is required.")
    content = invoke_prompt(PROFILE_PROMPT, {"cv_text": cv_text}, json_mode=True)
    profile_data = _normalise_profile_data(_json_from_model(content), cv_text)
    profile = CVProfile.model_validate(profile_data).model_dump()
    memory.save_profile(state["user_id"], profile)
    return {"profile": profile}


def generate_queries_node(state: JobSearchState) -> dict:
    profile = state["profile"]
    content = invoke_prompt(
        QUERY_PROMPT,
        {
            "profile": json.dumps(profile, ensure_ascii=False),
            "target_roles": ", ".join(state.get("target_roles", [])) or "Use the profile's role titles",
        },
    )
    queries = []
    for line in str(content).splitlines():
        cleaned = re.sub(r"^\s*(?:\d+[.)]|[-•])\s*", "", line).strip()
        cleaned = re.split(r"\s+(?:at|for)\s+[\w]", cleaned, maxsplit=1, flags=re.IGNORECASE)[0].strip()
        if 1 < len(cleaned.split()) <= 8:
            queries.append(cleaned)
    roles = state.get("target_roles") or profile.get("job_titles") or ["software"]
    if profile.get("is_student"):
        queries = [f"{role} internship" for role in roles[:3]] + queries
    if not queries:
        queries = [" ".join(roles[:1] + profile.get("primary_skills", [])[:2])]
    return {"search_queries": list(dict.fromkeys(queries))[:6]}


def classify_opportunity(title: str, description: str = "") -> str:
    text = f"{title} {description}".casefold()
    if any(term in text for term in _INTERNSHIP_TERMS):
        return "internship"
    if any(term in text for term in _GRADUATE_TERMS):
        return "graduate"
    if "part time" in text or "part-time" in text:
        return "part_time"
    return "job"


def _search_adzuna(query: str, location: str) -> list[dict]:
    response = requests.get(
        f"https://api.adzuna.com/v1/api/jobs/{settings.ADZUNA_COUNTRY}/search/1",
        params={
            "app_id": settings.ADZUNA_APP_ID,
            "app_key": settings.ADZUNA_APP_KEY,
            "what": query,
            "where": location,
            "results_per_page": settings.RESULTS_PER_QUERY,
            "content-type": "application/json",
        },
        timeout=20,
    )
    response.raise_for_status()
    jobs = []
    for item in response.json().get("results", []):
        title = item.get("title", "")
        description = item.get("description", "")
        jobs.append(
            JobPosting(
                id=str(item.get("id")),
                title=title,
                company=(item.get("company") or {}).get("display_name", "N/A"),
                location=(item.get("location") or {}).get("display_name", location),
                description=description,
                url=item.get("redirect_url", ""),
                source="adzuna",
                opportunity_type=classify_opportunity(title, description),
            ).model_dump()
        )
    return jobs


def _playwright_jobs(queries: list[str], location: str, live_browser: bool) -> list[dict]:
    raw = scrape_jobs_for_queries(queries, location, settings.RESULTS_PER_QUERY, live_browser)
    return [
        JobPosting(
            id=stable_job_id(item["url"], f"{item.get('query', '')}-{index}"),
            title=item["title"],
            company=item.get("company") or "N/A",
            location=item["location"],
            description=item["snippet"],
            url=item["url"],
            source=item.get("source") or "duckduckgo_playwright",
            opportunity_type=classify_opportunity(item["title"], item["snippet"]),
        ).model_dump()
        for index, item in enumerate(raw)
    ]


def search_jobs_node(state: JobSearchState) -> dict:
    location = state.get("location_override") or state["profile"].get("preferred_location") or settings.DEFAULT_LOCATION
    jobs: dict[str, dict] = {}
    live_browser = bool(state.get("live_browser"))
    if settings.has_adzuna and not live_browser:
        for query in state["search_queries"]:
            try:
                found = _search_adzuna(query, location)
            except requests.RequestException:
                found = []
            for job in found:
                jobs[job["id"]] = job
    if not jobs or live_browser:
        for job in _playwright_jobs(state["search_queries"], location, live_browser):
            jobs[job["id"]] = job
    excluded_terms = [term.casefold() for term in state.get("excluded_title_terms", [])]
    return {
        "raw_jobs": [
            job for job in jobs.values()
            if not any(term in job["title"].casefold() for term in excluded_terms)
        ]
    }


def filter_new_jobs_node(state: JobSearchState) -> dict:
    # Manual searches must stay repeatable. Seen IDs are retained for history,
    # but must not make every subsequent search look empty.
    return {"new_jobs": list(state["raw_jobs"])}


def _normalise(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9+#.]{2,}", text.casefold()))


def _skill_matches(job: dict, skills: list[str]) -> list[str]:
    text = f"{job['title']} {job['description']}".casefold()
    tokens = _normalise(text)
    matches = []
    for skill in skills:
        normalized = skill.casefold().strip()
        if normalized in text or (len(normalized.split()) == 1 and normalized in tokens):
            matches.append(skill)
    return list(dict.fromkeys(matches))


def _stage_adjustment(job: dict, profile: dict) -> tuple[float, list[str]]:
    title = job["title"].casefold()
    opportunity = job.get("opportunity_type") or classify_opportunity(job["title"], job.get("description", ""))
    adjustment = 0.0
    reasons: list[str] = []
    if profile.get("is_student"):
        if opportunity == "internship":
            adjustment += 0.22
            reasons.append("Internship fits the candidate's current student stage.")
        elif opportunity == "graduate":
            adjustment += 0.14
            reasons.append("Graduate opportunity is suitable for an early-career candidate.")
        if any(term in title for term in _SENIOR_TERMS):
            adjustment -= 0.45
            reasons.append("Role seniority conflicts with the student profile.")
    return adjustment, reasons


def match_keywords_node(state: JobSearchState) -> dict:
    jobs = state["new_jobs"][:30]
    skills = state["profile"].get("primary_skills", [])
    if not jobs:
        return {"matched_jobs": []}
    llm_items: dict[str, dict] = {}
    try:
        content = invoke_prompt(
            SEMANTIC_MATCH_PROMPT,
            {
                "profile": json.dumps(state["profile"], ensure_ascii=False),
                "jobs": json.dumps(
                    [
                        {
                            "id": job["id"],
                            "title": job["title"],
                            "description": job["description"][:900],
                            "opportunity_type": job.get("opportunity_type", "job"),
                        }
                        for job in jobs
                    ],
                    ensure_ascii=False,
                ),
            },
            json_mode=True,
            timeout=180,
        )
        ranked = _json_from_model(content)
        if isinstance(ranked, list):
            llm_items = {str(item.get("id")): item for item in ranked if isinstance(item, dict)}
    except Exception:
        llm_items = {}

    target_roles = [role.casefold() for role in state.get("target_roles", [])]
    matched_jobs = []
    for job in jobs:
        deterministic_matches = _skill_matches(job, skills)
        llm_item = llm_items.get(job["id"], {})
        allowed = {skill.casefold(): skill for skill in skills}
        model_matches = [
            allowed[value.casefold()]
            for value in llm_item.get("matched_keywords", [])
            if isinstance(value, str) and value.casefold() in allowed
        ]
        matched = list(dict.fromkeys(model_matches + deterministic_matches))[:8]
        lexical_score = min(1.0, len(matched) / max(min(len(skills), 6), 1))
        try:
            semantic_score = max(0.0, min(1.0, float(llm_item.get("score", lexical_score))))
        except (TypeError, ValueError):
            semantic_score = lexical_score
        stage_boost, stage_reasons = _stage_adjustment(job, state["profile"])
        target_boost = 0.08 if target_roles and any(role in job["title"].casefold() for role in target_roles) else 0.0
        score = max(0.0, min(1.0, 0.65 * semantic_score + 0.35 * lexical_score + stage_boost + target_boost))
        reasons = [
            str(reason) for reason in llm_item.get("reasons", [])
            if isinstance(reason, str) and reason.strip()
        ][:3]
        reasons = list(dict.fromkeys(stage_reasons + reasons))
        if matched and not reasons:
            reasons.append(f"Matches {len(matched)} verified profile skill(s).")
        if score >= 0.18 and (matched or job.get("opportunity_type") in {"internship", "graduate"}):
            matched_jobs.append(
                MatchedJob(
                    job=JobPosting(**job),
                    matched_keywords=matched,
                    match_score=round(score, 3),
                    score_breakdown={
                        "semantic": round(semantic_score, 3),
                        "skills": round(lexical_score, 3),
                        "career_stage_adjustment": round(stage_boost, 3),
                        "target_role_boost": round(target_boost, 3),
                    },
                    match_reasons=reasons,
                ).model_dump()
            )
    return {"matched_jobs": matched_jobs}


def rank_and_format_node(state: JobSearchState) -> dict:
    top = sorted(state["matched_jobs"], key=lambda item: item["match_score"], reverse=True)[: settings.TOP_N_JOBS]
    if not top:
        report = "No new matching jobs were found. Try a broader location or role."
    else:
        lines = [f"# Latest matching opportunities ({len(top)})\n"]
        for match in top:
            job = match["job"]
            lines.extend(
                [
                    f"## {job['title']} - {job['company']}",
                    f"{job['location']} | {job.get('opportunity_type', 'job')} | [Open job]({job['url']})",
                    f"Match: {int(match['match_score'] * 100)}%",
                    f"Skills matched: {', '.join(match['matched_keywords']) or 'Career-stage match'}",
                    "",
                ]
            )
        report = "\n".join(lines)
    memory.mark_jobs_seen(state["user_id"], [match["job"]["id"] for match in top])
    return {"final_report": report}
