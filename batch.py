"""Parallel, bounded execution for up to ten CV job-search agents."""

from __future__ import annotations

import hashlib
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Iterable

from graph import build_graph

MAX_BATCH_SIZE = 10


def _safe_candidate_id(name: str, cv_text: str) -> str:
    label = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "candidate"
    digest = hashlib.sha256(cv_text.encode("utf-8")).hexdigest()[:10]
    return f"batch-{label[:32]}-{digest}"


def _run_candidate(name: str, cv_text: str, location: str, target_roles: list[str] | None = None, excluded_title_terms: list[str] | None = None) -> dict[str, Any]:
    user_id = _safe_candidate_id(name, cv_text)
    candidate_graph = build_graph()
    try:
        result = candidate_graph.invoke(
            {"user_id": user_id, "cv_text": cv_text, "refresh_profile": True, "location_override": location, "target_roles": target_roles or [], "excluded_title_terms": excluded_title_terms or []},
            {"configurable": {"thread_id": user_id}},
        )
        return {"candidate": name, "user_id": user_id, "result": result, "error": None}
    except Exception as exc:
        return {"candidate": name, "user_id": user_id, "result": None, "error": str(exc)}


def run_batch_search(candidates: Iterable[tuple[str, str]], location: str, max_workers: int = MAX_BATCH_SIZE, target_roles: list[str] | None = None, excluded_title_terms: list[str] | None = None) -> list[dict[str, Any]]:
    """Run isolated LangGraph agents concurrently for at most ten CVs.

    This function only discovers and ranks public job listings. It never submits
    an application or transfers a CV to a job board.
    """
    items = list(candidates)
    if not items:
        return []
    if len(items) > MAX_BATCH_SIZE:
        raise ValueError(f"A batch can contain at most {MAX_BATCH_SIZE} CVs.")
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(max_workers, MAX_BATCH_SIZE, len(items))) as executor:
        futures = {executor.submit(_run_candidate, name, text, location, target_roles, excluded_title_terms): index for index, (name, text) in enumerate(items)}
        ordered: dict[int, dict[str, Any]] = {}
        for future in as_completed(futures):
            ordered[futures[future]] = future.result()
    return [ordered[index] for index in sorted(ordered)]


def application_review_rows(batch_results: Iterable[dict[str, Any]], limit_per_cv: int = 10) -> list[dict[str, Any]]:
    """Create a human review queue; opening a link remains a human decision."""
    rows: list[dict[str, Any]] = []
    for item in batch_results:
        result = item.get("result") or {}
        for match in result.get("matched_jobs", [])[:limit_per_cv]:
            job = match["job"]
            rows.append({
                "Candidate": item["candidate"], "Role": job["title"], "Company": job["company"],
                "Match": f"{int(match['match_score'] * 100)}%", "Keywords": ", ".join(match["matched_keywords"]),
                "Apply link": job["url"], "Status": "Review required",
            })
    return rows
