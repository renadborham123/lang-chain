from pathlib import Path

from fastapi.testclient import TestClient

import career_agent
from application_memory import ApplicationAnswerStore
from backend.main import app
from career_memory import CareerMemoryStore
from cv_enrichment import _append_section_facts


def test_acceptance_plan_uses_current_jobs_and_asks_one_high_impact_question(monkeypatch, tmp_path: Path):
    store = CareerMemoryStore(tmp_path / "career.json")
    monkeypatch.setattr(career_agent, "career_memory", store)
    monkeypatch.setattr(career_agent, "get_cv_text", lambda document_id: "SKILLS\nPython\nPROJECTS\nAPI project")
    monkeypatch.setattr(career_agent, "invoke_prompt", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")))

    result = career_agent.build_acceptance_plan(
        {
            "document_id": "doc-1",
            "location": "Cairo",
            "profile": {"primary_skills": ["Python"], "years_experience": 0, "is_student": True},
            "search": {"discovered": 12, "matched": 4},
            "jobs": [
                {
                    "id": "one",
                    "title": "Backend Intern",
                    "description": "Use Docker to ship Python APIs. Working English is required.",
                    "location": "Cairo",
                    "status": "ready",
                },
                {
                    "id": "two",
                    "title": "Junior Platform Engineer",
                    "description": "You will build Docker images and maintain Linux services.",
                    "location": "Giza · On-site",
                    "status": "review",
                },
            ],
        }
    )

    assert result["activities"][0]["label"] == "Found 12 live listings"
    assert result["recommendations"][0]["title"].startswith("Docker")
    assert result["recommendations"][0]["impact_jobs"] == 2
    assert result["recommendations"][0]["evidence"][0]["quote"] in {
        "Use Docker to ship Python APIs.",
        "Junior Platform Engineer.",
    }
    assert result["question"]["memory_key"] == "skill_evidence_docker"
    assert result["question"]["options"][0].startswith("Yes")
    assert result["decision"]["options"][1]["impact_jobs"] == 1
    assert result["decision"]["locations"] == ["Giza"]
    assert "travel time was not guessed" in result["decision"]["reason"]


def test_career_memory_only_exports_confirmed_cv_safe_facts(tmp_path: Path):
    store = CareerMemoryStore(tmp_path / "career.json")
    store.remember(
        "doc",
        "english_proficiency",
        "B2 — upper-intermediate",
        cv_safe=True,
        cv_section="LANGUAGES",
    )
    store.remember(
        "doc",
        "skill_evidence_docker",
        "Yes — in a project",
        kind="skill_evidence",
        subject="Docker",
        cv_safe=True,
        cv_section="SKILLS",
    )
    store.remember(
        "doc",
        "skill_evidence_kubernetes",
        "Learning it now",
        kind="skill_evidence",
        subject="Kubernetes",
        cv_safe=True,
        cv_section="SKILLS",
    )
    store.remember("doc", "commute", "Include Giza", cv_safe=False)

    assert store.cv_facts("doc") == {
        "SKILLS": ["Docker"],
        "LANGUAGES": ["English — B2 — upper-intermediate"],
    }
    assert store.known_skills("doc") == ["Docker"]


def test_salary_tradeoff_uses_saved_expectation_and_published_ranges(monkeypatch, tmp_path: Path):
    answers = ApplicationAnswerStore(tmp_path / "answers.json")
    answers.remember("expected_salary", "EGP 10,000 per month")
    monkeypatch.setattr(career_agent, "application_answers", answers)

    decision = career_agent._salary_decision(
        [
            {"id": "low", "title": "Analyst", "description": "Salary EGP 7,000-8,000 per month."},
            {"id": "high", "title": "Analyst", "description": "Salary EGP 12,000 per month."},
        ]
    )

    assert decision is not None
    assert decision["id"] == "salary_flexibility"
    assert decision["job_ids"] == ["low"]
    assert decision["options"][1]["impact_jobs"] == 1


def test_salary_tradeoff_does_not_compare_different_currencies_or_pay_periods(monkeypatch, tmp_path: Path):
    answers = ApplicationAnswerStore(tmp_path / "answers.json")
    answers.remember("expected_salary", "EGP 10,000 per month")
    monkeypatch.setattr(career_agent, "application_answers", answers)

    decision = career_agent._salary_decision(
        [
            {"id": "annual", "title": "Analyst", "description": "Salary EGP 8,000 per year."},
            {"id": "usd", "title": "Analyst", "description": "Salary USD 8,000 per month."},
            {"id": "unknown", "title": "Analyst", "description": "Salary 8,000 per month."},
        ]
    )

    assert decision is None


def test_cv_enrichment_adds_new_facts_without_rewriting_existing_claims():
    source = "Jane Doe\n\nSKILLS\nPython, SQL\n\nPROJECTS\nInventory API"
    enriched = _append_section_facts(
        source,
        {"SKILLS": ["Docker"], "LANGUAGES": ["English — B2"]},
    )

    assert "Python, SQL\nDocker" in enriched
    assert "PROJECTS\nInventory API" in enriched
    assert enriched.endswith("LANGUAGES\nEnglish - B2")


def test_career_plan_endpoint(monkeypatch):
    monkeypatch.setattr(
        "backend.main.build_acceptance_plan",
        lambda payload: {"message": f"Plan for {len(payload['jobs'])} jobs", "activities": []},
    )
    response = TestClient(app).post(
        "/api/career/plan",
        json={"document_id": "doc", "jobs": [{"id": "one"}], "profile": {}, "search": {}},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required."
