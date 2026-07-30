"""Fact-only ATS CV generation with readiness validation and PDF output."""

from __future__ import annotations

import re
from io import BytesIO
from typing import Any

from langchain_core.prompts import ChatPromptTemplate

from document_store import store_cv
from model_provider import invoke_prompt


_CV_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Create a one or two page ATS-friendly plain-text CV from the candidate's answers. "
            "Use only supplied facts. Never invent employers, dates, degrees, grades, metrics, certifications, or skills. "
            "If information is missing, omit it. Use these uppercase headings when applicable: CONTACT, SUMMARY, SKILLS, "
            "EXPERIENCE, PROJECTS, EDUCATION, CERTIFICATIONS, LINKS. Put the candidate name alone on the first line. "
            "Use simple bullets beginning with '-'. Avoid tables, columns, icons, markdown, and decorative characters. "
            "Make the summary appropriate to the candidate's actual stage, including student status when supplied. "
            "Return only the finished CV text.",
        ),
        ("human", "Candidate answers:\n{answers}"),
    ]
)


def _clean_answers(answers: dict[str, str]) -> dict[str, str]:
    return {
        str(key): re.sub(r"\s+", " ", str(value)).strip()
        for key, value in answers.items()
        if value and str(value).strip()
    }


def cv_readiness(answers: dict[str, str]) -> dict[str, Any]:
    """Require enough defensible information before progress can reach 100%."""
    clean = _clean_answers(answers)
    missing: list[dict[str, str]] = []

    identity = clean.get("identity", "")
    has_name = len(identity.split()) >= 2
    has_contact = bool(re.search(r"[\w.+-]+@[\w.-]+\.\w+|\+?\d[\d\s()-]{7,}", identity))
    if not has_name or not has_contact:
        missing.append({"field": "identity", "message": "Add your full name and at least one email address or phone number."})

    if len(clean.get("goal", "").split()) < 5:
        missing.append({"field": "goal", "message": "Describe the role or internship you want and your current career stage."})

    skills = [item.strip() for item in re.split(r"[,;\n|]", clean.get("skills", "")) if item.strip()]
    if len(skills) < 3:
        missing.append({"field": "skills", "message": "Add at least three skills you can genuinely use."})

    evidence = " ".join(clean.get(key, "") for key in ("experience", "projects", "education"))
    if len(evidence.split()) < 8:
        missing.append({"field": "evidence", "message": "Add education, a project, internship, freelance work, or job experience with useful detail."})

    weights = {"identity": 25, "goal": 20, "skills": 25, "evidence": 30}
    failed = {item["field"] for item in missing}
    score = sum(weight for field, weight in weights.items() if field not in failed)
    return {"ready": not missing, "progress": score, "missing": missing}


def _safe_pdf_text(value: str) -> str:
    # Standard ATS readers handle these ASCII equivalents more consistently.
    return value.replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-").replace("\u2022", "-")


def normalise_cv_text(value: str) -> str:
    """Remove model markdown so both the text and PDF remain ATS-safe."""
    headings = {"contact", "summary", "skills", "experience", "projects", "education", "certifications", "links"}
    output: list[str] = []
    for raw_line in _safe_pdf_text(value).splitlines():
        line = re.sub(r"[*_`]+", "", raw_line).strip()
        line = re.sub(r"^#{1,6}\s*", "", line)
        if not line:
            if output and output[-1] != "":
                output.append("")
            continue
        candidate = re.sub(r"^-\s*", "", line)
        label_match = re.match(r"^([A-Za-z ]+):\s*(.*)$", candidate)
        if label_match and label_match.group(1).strip().casefold() in headings:
            output.append(label_match.group(1).strip().upper())
            if label_match.group(2).strip():
                output.append(label_match.group(2).strip())
            continue
        if candidate.rstrip(":").casefold() in headings:
            output.append(candidate.rstrip(":").upper())
            continue
        if re.match(r"^\s*(?:[-•]\s+|\*\s+)", raw_line):
            output.append(f"- {candidate}")
        else:
            output.append(candidate)
    return "\n".join(output).strip()


def render_cv_pdf(cv_text: str) -> bytes:
    """Render a simple single-column PDF that remains easy for ATS parsers."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    except ImportError as exc:
        raise RuntimeError("PDF support is missing. Install the reportlab package.") from exc

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title="ATS Resume",
        author="Jobflow",
    )
    styles = getSampleStyleSheet()
    name_style = ParagraphStyle(
        "CandidateName",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=21,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#172016"),
        spaceAfter=6,
    )
    heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#28401f"),
        spaceBefore=8,
        spaceAfter=3,
        keepWithNext=True,
    )
    body_style = ParagraphStyle(
        "ATSBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.2,
        leading=12.2,
        textColor=colors.HexColor("#202820"),
        spaceAfter=2.5,
    )
    linked_body_style = ParagraphStyle(
        "ATSBodyKeepWithNext",
        parent=body_style,
        keepWithNext=True,
    )

    story = []
    lines = [line.strip() for line in _safe_pdf_text(cv_text).splitlines()]
    first_content = True
    headings = {"CONTACT", "SUMMARY", "SKILLS", "EXPERIENCE", "PROJECTS", "EDUCATION", "CERTIFICATIONS", "LINKS"}
    for index, line in enumerate(lines):
        if not line:
            story.append(Spacer(1, 2))
            continue
        escaped = (
            line.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        if first_content:
            story.append(Paragraph(escaped, name_style))
            first_content = False
        elif line.rstrip(":").upper() in headings and len(line) < 30:
            story.append(Paragraph(line.rstrip(":").upper(), heading_style))
        else:
            if line.startswith(("- ", "* ")):
                escaped = f"&#8226; {escaped[2:]}"
            next_line = next((candidate for candidate in lines[index + 1:] if candidate), "")
            should_link = (
                not line.startswith(("- ", "* "))
                and bool(next_line)
                and (next_line.startswith(("- ", "* ")) or "|" in next_line)
            )
            story.append(Paragraph(escaped, linked_body_style if should_link else body_style))
    document.build(story)
    return buffer.getvalue()


def build_cv_document(answers: dict[str, str]) -> dict[str, Any]:
    clean = _clean_answers(answers)
    readiness = cv_readiness(clean)
    if not readiness["ready"]:
        error = ValueError("More information is required before an ATS CV can be generated.")
        setattr(error, "readiness", readiness)
        raise error
    import json

    cv_text = normalise_cv_text(invoke_prompt(
        _CV_PROMPT,
        {"answers": json.dumps(clean, ensure_ascii=False, indent=2)},
        timeout=180,
    ))
    pdf_bytes = render_cv_pdf(cv_text)
    document_id = store_cv(cv_text, pdf_bytes, source_name="jobflow-generated-cv.pdf", answers=clean)
    return {
        "cv_text": cv_text,
        "document_id": document_id,
        "pdf_url": f"/api/documents/{document_id}.pdf",
        "readiness": readiness,
    }


def build_cv(answers: dict[str, str]) -> str:
    """Backward-compatible text-only helper."""
    return str(build_cv_document(answers)["cv_text"])
