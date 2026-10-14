"""Create a new CV version from facts the user explicitly confirmed."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from career_memory import career_memory
from cv_builder import normalise_cv_text, render_cv_pdf
from document_store import (
    find_document_by_metadata,
    get_cv_metadata,
    get_cv_text,
    store_cv,
)


_KNOWN_HEADINGS = {
    "CONTACT", "SUMMARY", "SKILLS", "EXPERIENCE", "PROJECTS", "EDUCATION",
    "CERTIFICATIONS", "LANGUAGES", "LINKS",
}


def _append_section_facts(cv_text: str, facts: dict[str, list[str]]) -> str:
    lines = normalise_cv_text(cv_text).splitlines()
    existing = "\n".join(lines).casefold()
    additions = {
        section: [line for line in values if line.casefold() not in existing]
        for section, values in facts.items()
    }
    additions = {section: values for section, values in additions.items() if values}
    if not additions:
        return normalise_cv_text(cv_text)

    output: list[str] = []
    inserted: set[str] = set()
    for index, line in enumerate(lines):
        heading = line.strip().rstrip(":").upper()
        if heading in _KNOWN_HEADINGS:
            previous_heading = next(
                (
                    lines[prior].strip().rstrip(":").upper()
                    for prior in range(index - 1, -1, -1)
                    if lines[prior].strip().rstrip(":").upper() in _KNOWN_HEADINGS
                ),
                "",
            )
            if previous_heading in additions and previous_heading not in inserted:
                while output and not output[-1].strip():
                    output.pop()
                output.extend(additions[previous_heading])
                output.append("")
                inserted.add(previous_heading)
        output.append(line)
    last_heading = next(
        (line.strip().rstrip(":").upper() for line in reversed(lines) if line.strip().rstrip(":").upper() in _KNOWN_HEADINGS),
        "",
    )
    if last_heading in additions and last_heading not in inserted:
        output.extend(additions[last_heading])
        inserted.add(last_heading)
    for section, values in additions.items():
        if section in inserted:
            continue
        if output and output[-1].strip():
            output.append("")
        output.extend((section, *values))
    return normalise_cv_text("\n".join(output))


def enrich_cv_document(document_id: str, user_id: str = "local-user") -> dict[str, Any]:
    facts = career_memory.cv_facts(document_id, user_id)
    if not facts:
        raise ValueError("No confirmed CV-safe facts are ready to add.")
    revision = career_memory.revision(document_id, user_id)
    cached = find_document_by_metadata(
        user_id=user_id,
        career_enriched_from=document_id,
        career_memory_revision=revision,
    )
    if cached:
        metadata = get_cv_metadata(cached, user_id)
        return {
            "document_id": cached,
            "pdf_url": f"/api/documents/{cached}.pdf",
            "filename": metadata.get("source_name") or "wazzefni-updated-cv.pdf",
            "added": facts,
            "cached": True,
        }

    source_text = get_cv_text(document_id, user_id)
    enriched_text = _append_section_facts(source_text, facts)
    if enriched_text == normalise_cv_text(source_text):
        raise ValueError("Those confirmed facts are already present in the CV.")
    source_name = str(get_cv_metadata(document_id, user_id).get("source_name") or "cv.pdf")
    stem = Path(source_name).stem
    filename = f"{stem}-updated.pdf"
    enriched_id = store_cv(
        enriched_text,
        render_cv_pdf(enriched_text),
        source_name=filename,
        metadata={
            "career_enriched_from": document_id,
            "career_memory_revision": revision,
            "career_facts_added": facts,
        },
        user_id=user_id,
    )
    career_memory.copy(document_id, enriched_id, user_id)
    return {
        "document_id": enriched_id,
        "pdf_url": f"/api/documents/{enriched_id}.pdf",
        "filename": filename,
        "added": facts,
        "cached": False,
    }
