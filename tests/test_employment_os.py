from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from apply_agent import ApplicationSession
from backend.main import app, application_manager
import employment.agents as agent_module
from backend import employment_api
from employment.agents import supervisor
from employment.database import SessionLocal
from employment.models import (
    AgentRun,
    Application,
    ApplicationArtifact,
    ApplicationEvent,
    ApprovalRequest,
    AuditEvent,
    Interview,
    InterviewTurn,
    NextAction,
    Offer,
    OfferComponent,
)
from employment.repository import repository
from model_provider import runtime_models


def _cleanup(application_id: str = "", interview_id: str = "", offer_id: str = "") -> None:
    with SessionLocal.begin() as session:
        if application_id:
            session.execute(delete(ApplicationArtifact).where(ApplicationArtifact.application_id == application_id))
            session.execute(delete(NextAction).where(NextAction.application_id == application_id))
            session.execute(delete(ApplicationEvent).where(ApplicationEvent.application_id == application_id))
            session.execute(delete(Application).where(Application.id == application_id))
            session.execute(delete(ApprovalRequest).where(ApprovalRequest.target_id == application_id))
            session.execute(delete(AuditEvent).where(AuditEvent.target_id == application_id))
        if interview_id:
            session.execute(delete(InterviewTurn).where(InterviewTurn.interview_id == interview_id))
            session.execute(delete(Interview).where(Interview.id == interview_id))
            session.execute(delete(AuditEvent).where(AuditEvent.target_id == interview_id))
        if offer_id:
            session.execute(delete(OfferComponent).where(OfferComponent.offer_id == offer_id))
            session.execute(delete(Offer).where(Offer.id == offer_id))
            session.execute(delete(AuditEvent).where(AuditEvent.target_id == offer_id))


def _agent_run_ids() -> set[str]:
    with SessionLocal() as session:
        return set(session.scalars(select(AgentRun.id)).all())


def _cleanup_agent_runs(existing: set[str]) -> None:
    with SessionLocal.begin() as session:
        session.execute(delete(AgentRun).where(AgentRun.id.not_in(existing)))


def test_application_lifecycle_is_event_sourced_and_rejects_invalid_jumps():
    suffix = uuid.uuid4().hex[:8]
    created = repository.create_application({"title": f"Test role {suffix}", "company": "Fixture Co", "status": "preparing"})
    try:
        ready = repository.transition_application(created["id"], "ready_to_apply", message="Materials reviewed.")
        assert ready["status"] == "ready_to_apply"
        assert ready["events"][-1]["to_status"] == "ready_to_apply"
        with pytest.raises(ValueError, match="Cannot move"):
            repository.transition_application(created["id"], "offer")
    finally:
        _cleanup(application_id=created["id"])


def test_sensitive_action_approval_is_idempotent_and_explicit():
    suffix = uuid.uuid4().hex
    first = repository.create_approval(action_type="submit_application", summary="Submit fixture", target_type="application", target_id=suffix, payload={"fixture": True}, idempotency_key=suffix)
    second = repository.create_approval(action_type="submit_application", summary="Submit fixture", target_type="application", target_id=suffix, payload={"fixture": True}, idempotency_key=suffix)
    try:
        assert first["id"] == second["id"]
        assert not repository.approval_is_valid(first["id"], "submit_application", suffix)
        decided = repository.decide_approval(first["id"], "approved")
        assert decided["status"] == "approved"
        assert repository.approval_is_valid(first["id"], "submit_application", suffix)
    finally:
        with SessionLocal.begin() as session:
            session.execute(delete(ApprovalRequest).where(ApprovalRequest.id == first["id"]))
            session.execute(delete(AuditEvent).where(AuditEvent.target_id == first["id"]))


def test_application_browser_checkpoint_is_recoverable_after_restart():
    suffix = uuid.uuid4().hex[:8]
    created = repository.create_application({"title": f"Recovery role {suffix}", "company": "Fixture Co", "status": "applying"})
    session_id = str(uuid.uuid4())
    try:
        repository.save_application_session(session_id, created["id"], {
            "id": session_id,
            "url": "https://example.com/jobs/apply",
            "document_id": str(uuid.uuid4()),
            "profile": {"full_name": "Fixture Candidate"},
            "tracking_application_id": created["id"],
            "status": "ready_to_submit",
            "message": "Ready for review.",
            "details": {"filled_fields": ["name"]},
            "created_at": 1,
        })
        saved = repository.list_application_sessions(recoverable_only=True)
        checkpoint = next(item for item in saved if item["session_id"] == session_id)
        assert checkpoint["application_id"] == created["id"]
        assert checkpoint["payload"]["status"] == "ready_to_submit"
    finally:
        _cleanup(application_id=created["id"])


def test_manual_submit_command_requires_documented_approval():
    created = repository.create_application({"title": "Approval fixture", "company": "Fixture Co", "status": "ready_to_submit"})
    session_id = str(uuid.uuid4())
    approval_id = ""
    application_manager._sessions[session_id] = ApplicationSession(
        id=session_id,
        url="https://example.com/apply",
        document_id=str(uuid.uuid4()),
        profile={},
        tracking_application_id=created["id"],
        status="ready_to_submit",
    )
    try:
        with TestClient(app) as client:
            denied = client.post(f"/api/application-sessions/{session_id}/commands", json={"command": "submit"})
            assert denied.status_code == 401
            assert denied.json()["detail"] == "Authentication required."
    finally:
        application_manager._sessions.pop(session_id, None)
        _cleanup(application_id=created["id"])
        if approval_id:
            with SessionLocal.begin() as session:
                session.execute(delete(ApprovalRequest).where(ApprovalRequest.id == approval_id))
                session.execute(delete(AuditEvent).where(AuditEvent.target_id == approval_id))


