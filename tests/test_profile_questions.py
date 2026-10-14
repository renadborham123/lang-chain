from __future__ import annotations

import json

from backend import employment_api
import profile_questions


def _candidate(**overrides):
    value = {
        "memory_key": "target_role",
        "label": "الوظيفة المستهدفة",
        "fallback_question": "ما الوظيفة التي تستهدفها الآن؟",
        "input_type": "text",
        "options": [],
        "contexts": ["profile", "search"],
        "existing_value": "",
    }
    value.update(overrides)
    return value


def test_llm_generates_simple_arabic_question_from_cv(monkeypatch):
    monkeypatch.setattr(profile_questions.runtime_models, "public", lambda: {"model": "fixture-model"})
    monkeypatch.setattr(
        profile_questions,
        "invoke_prompt",
        lambda *_args, **_kwargs: json.dumps(
            {
                "questions": [
                    {
                        "memory_key": "target_role",
                        "kind": "confirm",
                        "basis": "derived",
                        "inferred_value": "مهندس برمجيات",
                        "question": "فهمت من سيرتك إنك مستهدف شغل مهندس برمجيات، صح؟",
                        "reason": "المسمى ظاهر في خبراتك.",
                    }
                ]
            },
            ensure_ascii=False,
        ),
    )

    questions, source = profile_questions.generate_profile_questions(
        cv_text="Ahmed Ali\nSoftware Engineer\nPython",
        candidates=[_candidate()],
        locale="ar",
    )

    assert source == "llm"
    assert questions[0]["generated_by"] == "llm"
    assert questions[0]["kind"] == "confirm"
    assert questions[0]["inferred_value"] == "مهندس برمجيات"
    assert "صح" in questions[0]["question"]


def test_unconfirmed_cv_fact_is_asked_for_confirmation(monkeypatch):
    monkeypatch.setattr(
        employment_api.repository,
        "profile",
        lambda _user_id: {
            "locale": "en",
            "profile": {"name": "Ahmed Ali", "phone": "+20 100 000 0000"},
            "facts": [
                {
                    "fact_key": "phone",
                    "value": "+20 100 000 0000",
                    "source": "cv",
                    "confirmed": False,
                }
            ],
        },
    )
    monkeypatch.setattr(employment_api, "get_active_document", lambda _user_id: {"document_id": "fixture"})
    monkeypatch.setattr(employment_api, "get_cv_text", lambda *_args: "Ahmed Ali\n+20 100 000 0000")

    def fake_generate(*, candidates, **_kwargs):
        return [
            {
                "memory_key": item["memory_key"],
                "kind": "confirm" if item["existing_value"] else "missing",
                "inferred_value": item["existing_value"],
                "question": "Is this correct?" if item["existing_value"] else item["fallback_question"],
                "reason": "CV evidence",
                "generated_by": "llm",
            }
            for item in candidates
        ], "llm"

    monkeypatch.setattr(employment_api, "generate_profile_questions", fake_generate)
    result = employment_api._profile_completeness("fixture-user", "profile", "en")

    phone = next(item for item in result["missing"] if item["memory_key"] == "phone")
    assert phone["kind"] == "confirm"
    assert phone["inferred_value"] == "+20 100 000 0000"
    assert phone["basis"] == "explicit"
    assert "phone" not in result["known"]
    assert result["known"]["full_name"]["value"] == "Ahmed Ali"
    assert result["cv_reviewed"] is True
    assert result["analysis_source"] == "llm"
