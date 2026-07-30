"""Deterministic qualification rules that run before the application agent."""

from __future__ import annotations

from typing import Any


def is_direct_listing(url: str) -> bool:
    """Recognise common individual job-posting URLs, not result/category pages."""
    normalized = url.lower().split("?")[0]
    return any(pattern in normalized for pattern in (
        "linkedin.com/jobs/view/",
        "wuzzuf.net/jobs/p/",
        "indeed.com/viewjob",
        "greenhouse.io/jobs/",
        "jobs.lever.co/",
        "myworkdayjobs.com/",
    ))


def qualify_match(match: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """Classify a match as ready, review, or excluded with explicit reasons."""
    job = match["job"]
    score = float(match.get("match_score", 0))
    keywords = match.get("matched_keywords", [])
    title = job.get("title", "").lower()
    candidate_seniority = str(profile.get("seniority") or "").lower()
    direct_listing = is_direct_listing(job.get("url", ""))
    reasons: list[str] = []

    opportunity_type = job.get("opportunity_type", "job")
    if any(word in title for word in ("mid-level", "mid level", "senior", "lead", "principal", "manager", "director")) and (
        profile.get("is_student") or any(word in candidate_seniority for word in ("junior", "entry", "intern", "student"))
    ):
        return {"status": "excluded", "reasons": ["Role seniority exceeds the candidate profile."], "priority": 0, "direct_listing": direct_listing}
    if not direct_listing:
        return {"status": "review", "reasons": ["This is a search or category page; open it and confirm an individual live listing first."], "priority": 1, "direct_listing": False}
    if profile.get("is_student") and opportunity_type in {"internship", "graduate"} and score >= 0.28:
        reasons.append("Career stage and opportunity type fit a student profile.")
        if keywords:
            reasons.append(f"{len(keywords)} verified profile skill(s) match.")
        return {"status": "ready", "reasons": reasons, "priority": 3, "direct_listing": True}
    if len(keywords) >= 2 and score >= 0.25:
        reasons.append(f"{len(keywords)} CV skills are explicitly matched.")
        return {"status": "ready", "reasons": reasons, "priority": 2, "direct_listing": True}
    if keywords and score >= 0.12:
        reasons.append("At least one CV skill is matched; inspect requirements before applying.")
        return {"status": "review", "reasons": reasons, "priority": 1, "direct_listing": True}
    return {"status": "excluded", "reasons": ["Not enough skill overlap to justify an application."], "priority": 0, "direct_listing": True}
