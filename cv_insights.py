"""Strict, evidence-linked CV understanding and review discussions."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.prompts import ChatPromptTemplate

from model_provider import ModelProviderError, invoke_prompt, runtime_models


REQUIRED_INSIGHT_IDS = (
    "experience_years",
    "career_stage",
    "skills",
    "domains",
    "education",
    "location",
    "recommended_roles",
    "opportunity_path",
)

_ANALYSIS_SCHEMA = """{
  "summary": "user-facing text",
  "insights": [
    {"id": "experience_years", "label": "user-facing text", "value": "user-facing text or array", "basis": "explicit or derived", "confidence": 0.0, "evidence_quotes": ["exact CV quote"], "explanation": "user-facing text"},
    {"id": "career_stage", "label": "...", "value": "...", "basis": "derived", "confidence": 0.0, "evidence_quotes": [], "explanation": "..."},
    {"id": "skills", "label": "...", "value": [], "basis": "explicit or derived", "confidence": 0.0, "evidence_quotes": [], "explanation": "..."},
    {"id": "domains", "label": "...", "value": [], "basis": "derived", "confidence": 0.0, "evidence_quotes": [], "explanation": "..."},
    {"id": "education", "label": "...", "value": "...", "basis": "explicit or derived", "confidence": 0.0, "evidence_quotes": [], "explanation": "..."},
    {"id": "location", "label": "...", "value": "...", "basis": "explicit or derived", "confidence": 0.0, "evidence_quotes": [], "explanation": "..."},
    {"id": "recommended_roles", "label": "...", "value": [], "basis": "derived", "confidence": 0.0, "evidence_quotes": [], "explanation": "..."},
    {"id": "opportunity_path", "label": "...", "value": "...", "basis": "derived", "confidence": 0.0, "evidence_quotes": [], "explanation": "..."}
  ],
  "recommendation": {"path": "internship or job or either", "level": "user-facing text", "role_titles": ["user-facing text"], "reason": "user-facing text", "confidence": 0.0}
}"""


def _json_object(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        raise ValueError("The model did not return a JSON object.")
    value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("The model response must be an object.")
    return value


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _quote_is_present(quote: str, cv_text: str) -> bool:
    clean_quote = _normalise(quote).strip("… .,:;\"'“”")
    return len(clean_quote) >= 3 and clean_quote in _normalise(cv_text)


def _has_arabic(value: object) -> bool:
    return bool(re.search(r"[\u0600-\u06ff]", str(value or "")))


def _clean_insight(item: dict[str, Any], cv_text: str) -> dict[str, Any]:
    insight_id = str(item.get("id") or "").strip()
    if insight_id not in REQUIRED_INSIGHT_IDS:
        raise ValueError(f"Unexpected CV insight: {insight_id}")
    label = " ".join(str(item.get("label") or "").split())
    raw_value = item.get("value")
    if isinstance(raw_value, list):
        value: str | list[str] = list(dict.fromkeys(" ".join(str(part).split()) for part in raw_value if str(part).strip()))[:30]
    else:
        value = " ".join(str(raw_value or "").split())
    if not label or not value:
        raise ValueError(f"Incomplete CV insight: {insight_id}")
    quotes = [" ".join(str(quote).split()) for quote in item.get("evidence_quotes") or [] if str(quote).strip()][:5]
    valid_quotes = [quote for quote in quotes if _quote_is_present(quote, cv_text)]
    requested_basis = str(item.get("basis") or "derived")
    basis = "explicit" if requested_basis == "explicit" and valid_quotes else "derived"
    confidence = max(0.0, min(1.0, float(item.get("confidence") or 0)))
    return {
        "id": insight_id,
        "label": label,
        "value": value,
        "basis": basis,
        "confidence": confidence,
        "evidence_quotes": valid_quotes,
        "explanation": " ".join(str(item.get("explanation") or "").split()),
        "review_state": "original",
    }


def _review_from_output(output: dict[str, Any], cv_text: str, language: str) -> dict[str, Any]:
    items = output.get("insights")
    if not isinstance(items, list):
        raise ValueError("The model did not return CV insights.")
    cleaned = [_clean_insight(item, cv_text) for item in items if isinstance(item, dict)]
    by_id = {item["id"]: item for item in cleaned}
    if any(insight_id not in by_id for insight_id in REQUIRED_INSIGHT_IDS):
        raise ValueError("The model omitted a required CV insight.")
    recommendation = output.get("recommendation") or {}
    if not isinstance(recommendation, dict):
        raise ValueError("The model returned an invalid recommendation.")
    path = str(recommendation.get("path") or "").strip()
    if path not in {"internship", "job", "either"}:
        raise ValueError("The model returned an invalid opportunity path.")
    raw_roles = recommendation.get("role_titles") or []
    if not isinstance(raw_roles, list):
        raise ValueError("The model returned invalid role titles.")
    roles = [" ".join(str(role).split()) for role in raw_roles if str(role).strip()][:8]
    if not roles:
        raise ValueError("The model did not recommend any role titles.")
    summary = " ".join(str(output.get("summary") or "").split())
    level = " ".join(str(recommendation.get("level") or "").split())
    reason = " ".join(str(recommendation.get("reason") or "").split())
    localized_text = [summary, level, reason]
    localized_text.extend(item["label"] for item in cleaned)
    localized_text.extend(item["explanation"] for item in cleaned)
    if not all(localized_text):
        raise ValueError("The model omitted user-facing CV review text.")
    if language == "ar" and not all(_has_arabic(value) for value in localized_text):
        raise ValueError("The model did not localize the full CV review in Arabic.")
    if language == "en" and any(_has_arabic(value) for value in localized_text):
        raise ValueError("The model did not localize the full CV review in English.")
    return {
        "summary": summary,
        "insights": [by_id[insight_id] for insight_id in REQUIRED_INSIGHT_IDS],
        "recommendation": {
            "path": path,
            "level": level,
            "role_titles": roles,
            "reason": reason,
            "confidence": max(0.0, min(1.0, float(recommendation.get("confidence") or 0))),
            "basis": "derived",
        },
        "language": language,
        "review_status": "pending",
        "generated_by": "llm",
        "source_note": (
            "كل حقيقة مباشرة مرتبطة بنص موجود فعلًا في السيرة. التوصية تقييم وليست حقيقة." if language == "ar"
            else "Every direct fact is linked to text actually present in the CV. The recommendation is an assessment, not a fact."
        ),
    }


def analyze_cv(cv_text: str, locale: str = "en") -> dict[str, Any]:
    """Read a CV once and return structured insights with verified evidence links."""
    language = "ar" if locale == "ar" else "en"
    if not cv_text.strip():
        raise ValueError("The CV has no readable text.")
    if not str(runtime_models.public().get("model") or "").strip():
        raise ModelProviderError("Choose an AI model before reviewing this CV.")
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            "You are a strict CV evidence auditor. Read the supplied CV and return JSON only. "
            "Never invent dates, skills, seniority, achievements, or experience. Distinguish explicit facts from derived assessments. "
            "Use basis=explicit only when the value is directly written in the CV and include exact short evidence_quotes copied from it. "
            "Use basis=derived when calculating duration, combining several lines, classifying a domain, deciding career stage, or recommending a path. "
            "For derived items, explain the reasoning and include the CV lines used when possible. "
            "Return: summary; insights with exactly these ids: experience_years, career_stage, skills, domains, education, location, recommended_roles, opportunity_path; "
            "and recommendation containing path (internship, job, or either), level, role_titles, reason, confidence. "
            "Experience years must not double-count overlapping roles. If dates are unclear, say that the duration is unclear instead of guessing. "
            "Recommendation is always an assessment, never an explicit fact. "
            "Write every user-facing label, value, explanation, summary, and reason in simple friendly Arabic when language=ar, otherwise English. "
            "CRITICAL: JSON property names, insight ids, basis values, path values, and booleans/numbers must stay in English ASCII exactly as shown. "
            "Never translate a JSON key or enum. insights must be an array, not an object. Follow this exact shape:\n{schema}"
        ),
        ("human", "Language: {language}\nCV text:\n{cv_text}"),
    ])
    raw = invoke_prompt(prompt, {"language": language, "cv_text": cv_text[:24000], "schema": _ANALYSIS_SCHEMA}, json_mode=True, timeout=75)
    output = _json_object(raw)
    try:
        return _review_from_output(output, cv_text, language)
    except (TypeError, ValueError):
        repair_prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "Repair the prior CV-audit response into the exact JSON schema below. Return JSON only. "
                "Preserve its evidence-based meaning; do not add facts. User-facing text follows the requested language. "
                "Translate every summary, label, value description, explanation, level, and reason into that language. "
                "Technical skill names and proper role titles may stay in their conventional English form. "
                "All JSON keys, ids, enum values, and numeric values must remain English ASCII and must not be translated. "
                "insights must be an array with exactly eight items.\n{schema}",
            ),
            (
                "human",
                "Language: {language}\nOriginal CV:\n{cv_text}\n\nPrior response to repair:\n{raw}",
            ),
        ])
        repaired_raw = invoke_prompt(
            repair_prompt,
            {"language": language, "cv_text": cv_text[:24000], "raw": raw[:30000], "schema": _ANALYSIS_SCHEMA},
            json_mode=True,
            timeout=75,
        )
        return _review_from_output(_json_object(repaired_raw), cv_text, language)


def discuss_insight(
    *,
    cv_text: str,
    insight: dict[str, Any],
    requested_value: str,
    message: str,
    history: list[dict[str, str]],
    locale: str,
) -> dict[str, Any]:
    """Challenge a proposed edit and request evidence instead of silently overwriting the CV."""
    language = "ar" if locale == "ar" else "en"
    if not str(runtime_models.public().get("model") or "").strip():
        raise ModelProviderError("Choose an AI model before discussing this CV insight.")
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            "You are a strict CV fact reviewer. The user wants to change one CV insight. "
            "Do not agree just because the user requested a different value. Compare the request with the original CV and conversation. "
            "If evidence is missing, return status=needs_evidence and ask one precise follow-up question. "
            "For experience duration, require the missing role or project, organisation, start date, end date, and whether it overlaps another role. "
            "For skills, require a project, job, course, or inspectable work showing use. For education or location, require the exact corrected fact. "
            "When the user supplies specific evidence, return status=accepted_as_claim. This remains a user claim, not CV-verified evidence. "
            "Return JSON: status (needs_evidence, accepted_as_claim, or rejected), message, follow_up_question, evidence_received (array), and updated_value. "
            "Use simple friendly Arabic when language=ar, otherwise English. "
            "Keep every JSON property name and status enum in English ASCII exactly as specified; translate only the user-facing text values."
        ),
        (
            "human",
            "Language: {language}\nOriginal insight: {insight}\nRequested value: {requested_value}\nLatest message: {message}\nConversation: {history}\nOriginal CV:\n{cv_text}",
        ),
    ])
    raw = invoke_prompt(
        prompt,
        {
            "language": language,
            "insight": json.dumps(insight, ensure_ascii=False),
            "requested_value": requested_value[:1000],
            "message": message[:3000],
            "history": json.dumps(history[-10:], ensure_ascii=False),
            "cv_text": cv_text[:18000],
        },
        json_mode=True,
        timeout=60,
    )
    output = _json_object(raw)
    status = str(output.get("status") or "needs_evidence")
    if status not in {"needs_evidence", "accepted_as_claim", "rejected"}:
        status = "needs_evidence"
    evidence = [" ".join(str(item).split()) for item in output.get("evidence_received") or [] if str(item).strip()][:10]
    if status == "accepted_as_claim" and not evidence:
        status = "needs_evidence"
    return {
        "status": status,
        "message": " ".join(str(output.get("message") or "").split()),
        "follow_up_question": " ".join(str(output.get("follow_up_question") or "").split()),
        "evidence_received": evidence,
        "updated_value": output.get("updated_value") or requested_value,
        "basis": "user_claim" if status == "accepted_as_claim" else insight.get("basis", "derived"),
        "verified_for_cv": False,
    }
