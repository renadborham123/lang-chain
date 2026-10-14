from __future__ import annotations

import json

import cv_insights


def _analysis_payload() -> dict:
    ids = {
        "experience_years": ("Experience", "About 2 years", "derived", ["Jan 2023 - Present"]),
        "career_stage": ("Career stage", "Early career", "derived", ["Software Engineer"]),
        "skills": ("Skills", ["Python", "FastAPI"], "explicit", ["Python, FastAPI"]),
        "domains": ("Domains", ["Backend development"], "derived", ["Built REST APIs"]),
        "education": ("Education", "BSc Computer Science", "explicit", ["BSc Computer Science"]),
        "location": ("Location", "Cairo, Egypt", "explicit", ["Cairo, Egypt"]),
        "recommended_roles": ("Recommended roles", ["Junior Backend Engineer"], "derived", ["Software Engineer"]),
        "opportunity_path": ("Opportunity path", "Full-time job", "derived", ["Software Engineer"]),
    }
    return {
        "summary": "An early-career backend engineer.",
        "insights": [
            {
                "id": key,
                "label": label,
                "value": value,
                "basis": basis,
                "confidence": .86,
                "evidence_quotes": quotes,
                "explanation": "Grounded in the supplied CV.",
            }
            for key, (label, value, basis, quotes) in ids.items()
        ],
        "recommendation": {
            "path": "job",
            "level": "Junior",
            "role_titles": ["Junior Backend Engineer"],
            "reason": "The CV shows applied backend work.",
            "confidence": .82,
        },
    }


def test_cv_analysis_separates_explicit_facts_from_derived_assessments(monkeypatch):
    cv_text = "Cairo, Egypt\nBSc Computer Science\nPython, FastAPI\nSoftware Engineer\nJan 2023 - Present\nBuilt REST APIs"
    monkeypatch.setattr(cv_insights.runtime_models, "public", lambda: {"model": "fixture-model"})
    monkeypatch.setattr(cv_insights, "invoke_prompt", lambda *_args, **_kwargs: json.dumps(_analysis_payload()))

    result = cv_insights.analyze_cv(cv_text, "en")
    by_id = {item["id"]: item for item in result["insights"]}

    assert by_id["location"]["basis"] == "explicit"
    assert by_id["location"]["evidence_quotes"] == ["Cairo, Egypt"]
    assert by_id["experience_years"]["basis"] == "derived"
    assert result["recommendation"]["basis"] == "derived"
    assert result["review_status"] == "pending"


def test_arabic_review_repairs_mixed_language_model_output(monkeypatch):
    cv_text = "Cairo, Egypt\nBSc Computer Science\nPython, FastAPI\nSoftware Engineer\nJan 2023 - Present\nBuilt REST APIs"
    arabic = _analysis_payload()
    arabic["summary"] = "مهندس برمجيات في بداية مساره المهني."
    for index, item in enumerate(arabic["insights"], start=1):
        item["label"] = f"المعلومة {index}"
        item["explanation"] = "النتيجة مبنية على النص الموجود في السيرة."
    arabic["recommendation"]["level"] = "مبتدئ"
    arabic["recommendation"]["reason"] = "السيرة تعرض خبرة عملية في تطوير البرمجيات الخلفية."
    responses = iter([json.dumps(_analysis_payload()), json.dumps(arabic, ensure_ascii=False)])
    calls = []
    monkeypatch.setattr(cv_insights.runtime_models, "public", lambda: {"model": "fixture-model"})
    monkeypatch.setattr(cv_insights, "invoke_prompt", lambda *_args, **_kwargs: calls.append(1) or next(responses))

    result = cv_insights.analyze_cv(cv_text, "ar")

    assert len(calls) == 2
    assert result["language"] == "ar"
    assert all(cv_insights._has_arabic(item["label"]) for item in result["insights"])
    assert all(cv_insights._has_arabic(item["explanation"]) for item in result["insights"])


def test_claim_is_not_accepted_without_specific_evidence(monkeypatch):
    monkeypatch.setattr(cv_insights.runtime_models, "public", lambda: {"model": "fixture-model"})
    monkeypatch.setattr(
        cv_insights,
        "invoke_prompt",
        lambda *_args, **_kwargs: json.dumps({
            "status": "accepted_as_claim",
            "message": "Updated.",
            "follow_up_question": "",
            "evidence_received": [],
            "updated_value": "4 years",
        }),
    )

    result = cv_insights.discuss_insight(
        cv_text="Jan 2023 - Present",
        insight={"id": "experience_years", "value": "3 years", "basis": "derived"},
        requested_value="4 years",
        message="Make it four.",
        history=[],
        locale="en",
    )

    assert result["status"] == "needs_evidence"
    assert result["verified_for_cv"] is False
