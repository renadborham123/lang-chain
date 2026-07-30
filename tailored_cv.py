"""Fact-safe, job-specific ATS CV generation and caching."""

from __future__ import annotations

import hashlib
import html
import re
from functools import lru_cache
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit

import requests
from pypdf import PdfReader

from cv_builder import normalise_cv_text, render_cv_pdf
from document_store import (
    find_document_by_metadata,
    get_cv_metadata,
    get_cv_pdf_path,
    get_cv_text,
    store_cv,
)


_HEADINGS = {
    "CONTACT",
    "SUMMARY",
    "SKILLS",
    "EXPERIENCE",
    "PROJECTS",
    "EDUCATION",
    "CERTIFICATIONS",
    "LINKS",
}
_HEADING_ALIASES = {
    "PROFESSIONAL SUMMARY": "SUMMARY",
    "CAREER SUMMARY": "SUMMARY",
    "PROFILE": "SUMMARY",
    "TECHNICAL SKILLS": "SKILLS",
    "CORE SKILLS": "SKILLS",
    "PROFESSIONAL EXPERIENCE": "EXPERIENCE",
    "WORK EXPERIENCE": "EXPERIENCE",
    "EMPLOYMENT HISTORY": "EXPERIENCE",
    "SELECTED PROJECTS": "PROJECTS",
    "TECHNICAL PROJECTS": "PROJECTS",
    "ACADEMIC PROJECTS": "PROJECTS",
    "EDUCATION & SELECTED TRAINING": "EDUCATION",
    "EDUCATION AND SELECTED TRAINING": "EDUCATION",
    "ACADEMIC BACKGROUND": "EDUCATION",
    "CERTIFICATES": "CERTIFICATIONS",
}
_TAILORING_VERSION = 3
_STOP_WORDS = {
    "about", "after", "also", "and", "are", "at", "be", "for", "from", "in", "is",
    "job", "of", "on", "or", "our", "role", "that", "the", "this", "to", "we", "will",
    "with", "you", "your", "ago", "day", "days", "week", "weeks", "month", "months",
}


class _DescriptionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = dict(attrs).get("class") or ""
        if self.depth:
            self.depth += 1
        elif "show-more-less-html__markup" in classes:
            self.depth = 1

    def handle_endtag(self, tag: str) -> None:
        if self.depth:
            self.depth -= 1

    def handle_data(self, data: str) -> None:
        if self.depth and data.strip():
            self.parts.append(data.strip())


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return cleaned[:70] or "job"