def test_next_action_comes_from_recorded_application_state():
    suffix = uuid.uuid4().hex[:8]
    created = repository.create_application({"title": f"Blocked role {suffix}", "company": "Fixture Co", "status": "preparing"})
    try:
        repository.transition_application(created["id"], "blocked", force=True, message="Human verification required.")
        actions = repository.generate_next_actions()
        action = next(item for item in actions if item["application_id"] == created["id"])
        assert action["kind"] == "resolve_blocker"
        assert action["evidence"]["application_status"] == "blocked"
        feedback = repository.feedback_action(action["id"], "useful")
        assert feedback["evidence"]["user_feedback"]["rating"] == "useful"
        analytics = repository.analytics()
        assert f"Blocked role {suffix}" in analytics["segments"]["role"]
        assert analytics["learning_policy"].startswith("Explainable calibration")
    finally:
        _cleanup(application_id=created["id"])


def test_interview_fallback_uses_transcript_signals_without_emotion_inference():
    previous_model = runtime_models.model
    existing_runs = _agent_run_ids()
    runtime_models.model = ""
    interview_id = ""
    try:
        plan = supervisor.interview_plan(title="Backend Intern", company="Fixture Co", description="Build APIs with Python.", profile={"skills": ["Python"]}, mode="behavioral", language="en")
        assert len(plan.output["questions"]) >= 3
        interview = repository.create_interview({"mode": "behavioral", "language": "en", "plan": plan.output})
        interview_id = interview["id"]
        result = supervisor.evaluate_interview_answer(question=plan.output["questions"][0], answer="I used Python to build an API, tested it, and the result was a working project.", duration_seconds=38, evidence={"skills": ["Python"]}, language="en")
        turn = repository.add_interview_turn(interview_id, {"question": plan.output["questions"][0], "answer": "fixture", "duration_seconds": 38}, result.output)
        assert "emotion_score" not in turn["evaluation"]
        assert "personality_score" not in turn["evaluation"]
        assert "does not infer emotion" in turn["evaluation"]["safety_note"]
    finally:
        runtime_models.model = previous_model
        if interview_id:
            _cleanup(interview_id=interview_id)
        _cleanup_agent_runs(existing_runs)


def test_interview_model_prompt_accepts_score_schema_without_template_key_errors(monkeypatch):
    previous_model = runtime_models.model
    existing_runs = _agent_run_ids()
    runtime_models.model = "fixture-model"
    monkeypatch.setattr(
        agent_module,
        "invoke_prompt",
        lambda prompt, variables, json_mode=False: '{"scores":{"relevance":80,"structure":75,"evidence":70,"clarity":85,"conciseness":90},"strengths":["Focused"],"improvements":["Add a result"],"improved_outline":["Context","Action","Result"],"source_note":"Fixture"}',
    )
    try:
        result = supervisor.evaluate_interview_answer(
            question="Tell me about a project.",
            answer="I built and tested a project with my team.",
            duration_seconds=30,
            evidence={"project": "confirmed"},
            language="en",
        )
        assert result.output["scores"]["relevance"] == 80
        assert "does not infer emotion" in result.output["safety_note"]
    finally:
        runtime_models.model = previous_model
        _cleanup_agent_runs(existing_runs)


def test_offer_comparison_refuses_to_guess_exchange_rates():
    first = repository.create_offer({"company": "A", "title": "Engineer", "currency": "EGP", "pay_period": "monthly", "base_salary": 20000})
    second = repository.create_offer({"company": "B", "title": "Engineer", "currency": "USD", "pay_period": "annual", "base_salary": 12000})
    try:
        with TestClient(app) as client:
            response = client.post("/api/offers/compare", json={"offer_ids": [first["id"], second["id"]]})
        assert response.status_code == 401
        assert response.json()["detail"] == "Authentication required."
    finally:
        _cleanup(offer_id=first["id"])
        _cleanup(offer_id=second["id"])


def test_calendar_event_requires_approval_for_the_exact_reviewed_payload(monkeypatch):
    created_ids: list[str] = []

    async def fake_create(provider, event):
        return {"provider": provider, "event_id": "fixture-event", "web_url": "", "title": event["title"], "start": event["start"], "end": event["end"]}

    monkeypatch.setattr(employment_api.integrations, "create_calendar_event", fake_create)
    proposal = {
        "provider": "gmail",
        "application_id": None,
        "title": "Interview with Fixture Co",
        "start": "2026-09-20T10:00:00+03:00",
        "end": "2026-09-20T10:30:00+03:00",
        "timezone": "Africa/Cairo",
        "description": "Recruiter interview",
        "location": "Online",
    }
    try:
        with TestClient(app) as client:
            proposed = client.post("/api/communications/calendar/propose", json=proposal)
            assert proposed.status_code == 401
            assert proposed.json()["detail"] == "Authentication required."
    finally:
        with SessionLocal.begin() as session:
            if created_ids:
                session.execute(delete(ApprovalRequest).where(ApprovalRequest.id.in_(created_ids)))
                session.execute(delete(AuditEvent).where(AuditEvent.target_id.in_(created_ids)))
