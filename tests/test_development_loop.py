from __future__ import annotations

import uuid

from sqlalchemy import delete, select

from employment.database import SessionLocal
from employment.development import DevelopmentService
from employment.models import (
    AssessmentTurn,
    AuditEvent,
    CareerFact,
    CareerMilestone,
    CVChangeProposal,
    DevelopmentPlan,
    DevelopmentTask,
    LearningOpportunity,
    MarketRequirement,
    ReadinessSnapshot,
    SkillAssessment,
    SkillEvidence,
    TargetRole,
    UserProfile,
)


service = DevelopmentService()


def _user() -> str:
    return f"qualification-test-{uuid.uuid4().hex}"


def _cleanup(user_id: str) -> None:
    with SessionLocal.begin() as session:
        assessment_ids = select(SkillAssessment.id).where(SkillAssessment.user_id == user_id)
        plan_ids = select(DevelopmentPlan.id).where(DevelopmentPlan.user_id == user_id)
        role_ids = select(TargetRole.id).where(TargetRole.user_id == user_id)
        session.execute(delete(AssessmentTurn).where(AssessmentTurn.assessment_id.in_(assessment_ids)))
        session.execute(delete(CVChangeProposal).where(CVChangeProposal.user_id == user_id))
        session.execute(delete(SkillAssessment).where(SkillAssessment.user_id == user_id))
        session.execute(delete(CareerMilestone).where(CareerMilestone.user_id == user_id))
        session.execute(delete(DevelopmentTask).where(DevelopmentTask.user_id == user_id))
        session.execute(delete(DevelopmentPlan).where(DevelopmentPlan.user_id == user_id))
        session.execute(delete(ReadinessSnapshot).where(ReadinessSnapshot.user_id == user_id))
        session.execute(delete(MarketRequirement).where(MarketRequirement.target_role_id.in_(role_ids)))
        session.execute(delete(TargetRole).where(TargetRole.user_id == user_id))
        session.execute(delete(SkillEvidence).where(SkillEvidence.user_id == user_id))
        session.execute(delete(LearningOpportunity).where(LearningOpportunity.user_id == user_id))
        session.execute(delete(CareerFact).where(CareerFact.user_id == user_id))
        session.execute(delete(AuditEvent).where(AuditEvent.user_id == user_id))
        session.execute(delete(UserProfile).where(UserProfile.id == user_id))


def _diagnose(user_id: str):
    return service.diagnose(
        {
            "target_role": "Junior Data Analyst",
            "level": "entry",
            "location": "Cairo",
            "market_requirements": [
                {"skill": "SQL", "label": "SQL", "frequency": .9, "importance": 1, "hard_requirement": True, "sample_size": 10, "evidence": [{"job": "A"}]},
                {"skill": "Power BI", "label": "Power BI", "frequency": .6, "importance": .7, "hard_requirement": False, "sample_size": 10, "evidence": [{"job": "B"}]},
            ],
        },
        user_id,
    )


def test_novice_gets_foundational_path_and_not_acceptance_probability():
    user_id = _user()
    try:
        readiness = _diagnose(user_id)
        assert readiness["scores"]["role_readiness"] == 0
        assert [item["label"] for item in readiness["hard_gaps"]] == ["SQL"]
        assert readiness["track"] == "development"
        assert "not an acceptance probability" in readiness["score_note"]

        plan = service.create_plan(user_id)
        assert plan["items"][0]["task_type"] == "learn"
        assert plan["milestones"][0]["kind"] == "foundation"
        assert plan["milestones"][-1]["kind"] == "junior_role"

        programs = service.learning_opportunities(True, user_id)
        iti = next(item for item in programs["items"] if "ITI Professional" in item["title"])
        assert iti["recommendable"] is False
        assert iti["status"] == "needs_verification"
        assert "acceptance probability" in programs["score_note"]
    finally:
        _cleanup(user_id)


def test_course_completion_records_exposure_but_does_not_raise_readiness():
    user_id = _user()
    try:
        original = _diagnose(user_id)
        plan = service.create_plan(user_id)
        task = plan["items"][0]
        completed = service.update_task(task["id"], "complete", {"deliverable_note": "Completed a focused SQL foundation and a worked query example."}, user_id)
        assert completed["status"] == "awaiting_assessment"
        with SessionLocal() as session:
            evidence = session.scalar(select(SkillEvidence).where(SkillEvidence.user_id == user_id, SkillEvidence.skill_key == task["skill_key"]))
            assert evidence.level == "exposed"
            assert evidence.confirmed is False
        recalculated = service.recalculate(user_id)
        assert recalculated["scores"]["role_readiness"] == original["scores"]["role_readiness"]
    finally:
        _cleanup(user_id)


def test_project_assessment_pass_creates_proposal_and_requires_decision():
    user_id = _user()
    try:
        _diagnose(user_id)
        with SessionLocal.begin() as session:
            session.add(SkillEvidence(user_id=user_id, skill_key="sql", label="SQL", level="knowledge_verified", source_type="assessment", confirmed=True))
        plan = service.create_plan(user_id)
        task = next(item for item in plan["items"] if item["skill_key"] == "sql")
        assert task["task_type"] == "project"
        service.update_task(task["id"], "complete", {"deliverable_note": "Built a SQL analysis project", "deliverable_url": "https://github.com/example/sql-project"}, user_id)
        assessment = service.start_assessment(task["id"], "project_defense", user_id)
        answer = "I built and tested a SQL project because the dataset needed consistent joins. I measured the result, checked edge cases, and documented the trade-off instead of hiding missing values."
        service.answer_assessment(assessment["id"], answer, {"deliverable_url": "https://github.com/example/sql-project"}, user_id)
        service.answer_assessment(assessment["id"], answer, {"deliverable_url": "https://github.com/example/sql-project"}, user_id)
        result = service.finish_assessment(assessment["id"], user_id)
        assert result["assessment"]["outcome"] == "pass"
        assert result["cv_proposal"]["status"] == "pending"
        with SessionLocal() as session:
            assert session.scalar(select(CareerFact).where(CareerFact.user_id == user_id, CareerFact.fact_key == "verified_skill_sql")) is None
        approved = service.decide_cv_proposal(result["cv_proposal"]["id"], "approved", user_id)
        assert approved["status"] == "approved"
        with SessionLocal() as session:
            fact = session.scalar(select(CareerFact).where(CareerFact.user_id == user_id, CareerFact.fact_key == "verified_skill_sql"))
            assert fact is not None and fact.cv_safe is True
    finally:
        _cleanup(user_id)


def test_weak_assessment_adds_remediation_without_claiming_progress():
    user_id = _user()
    try:
        _diagnose(user_id)
        plan = service.create_plan(user_id)
        task = plan["items"][0]
        service.update_task(task["id"], "complete", {"deliverable_note": "Read an introduction."}, user_id)
        assessment = service.start_assessment(task["id"], "mixed", user_id)
        service.answer_assessment(assessment["id"], "I read about it and remember a few terms but cannot show a concrete application yet.", {}, user_id)
        result = service.finish_assessment(assessment["id"], user_id)
        assert result["assessment"]["outcome"] in {"partial", "not_yet"}
        assert result["cv_proposal"] is None
        assert result["readiness_changed"] is False
        assert result["remediation_task"]["task_type"] == "remediation"
    finally:
        _cleanup(user_id)
