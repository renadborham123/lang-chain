"""Nodes for the CV-to-jobs LangGraph workflow."""

from __future__ import annotations

import json
import re
from typing import Any

import requests
from langchain_core.prompts import ChatPromptTemplate

from config import settings
from memory_store import memory
from scrape_jobs import scrape_jobs_with_playwright, stable_job_id
from state import CVProfile, JobPosting, JobSearchState, MatchedJob


def _build_llm():
    """Create the Gemini agent only when a LangGraph node needs it."""
    if not settings.GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY is missing. Add it to the local .env file.")
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=settings.GOOGLE_MODEL,
        google_api_key=settings.GOOGLE_API_KEY,
        temperature=0,
    )


PROFILE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "Read this CV and return JSON only. Required keys: full_name, job_titles, seniority, primary_skills, domains, years_experience, preferred_location. Use arrays for job_titles, primary_skills and domains."),
    ("human", "CV:\n{cv_text}"),
])

QUERY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "Create 3 to 5 concise job-search queries from the candidate profile. Prefer distinct individual vacancy titles over broad categories. Return one query per line, with no numbering or commentary."),
    ("human", "Profile:\n{profile}\n\nTarget roles (strictly prioritise these): {target_roles}"),
])

SEMANTIC_MATCH_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "You are a precise job-to-CV matcher. Compare meaning, transferable experience, and tools—not just exact words. Return JSON only: an array of objects with id, score (0 to 1), and matched_keywords (up to 5 skills explicitly present in the candidate profile). Do not invent skills or experience. A role that is only loosely related should score below 0.20."),
    ("human", "Candidate profile:\n{profile}\n\nJobs:\n{jobs}"),
])


def _json_from_model(content: Any) -> dict[str, Any]:
    text = content if isinstance(content, str) else str(content)
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    return json.loads(text)


def _normalise_profile_data(profile_data: dict[str, Any]) -> dict[str, Any]:
    """Make sparse CV extractions valid without discarding useful fields."""
    for key in ("job_titles", "primary_skills", "domains"):
        if not isinstance(profile_data.get(key), list):
            profile_data[key] = []
    if not isinstance(profile_data.get("seniority"), str) or not profile_data["seniority"].strip():
        profile_data["seniority"] = "Not specified"
    try:
        profile_data["years_experience"] = float(profile_data.get("years_experience") or 0)
    except (TypeError, ValueError):
        profile_data["years_experience"] = 0.0
    if isinstance(profile_data.get("preferred_location"), list):
        profile_data["preferred_location"] = ", ".join(profile_data["preferred_location"])
    return profile_data


def extract_profile_node(state: JobSearchState) -> dict:
    if not state.get("refresh_profile"):
        cached = memory.get_profile(state["user_id"])
        if cached:
            return {"profile": cached}

    if not state.get("cv_text", "").strip():
        raise ValueError("A CV is required the first time. Pass --cv path/to/cv.pdf.")

    llm = _build_llm()
    response = (PROFILE_PROMPT | llm).invoke({"cv_text": state["cv_text"]})
    profile_data = _normalise_profile_data(_json_from_model(response.content))
    # Models occasionally return multiple acceptable locations as an array;
    # persist it as one searchable location string used by the job-source node.
    profile = CVProfile.model_validate(profile_data).model_dump()
    memory.save_profile(state["user_id"], profile)
    return {"profile": profile}


def generate_queries_node(state: JobSearchState) -> dict:
    profile = state["profile"]
    llm = _build_llm()
    response = (QUERY_PROMPT | llm).invoke({
        "profile": json.dumps(profile, ensure_ascii=False),
        "target_roles": ", ".join(state.get("target_roles", [])) or "Use the CV's role titles",
    })
    queries = [line.strip(" -•\t") for line in str(response.content).splitlines() if line.strip()]
    if not queries:
        queries = [" ".join(profile.get("job_titles", []) + profile.get("primary_skills", [])[:2])]
    return {"search_queries": queries[:5]}


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
    return [
        JobPosting(
            id=str(item.get("id")),
            title=item.get("title", ""),
            company=(item.get("company") or {}).get("display_name", "N/A"),
            location=(item.get("location") or {}).get("display_name", location),
            description=item.get("description", ""),
            url=item.get("redirect_url", ""),
            source="adzuna",
        ).model_dump()
        for item in response.json().get("results", [])
    ]


