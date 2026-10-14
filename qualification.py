"""Deterministic qualification rules that run before the application agent."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlsplit


def is_direct_listing(url: str) -> bool:
    """Recognise common individual job-posting URLs, not result/category pages."""
    parsed = urlsplit(url.strip())
    host = (parsed.hostname or "").casefold().rstrip(".")
    path = parsed.path.casefold().rstrip("/") + "/"

    def host_is(domain: str) -> bool:
        return host == domain or host.endswith(f".{domain}")

    if host_is("linkedin.com"):
        return path.startswith("/jobs/view/")
    if host_is("wuzzuf.net"):
        return path.startswith("/jobs/p/")
    if host_is("indeed.com"):
        return path.startswith("/viewjob/") or path == "/viewjob/"
    if host in {"boards.greenhouse.io", "job-boards.greenhouse.io"} or host_is("greenhouse.io"):
        return "/jobs/" in path
    if host == "jobs.lever.co" or host.endswith(".jobs.lever.co"):
        return len([part for part in path.split("/") if part]) >= 2
    if host_is("myworkdayjobs.com"):
        return "/job/" in path
    if host in {"jobs.smartrecruiters.com", "jobs.ashbyhq.com"}:
        return len([part for part in path.split("/") if part]) >= 2
    if host_is("workable.com") and path.startswith("/j/"):
        return True

    query_keys = {key.casefold() for key in parse_qs(parsed.query)}
    if query_keys & {"gh_jid", "job_id", "jobid", "jk", "requisitionid", "rid"}:
        return True
    if re.search(r"(?:^|[-_/])jid[-_/]?\d+", path):
        return True
    if re.search(r"/[^/]+\.(?:com|net|org|io|co)/", path):
        return False
    if re.search(r"/(?:job|jobs|position|positions|vacancy|vacancies|opening|openings)/[^/]+", path):
        return True

    first_host_label = host.split(".", 1)[0]
    path_parts = [part for part in path.split("/") if part]
    category_parts = {"all", "browse", "categories", "category", "search", "results", "vacancies"}
    return bool(
        first_host_label in {"career", "careers", "job", "jobs"}
        and path_parts
        and not category_parts.intersection(path_parts)
    )


def qualify_match(match: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """Classify a match as ready, review, or excluded with explicit reasons."""
    job = match["job"]
    score = float(match.get("match_score", 0))
    role_score = float((match.get("score_breakdown") or {}).get("role_title", 0))
    keywords = match.get("matched_keywords", [])
    title = job.get("title", "").lower()
    candidate_seniority = str(profile.get("seniority") or "").lower()
    candidate_years = float(profile.get("years_experience") or 0)
    stage_adjustment = float((match.get("score_breakdown") or {}).get("career_stage_adjustment", 0))
    direct_listing = is_direct_listing(job.get("url", ""))
    reasons: list[str] = []

    opportunity_type = job.get("opportunity_type", "job")
    advanced_title = any(
        word in title for word in ("mid-level", "mid level", "senior", "lead", "principal", "manager", "director")
    )
    senior_title = any(word in title for word in ("senior", "lead", "principal", "manager", "director"))
    senior_profile = any(word in candidate_seniority for word in ("senior", "lead", "principal", "manager"))
    early_profile = profile.get("is_student") or any(
        word in candidate_seniority for word in ("junior", "entry", "intern", "student")
    )
    if (advanced_title and early_profile) or (
        senior_title and 0 < candidate_years < 4 and not senior_profile
    ):
        return {"status": "excluded", "reasons": ["Role seniority exceeds the candidate profile."], "priority": 0, "direct_listing": direct_listing}
    experience_text = f"{title} {job.get('description', '')}".casefold()
    range_match = re.search(r"\b(\d+)\s*(?:-|–|—|to)\s*\d+\s*(?:years?|yrs?)\b", experience_text)
    plus_match = re.search(r"\b(\d+)\s*\+\s*(?:years?|yrs?)\b", experience_text)
    required_minimum = int((range_match or plus_match).group(1)) if range_match or plus_match else 0
    if required_minimum and required_minimum >= candidate_years + 2:
        return {
            "status": "excluded",
            "reasons": [f"The role asks for at least {required_minimum} years of experience."],
            "priority": 0,
            "direct_listing": direct_listing,
        }
    if not direct_listing:
        return {"status": "excluded", "reasons": ["This result is a search or category page, not an individual application."], "priority": 0, "direct_listing": False}
    if profile.get("is_student") and opportunity_type in {"internship", "graduate"} and score >= 0.28:
        reasons.append("Career stage and opportunity type fit a student profile.")
        if keywords:
            reasons.append(f"{len(keywords)} verified profile skill(s) match.")
        return {"status": "ready", "reasons": reasons, "priority": 3, "direct_listing": True}
    if len(keywords) >= 2 and score >= 0.25 and stage_adjustment >= 0:
        reasons.append(f"{len(keywords)} CV skills are explicitly matched.")
        return {"status": "ready", "reasons": reasons, "priority": 2, "direct_listing": True}
    if role_score >= 0.5 and score >= 0.28:
        reasons.append("The job title closely matches the candidate's target role.")
        if keywords:
            reasons.append(f"{len(keywords)} CV skill is explicitly matched.")
        return {"status": "review", "reasons": reasons, "priority": 2, "direct_listing": True}
    if keywords and score >= 0.12:
        reasons.append("At least one CV skill is matched; inspect requirements before applying.")
        return {"status": "review", "reasons": reasons, "priority": 1, "direct_listing": True}
    if score >= 0.35 and match.get("match_reasons"):
        reasons.append("The semantic match is promising, but the source did not expose enough skill detail.")
        return {"status": "review", "reasons": reasons, "priority": 1, "direct_listing": True}
    return {"status": "excluded", "reasons": ["Not enough skill overlap to justify an application."], "priority": 0, "direct_listing": True}