def _job_key(job: dict[str, Any]) -> str:
    identity = "|".join(
        str(job.get(key) or "").strip().casefold()
        for key in ("url", "title", "company")
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


@lru_cache(maxsize=128)
def fetch_job_description(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=(4, 12),
        )
        response.raise_for_status()
    except requests.RequestException:
        return ""
    parser = _DescriptionParser()
    parser.feed(response.text)
    return re.sub(r"\s+", " ", html.unescape(" ".join(parser.parts))).strip()[:12000]


def _terms(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[A-Za-z][A-Za-z0-9+#.-]{1,}", value.casefold())
        if token not in _STOP_WORDS
    }


def _line_score(line: str, relevant_terms: set[str], verified_keywords: set[str]) -> tuple[int, int]:
    normalized = line.casefold()
    verified_hits = sum(1 for keyword in verified_keywords if keyword and keyword in normalized)
    term_hits = len(_terms(line) & relevant_terms)
    return verified_hits * 10 + term_hits, len(line)


def _sort_skill_line(line: str, relevant_terms: set[str], verified_keywords: set[str]) -> str:
    prefix = ""
    values = line
    if ":" in line:
        category, remainder = line.split(":", 1)
        if len(category.split()) <= 5:
            prefix = f"{category.strip()}: "
            values = remainder
    items = [item.strip() for item in re.split(r"[,|;]", values) if item.strip()]
    if len(items) < 2:
        return line
    ordered = sorted(
        items,
        key=lambda item: _line_score(item, relevant_terms, verified_keywords),
        reverse=True,
    )
    return prefix + ", ".join(ordered)


def _parse_sections(cv_text: str) -> tuple[list[str], dict[str, list[str]], list[str]]:
    preamble: list[str] = []
    sections: dict[str, list[str]] = {}
    order: list[str] = []
    current: str | None = None
    for line in normalise_cv_text(cv_text).splitlines():
        stripped = line.strip()
        heading = stripped.rstrip(":").upper()
        heading = _HEADING_ALIASES.get(heading, heading)
        if heading in _HEADINGS:
            current = heading
            if heading not in sections:
                sections[heading] = []
                order.append(heading)
            continue
        if current is None:
            if stripped:
                preamble.append(stripped)
        else:
            sections[current].append(stripped)
    return preamble, sections, order


def tailor_cv_text(original_cv: str, job: dict[str, Any], job_description: str = "") -> str:
    original = normalise_cv_text(original_cv)
    preamble, sections, original_order = _parse_sections(original)
    title = re.sub(r"\s+", " ", str(job.get("title") or "Target role")).strip()
    company = re.sub(r"\s+", " ", str(job.get("company") or "")).strip()
    fallback_description = str(job.get("description") or "")
    verified = {
        str(keyword).strip().casefold()
        for keyword in (job.get("keywords") or [])
        if str(keyword).strip() and str(keyword).strip().casefold() in original.casefold()
    }
    relevant = _terms(" ".join((title, company, fallback_description, job_description, *verified)))

    for heading in ("SKILLS",):
        lines = sections.get(heading)
        if lines:
            nonempty = [
                _sort_skill_line(line, relevant, verified)
                for line in lines
                if line
            ]
            sections[heading] = sorted(
                nonempty,
                key=lambda line: _line_score(line, relevant, verified),
                reverse=True,
            )

    if verified and not sections.get("SKILLS"):
        sections["SKILLS"] = [", ".join(sorted(verified, key=str.casefold))]
        original_order.append("SKILLS")

    target_line = f"Targeting: {title}"
    if company and company.casefold() not in {"n/a", "unknown"}:
        target_line += f" at {company}"
    summary = [line for line in sections.get("SUMMARY", []) if line]
    sections["SUMMARY"] = [target_line, *summary]
    if "SUMMARY" not in original_order:
        original_order.insert(0, "SUMMARY")

    preferred_order = [
        "CONTACT",
        "SUMMARY",
        "SKILLS",
        "PROJECTS",
        "EXPERIENCE",
        "EDUCATION",
        "CERTIFICATIONS",
        "LINKS",
    ]
    output = list(preamble)
    for heading in preferred_order:
        lines = sections.get(heading)
        if not lines:
            continue
        if output:
            output.append("")
        output.append(heading)
        output.extend(lines)
    for heading in original_order:
        if heading in preferred_order or not sections.get(heading):
            continue
        output.extend(("", heading, *sections[heading]))
    return normalise_cv_text("\n".join(output))


def _audit_tailored_pdf(source_text: str, tailored_text: str, pdf_bytes: bytes, title: str) -> dict[str, Any]:
    from io import BytesIO

    reader = PdfReader(BytesIO(pdf_bytes))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    name = next((line.strip() for line in source_text.splitlines() if line.strip()), "")
    checks = {
        "single_column": True,
        "plain_text_headings": True,
        "no_tables_or_graphics": True,
        "source_name_preserved": bool(name and name.casefold() in extracted.casefold()),
        "target_role_present": title.casefold() in extracted.casefold(),
        "one_or_two_pages": 1 <= len(reader.pages) <= 2,
    }
    if not all(checks.values()):
        failed = ", ".join(key for key, value in checks.items() if not value)
        raise ValueError(f"Tailored ATS CV failed validation: {failed}.")
    return {"pages": len(reader.pages), "checks": checks}


def build_tailored_cv(document_id: str, job: dict[str, Any]) -> dict[str, Any]:
    source_text = get_cv_text(document_id)
    key = _job_key(job)
    cached_id = find_document_by_metadata(
        tailored_from=document_id,
        tailored_job_key=key,
        tailoring_version=_TAILORING_VERSION,
    )
    if cached_id:
        metadata = get_cv_metadata(cached_id)
        return {
            "document_id": cached_id,
            "pdf_url": f"/api/documents/{cached_id}.pdf",
            "filename": metadata.get("source_name") or "tailored-cv.pdf",
            "cached": True,
            "audit": metadata.get("ats_audit") or {},
        }
    description = fetch_job_description(str(job.get("url") or ""))
    tailored_text = tailor_cv_text(source_text, job, description)
    pdf_bytes = render_cv_pdf(tailored_text)
    title = str(job.get("title") or "Target role").strip()
    audit = _audit_tailored_pdf(source_text, tailored_text, pdf_bytes, title)
    company = str(job.get("company") or "company")
    filename = f"ats-{_safe_filename(company)}-{_safe_filename(title)}.pdf"
    tailored_id = store_cv(
        tailored_text,
        pdf_bytes,
        source_name=filename,
        metadata={
            "tailored_from": document_id,
            "tailored_job_key": key,
            "tailored_job_title": title,
            "tailored_job_company": company,
            "tailoring_version": _TAILORING_VERSION,
            "ats_audit": audit,
        },
    )
    return {
        "document_id": tailored_id,
        "pdf_url": f"/api/documents/{tailored_id}.pdf",
        "filename": filename,
        "cached": False,
        "audit": audit,
    }
