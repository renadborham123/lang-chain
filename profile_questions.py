"""LLM-first, evidence-bound questions for completing a career profile."""

from __future__ import annotations

import json
import re
from hashlib import sha256
from threading import RLock
from typing import Any

from langchain_core.prompts import ChatPromptTemplate

from model_provider import ModelProviderError, invoke_prompt, runtime_models


_CACHE: dict[str, tuple[list[dict[str, Any]], str]] = {}
_CACHE_LOCK = RLock()


def _json_object(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        raise ValueError("Model did not return a JSON object.")
    value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("Model response must be an object.")
    return value


def _fallback_question(candidate: dict[str, Any], locale: str) -> dict[str, Any]:
    inferred = str(candidate.get("existing_value") or "").strip()
    if inferred:
        question = (
            f"لقيت في سيرتك إن {candidate['label']} هو «{inferred}». هل ده صحيح؟"
            if locale == "ar"
            else f"Your CV states that your {str(candidate['label']).lower()} is “{inferred}”. Is that correct?"
        )
        kind = "confirm"
    else:
        question = str(candidate["fallback_question"])
        kind = "missing"
    return {
        "memory_key": candidate["memory_key"],
        "kind": kind,
        "inferred_value": inferred,
        "question": question,
        "reason": (
            "محتاجين تأكيد المعلومة قبل ما نحفظها." if locale == "ar" and inferred
            else "المعلومة دي مش واضحة في السيرة." if locale == "ar"
            else "This needs your confirmation before it is saved." if inferred
            else "This detail is not clear in the CV."
        ),
        "generated_by": "fallback",
        "basis": "explicit" if inferred else "missing",
    }


def _language_matches(question: str, locale: str) -> bool:
    has_arabic = bool(re.search(r"[\u0600-\u06ff]", question))
    return has_arabic if locale == "ar" else not has_arabic


def generate_profile_questions(
    *,
    cv_text: str,
    candidates: list[dict[str, Any]],
    locale: str,
) -> tuple[list[dict[str, Any]], str]:
    """Generate one grounded question per candidate, with a safe localized fallback."""
    locale = "ar" if locale == "ar" else "en"
    fallbacks = {item["memory_key"]: _fallback_question(item, locale) for item in candidates}
    if not candidates:
        return [], "none"
    if not cv_text.strip() or not str(runtime_models.public().get("model") or "").strip():
        return list(fallbacks.values()), "fallback"

    compact_candidates = [
        {
            "memory_key": item["memory_key"],
            "label": item["label"],
            "existing_unconfirmed_value": item.get("existing_value") or "",
            "input_type": item.get("input_type") or "text",
            "options": item.get("options") or [],
            "evidence_basis": "explicit" if item.get("existing_value") else "unknown",
        }
        for item in candidates
    ]
    cache_payload = json.dumps(
        {"cv": cv_text, "candidates": compact_candidates, "locale": locale},
        ensure_ascii=False,
        sort_keys=True,
    )
    cache_key = sha256(cache_payload.encode("utf-8")).hexdigest()
    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
    if cached:
        return cached

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            "You create career-profile questions using only the supplied CV evidence. "
            "Return JSON with a questions array and exactly one item for every supplied memory_key. "
            "Each item must contain memory_key, kind (confirm or missing), basis (explicit, derived, or missing), inferred_value, question, and reason. "
            "If an existing_unconfirmed_value is supplied, it was directly extracted from the CV: use basis=explicit, say it was found or written in the CV, ask the user to confirm it, and copy it exactly into inferred_value. Never call it an inference. "
            "Otherwise, infer a value only when it is directly and unambiguously stated in the CV; then ask whether that understanding is correct. "
            "If you derive a conclusion by combining evidence, use basis=derived. If the detail is absent or ambiguous, use kind=missing, basis=missing, leave inferred_value empty, and ask one short direct question. "
            "Never infer work authorization, visa sponsorship, notice period, or work preference unless the CV states it explicitly. "
            "Do not invent facts. When language is ar, write friendly, simple everyday Arabic that is easy to understand, not formal or ornate Arabic. "
            "When language is en, write natural concise English. Every question and reason must use only the requested language."
        ),
        (
            "human",
            "Language: {language}\nFields to review: {candidates}\nCV:\n{cv_text}",
        ),
    ])
    try:
        raw = invoke_prompt(
            prompt,
            {
                "language": locale,
                "candidates": json.dumps(compact_candidates, ensure_ascii=False),
                "cv_text": cv_text[:16000],
            },
            json_mode=True,
            timeout=35,
        )
        output = _json_object(raw)
        generated: dict[str, dict[str, Any]] = {}
        allowed = set(fallbacks)
        for item in output.get("questions") or []:
            if not isinstance(item, dict):
                continue
            key = str(item.get("memory_key") or "")
            question = " ".join(str(item.get("question") or "").split())
            kind = str(item.get("kind") or "missing")
            basis = str(item.get("basis") or "missing")
            inferred = " ".join(str(item.get("inferred_value") or "").split())
            if key not in allowed or kind not in {"confirm", "missing"} or basis not in {"explicit", "derived", "missing"} or not question or not _language_matches(question, locale):
                continue
            if kind == "confirm" and not inferred:
                continue
            candidate = next(candidate for candidate in candidates if candidate["memory_key"] == key)
            if candidate.get("existing_value"):
                basis = "explicit"
            generated[key] = {
                "memory_key": key,
                "kind": kind,
                "inferred_value": inferred if kind == "confirm" else "",
                "question": question,
                "reason": " ".join(str(item.get("reason") or "").split()),
                "generated_by": "llm",
                "basis": basis,
            }
        questions = [generated.get(item["memory_key"], fallbacks[item["memory_key"]]) for item in candidates]
        source = "llm" if any(item["generated_by"] == "llm" for item in questions) else "fallback"
    except (ModelProviderError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        questions, source = list(fallbacks.values()), "fallback"

    with _CACHE_LOCK:
        if len(_CACHE) >= 128:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[cache_key] = (questions, source)
    return questions, source
