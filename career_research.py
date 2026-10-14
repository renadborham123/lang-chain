"""Find current, source-linked events and competitions for a candidate."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from public_search import public_search, public_search_url


_OPPORTUNITY_TERMS = re.compile(
    r"\b(?:hackathon|competition|challenge|career fair|job fair|meetup|conference|bootcamp|open source|fellowship)\b",
    re.IGNORECASE,
)


def discover_growth_opportunities(payload: dict[str, Any]) -> dict[str, Any]:
    profile = payload.get("profile") if isinstance(payload.get("profile"), dict) else {}
    location = str(payload.get("location") or profile.get("preferred_location") or "").strip()
    roles = [str(item).strip() for item in (profile.get("job_titles") or []) if str(item).strip()]
    domains = [str(item).strip() for item in (profile.get("domains") or []) if str(item).strip()]
    focus = roles[0] if roles else domains[0] if domains else "early career technology"
    year = datetime.now().year
    query = f'"{focus}" (hackathon OR competition OR "career fair" OR meetup) {location} {year}'.strip()
    raw = public_search(query, 10)
    items = []
    for item in raw:
        combined = f"{item.get('title', '')} {item.get('snippet', '')}"
        if not _OPPORTUNITY_TERMS.search(combined):
            continue
        items.append(
            {
                "title": item["title"],
                "url": item["url"],
                "snippet": item["snippet"],
                "type": (_OPPORTUNITY_TERMS.search(combined).group(0) if _OPPORTUNITY_TERMS.search(combined) else "opportunity").title(),
                "verification": "Public source found. Check the organiser page for date, eligibility, and availability before acting.",
            }
        )
        if len(items) >= 4:
            break
    return {
        "query": query,
        "search_url": public_search_url(query),
        "items": items,
        "message": (
            f"Found {len(items)} source-linked opportunit{'y' if len(items) == 1 else 'ies'}."
            if items
            else "No sufficiently clear current opportunity was found, so nothing was recommended."
        ),
    }