def _search_playwright(query: str, location: str, live_browser: bool = False) -> list[dict]:
    return [
        JobPosting(
            id=stable_job_id(item["url"], f"{query}-{index}"),
            title=item["title"],
            company="N/A",
            location=item["location"],
            description=item["snippet"],
            url=item["url"],
            source="duckduckgo_playwright",
        ).model_dump()
        for index, item in enumerate(scrape_jobs_with_playwright(query, location, settings.RESULTS_PER_QUERY, live_browser=live_browser))
    ]


def search_jobs_node(state: JobSearchState) -> dict:
    location = state.get("location_override") or state["profile"].get("preferred_location") or settings.DEFAULT_LOCATION
    jobs: dict[str, dict] = {}
    for query in state["search_queries"]:
        try:
            found = _search_adzuna(query, location) if settings.has_adzuna else _search_playwright(query, location, state.get("live_browser", False))
        except requests.RequestException:
            found = _search_playwright(query, location, state.get("live_browser", False))
        for job in found:
            title = job["title"].lower()
            excluded_terms = [term.lower() for term in state.get("excluded_title_terms", [])]
            target_roles = [term.lower() for term in state.get("target_roles", [])]
            if any(term in title for term in excluded_terms):
                continue
            if target_roles and not any(term in title for term in target_roles):
                continue
            jobs[job["id"]] = job
    return {"raw_jobs": list(jobs.values())}


def filter_new_jobs_node(state: JobSearchState) -> dict:
    seen = memory.get_seen_job_ids(state["user_id"])
    return {"new_jobs": [job for job in state["raw_jobs"] if job["id"] not in seen]}


def _normalise(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9+#.]{2,}", text.lower()))


def match_keywords_node(state: JobSearchState) -> dict:
    """Use Gemini once to semantically rank the discovered roles against the CV."""
    jobs = state["new_jobs"][:30]
    skills = state["profile"].get("primary_skills", [])
    if not jobs:
        return {"matched_jobs": []}
    try:
        response = (SEMANTIC_MATCH_PROMPT | _build_llm()).invoke({
            "profile": json.dumps(state["profile"], ensure_ascii=False),
            "jobs": json.dumps([{"id": job["id"], "title": job["title"], "description": job["description"][:700]} for job in jobs], ensure_ascii=False),
        })
        ranked = _json_from_model(response.content)
        if not isinstance(ranked, list):
            raise ValueError("Semantic matcher did not return a list.")
        by_id = {job["id"]: job for job in jobs}
        allowed_skills = {skill.casefold(): skill for skill in skills}
        matched_jobs = []
        for item in ranked:
            job = by_id.get(str(item.get("id", "")))
            if not job:
                continue
            score = max(0.0, min(1.0, float(item.get("score", 0))))
            matched = [allowed_skills[value.casefold()] for value in item.get("matched_keywords", []) if isinstance(value, str) and value.casefold() in allowed_skills]
            if score >= 0.20 and matched:
                matched_jobs.append(MatchedJob(job=JobPosting(**job), matched_keywords=list(dict.fromkeys(matched)), match_score=round(score, 2)).model_dump())
        return {"matched_jobs": matched_jobs}
    except Exception:
        # A deterministic fallback keeps discovery usable if the semantic call is unavailable.
        matched_jobs = []
        for job in jobs:
            text = _normalise(f"{job['title']} {job['description']}")
            matched = [skill for skill in skills if skill.lower() in text]
            if matched:
                matched_jobs.append(MatchedJob(job=JobPosting(**job), matched_keywords=matched, match_score=round(len(matched) / max(len(skills), 1), 2)).model_dump())
        return {"matched_jobs": matched_jobs}


def rank_and_format_node(state: JobSearchState) -> dict:
    top = sorted(state["matched_jobs"], key=lambda item: item["match_score"], reverse=True)[: settings.TOP_N_JOBS]
    if not top:
        report = "No new matching jobs were found in this run. Try again later or expand the CV skills/location."
    else:
        lines = [f"# Latest matching jobs ({len(top)})\n"]
        for match in top:
            job = match["job"]
            lines.extend([
                f"## {job['title']} — {job['company']}",
                f"{job['location']} | [Open job]({job['url']})",
                f"Match: {int(match['match_score'] * 100)}%",
                f"Keywords matched: {', '.join(match['matched_keywords'])}",
                "",
            ])
        report = "\n".join(lines)
    memory.mark_jobs_seen(state["user_id"], [match["job"]["id"] for match in top])
    return {"final_report": report}
