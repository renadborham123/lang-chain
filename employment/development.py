"""Deterministic qualification loop for Wazzefni.

The service deliberately separates readiness from hiring probability.  Language
models may explain these records elsewhere, but the stored scores and state
transitions are derived from evidence that can be inspected and replayed.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import func, select

from .database import SessionLocal, init_database
from .models import (
    AssessmentTurn,
    AuditEvent,
    CareerFact,
    CareerMilestone,
    CVChangeProposal,
    DevelopmentPlan,
    DevelopmentTask,
    LearningOpportunity,
    MarketRequirement,
    Opportunity,
    ReadinessSnapshot,
    SkillAssessment,
    SkillEvidence,
    TargetRole,
    UserProfile,
    utcnow,
)
from .repository import LOCAL_USER_ID


EVIDENCE_LEVELS = {
    "none": 0.0,
    "exposed": 0.2,
    "knowledge_verified": 0.5,
    "applied": 0.8,
    "interview_verified": 1.0,
}

SKILL_ALIASES: dict[str, tuple[str, ...]] = {
    "python": ("python",),
    "sql": ("sql", "mysql", "postgresql", "sql server"),
    "excel": ("excel", "spreadsheets"),
    "power_bi": ("power bi", "powerbi"),
    "tableau": ("tableau",),
    "data_analysis": ("data analysis", "data analytics", "pandas"),
    "statistics": ("statistics", "statistical"),
    "javascript": ("javascript", "typescript", "js", "ts"),
    "react": ("react", "react.js", "reactjs"),
    "nodejs": ("node", "node.js", "nodejs"),
    "fastapi": ("fastapi",),
    "django": ("django",),
    "git": ("git", "github", "version control"),
    "rest_api": ("rest api", "restful", "api development"),
    "docker": ("docker", "containers"),
    "linux": ("linux",),
    "figma": ("figma",),
    "ux_research": ("ux research", "user research", "usability testing"),
    "prototyping": ("prototyping", "prototype", "wireframe"),
    "communication": ("communication", "presentation", "stakeholder"),
}

ROLE_BLUEPRINTS: tuple[tuple[tuple[str, ...], tuple[tuple[str, str, float, bool], ...]], ...] = (
    (("data analyst", "business intelligence", "bi analyst"), (
        ("sql", "SQL", 1.0, True), ("excel", "Excel", .85, False),
        ("data_analysis", "Data analysis", 1.0, True), ("power_bi", "Power BI", .75, False),
        ("statistics", "Statistics", .65, False), ("communication", "Data storytelling", .55, False),
    )),
    (("backend", "back-end", "api developer"), (
        ("python", "Python", .9, True), ("sql", "SQL", .8, True),
        ("rest_api", "REST APIs", 1.0, True), ("git", "Git", .65, False),
        ("docker", "Docker", .55, False), ("linux", "Linux", .5, False),
    )),
    (("frontend", "front-end", "react developer"), (
        ("javascript", "JavaScript / TypeScript", 1.0, True), ("react", "React", .9, True),
        ("git", "Git", .6, False), ("rest_api", "API integration", .65, False),
        ("prototyping", "UI implementation", .45, False),
    )),
    (("ui", "ux", "product designer"), (
        ("figma", "Figma", 1.0, True), ("ux_research", "UX research", .75, False),
        ("prototyping", "Prototyping", .9, True), ("communication", "Design communication", .6, False),
    )),
)

OFFICIAL_PROGRAM_WATCHLIST = (
    {
        "provider": "Information Technology Institute (ITI)",
        "title": "ITI Professional Training Program (9-month)",
        "url": "https://iti.gov.eg/assets/pdfs/Student%20Handbook%20for%20ITI%20Programs.pdf",
        "requirements": ["Egyptian national", "Bachelor's degree", "Recent graduate", "Full-time commitment"],
        "skill_tags": ["python", "sql", "javascript", "react", "data_analysis", "ux_research"],
        "location": "Egypt — multiple branches",
    },
    {
        "provider": "Information Technology Institute (ITI)",
        "title": "ITI Intensive Code Camp",
        "url": "https://iti.gov.eg/assets/pdfs/Student%20Handbook%20for%20ITI%20Programs.pdf",
        "requirements": ["Egyptian graduate", "Bachelor's degree", "Full-time commitment"],
        "skill_tags": ["python", "sql", "javascript", "react", "docker", "linux"],
        "location": "Egypt — multiple branches",
    },
    {
        "provider": "National Telecommunication Institute (NTI)",
        "title": "NTI Training Programs",
        "url": "https://www.nti.sci.eg/",
        "requirements": [],
        "skill_tags": ["linux", "python", "communication"],
        "location": "Egypt",
    },
    {
        "provider": "Digital Egypt Pioneers Initiative (DEPI)",
        "title": "Digital Egypt Pioneers Initiative",
        "url": "https://depi.gov.eg/",
        "requirements": [],
        "skill_tags": ["python", "sql", "data_analysis", "javascript", "react", "ux_research"],
        "location": "Egypt",
    },
)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _skill_key(value: str) -> str:
    clean = re.sub(r"[^a-z0-9+#. ]+", " ", value.casefold())
    clean = " ".join(clean.split())
    for key, aliases in SKILL_ALIASES.items():
        if clean == key or any(alias in clean for alias in aliases):
            return key
    return clean.replace(" ", "_")[:120]


def _matches_skill(text: str, skill_key: str) -> bool:
    haystack = f" {text.casefold()} "
    aliases = SKILL_ALIASES.get(skill_key, (skill_key.replace("_", " "),))
    return any(re.search(rf"(?<![a-z0-9]){re.escape(alias.casefold())}(?![a-z0-9])", haystack) for alias in aliases)


def _clamp(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 1)


class DevelopmentService:
    def __init__(self) -> None:
        init_database()

    def diagnose(self, payload: dict[str, Any], user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        title = " ".join(str(payload.get("target_role") or "").split())
        if not title:
            raise ValueError("A target role is required.")
        level = str(payload.get("level") or "entry").strip().lower()
        location = str(payload.get("location") or "Egypt").strip()
        supplied_requirements = payload.get("market_requirements") or []
        jobs = payload.get("jobs") or []
        with SessionLocal.begin() as session:
            self._ensure_user(session, user_id)
            if not jobs:
                role_terms = {token for token in re.findall(r"[a-z0-9+#.]{3,}", title.casefold()) if token not in {"junior", "entry", "intern"}}
                opportunity_rows = session.scalars(select(Opportunity).where(Opportunity.user_id == user_id).order_by(Opportunity.updated_at.desc()).limit(80)).all()
                relevant_rows = [row for row in opportunity_rows if not role_terms or role_terms & set(re.findall(r"[a-z0-9+#.]{3,}", f"{row.title} {(row.payload or {}).get('description', '')}".casefold()))]
                jobs = [row.payload or {"title": row.title, "company": row.company, "location": row.location, "keywords": (row.evidence or {}).get("keywords", [])} for row in relevant_rows[:30]]
            for old in session.scalars(select(TargetRole).where(TargetRole.user_id == user_id, TargetRole.active.is_(True))).all():
                old.active = False
            role = TargetRole(user_id=user_id, title=title, domain=str(payload.get("domain") or ""), level=level, location=location, country="EG", active=True)
            session.add(role)
            session.flush()

            requirements = self._normalise_requirements(title, supplied_requirements, jobs)
            for item in requirements:
                session.add(MarketRequirement(target_role_id=role.id, **item))

            facts = session.scalars(select(CareerFact).where(CareerFact.user_id == user_id, CareerFact.confirmed.is_(True))).all()
            stored_evidence = session.scalars(select(SkillEvidence).where(SkillEvidence.user_id == user_id)).all()
            evidence_map = self._evidence_map(facts, stored_evidence, requirements)
            snapshot = self._build_snapshot(session, role, requirements, evidence_map, user_id, source="diagnose")
            self._audit(session, user_id, "development.diagnosed", "target_role", role.id, {"title": title, "sample_size": max((r["sample_size"] for r in requirements), default=0)})
            session.flush()
            return self._snapshot_view(snapshot, role, requirements, evidence_map)

    def latest_readiness(self, user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        with SessionLocal() as session:
            role = session.scalar(select(TargetRole).where(TargetRole.user_id == user_id, TargetRole.active.is_(True)).order_by(TargetRole.updated_at.desc()))
            if role is None:
                return {"configured": False, "message": "Choose a target role to calculate readiness."}
            snapshot = session.scalar(select(ReadinessSnapshot).where(ReadinessSnapshot.target_role_id == role.id).order_by(ReadinessSnapshot.version.desc()))
            requirements = session.scalars(select(MarketRequirement).where(MarketRequirement.target_role_id == role.id).order_by(MarketRequirement.importance.desc())).all()
            evidence = session.scalars(select(SkillEvidence).where(SkillEvidence.user_id == user_id)).all()
            if snapshot is None:
                return {"configured": False, "message": "Run a diagnosis to calculate readiness."}
            return self._snapshot_view(snapshot, role, requirements, {item.skill_key: self._evidence_view(item) for item in evidence})

    def create_plan(self, user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        with SessionLocal.begin() as session:
            role = session.scalar(select(TargetRole).where(TargetRole.user_id == user_id, TargetRole.active.is_(True)).order_by(TargetRole.updated_at.desc()))
            if role is None:
                raise ValueError("Run readiness diagnosis before creating a qualification plan.")
            snapshot = session.scalar(select(ReadinessSnapshot).where(ReadinessSnapshot.target_role_id == role.id).order_by(ReadinessSnapshot.version.desc()))
            if snapshot is None:
                raise ValueError("No readiness snapshot exists for this role.")
            for old in session.scalars(select(DevelopmentPlan).where(DevelopmentPlan.user_id == user_id, DevelopmentPlan.status == "active")).all():
                old.status = "superseded"
            version = int(session.scalar(select(func.max(DevelopmentPlan.version)).where(DevelopmentPlan.user_id == user_id)) or 0) + 1
            plan = DevelopmentPlan(
                user_id=user_id,
                target_role_id=role.id,
                version=version,
                summary=f"A focused qualification path for {role.title}, based on verified evidence and current sampled requirements.",
                rationale={"weights": {"market_frequency": 35, "role_importance": 25, "evidence_weakness": 20, "deadline": 10, "preferences": 10}, "readiness_snapshot_id": snapshot.id},
            )
            session.add(plan)
            session.flush()
            requirements = session.scalars(select(MarketRequirement).where(MarketRequirement.target_role_id == role.id)).all()
            evidence_rows = session.scalars(select(SkillEvidence).where(SkillEvidence.user_id == user_id)).all()
            evidence = {item.skill_key: item for item in evidence_rows}
            missing = sorted(requirements, key=lambda req: self._task_priority(req, evidence.get(req.skill_key)), reverse=True)
            created: list[DevelopmentTask] = []
            for req in missing:
                level_value = EVIDENCE_LEVELS.get(evidence.get(req.skill_key).level if evidence.get(req.skill_key) else "none", 0)
                if level_value >= .8:
                    continue
                task_type = "project" if level_value >= .2 else "learn"
                priority = self._task_priority(req, evidence.get(req.skill_key))
                impact = self._readiness_impact(req, requirements, level_value)
                task = DevelopmentTask(
                    user_id=user_id,
                    plan_id=plan.id,
                    skill_key=req.skill_key,
                    task_type=task_type,
                    title=(f"Build proof for {req.label}" if task_type == "project" else f"Learn the working foundations of {req.label}"),
                    detail=f"{req.label} appears in {round(req.frequency * 100)}% of the sampled requirements for {role.title}. Completing material alone will not mark it as verified.",
                    priority=priority,
                    dependencies=[],
                    deliverable=(f"A small, reviewable project that uses {req.label} and includes a README explaining your decisions." if task_type == "project" else f"Complete a focused foundation resource and write a one-page worked example using {req.label}."),
                    assessment_method="Concept questions, an applied scenario, and a short defence of your deliverable.",
                    readiness_impact=impact,
                    market_evidence={"sample_size": req.sample_size, "frequency": req.frequency, "importance": req.importance, "hard_requirement": req.hard_requirement, "examples": req.evidence[:3]},
                    unlocks=["A stronger project task", "Recalculated saved opportunities"] if task_type == "learn" else ["Skill assessment", "CV change proposal after passing"],
                )
                session.add(task)
                created.append(task)
            self._create_milestones(session, plan, role, bool(created))
            self._seed_program_watchlist(session, user_id)
            self._audit(session, user_id, "development.plan_created", "development_plan", plan.id, {"version": version, "task_count": len(created)})
            session.flush()
            return self._plan_view(session, plan)

    def list_tasks(self, user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        with SessionLocal() as session:
            plan = session.scalar(select(DevelopmentPlan).where(DevelopmentPlan.user_id == user_id, DevelopmentPlan.status == "active").order_by(DevelopmentPlan.updated_at.desc()))
            if plan is None:
                return {"configured": False, "items": [], "milestones": []}
            return self._plan_view(session, plan)

    def update_task(self, task_id: str, command: str, payload: dict[str, Any], user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        if command not in {"start", "complete", "snooze", "skip", "resume"}:
            raise ValueError("Command must be start, complete, snooze, skip, or resume.")
        with SessionLocal.begin() as session:
            task = session.get(DevelopmentTask, task_id)
            if task is None or task.user_id != user_id:
                raise KeyError("Development task was not found.")
            task.status = {"start": "in_progress", "complete": "awaiting_assessment", "snooze": "snoozed", "skip": "skipped", "resume": "pending"}[command]
            if command == "complete":
                task.completed_at = utcnow()
                # Completion records exposure only.  It never verifies the skill.
                evidence = session.scalar(select(SkillEvidence).where(SkillEvidence.user_id == user_id, SkillEvidence.skill_key == task.skill_key))
                if evidence is None:
                    evidence = SkillEvidence(user_id=user_id, skill_key=task.skill_key, label=task.skill_key.replace("_", " ").title())
                    session.add(evidence)
                if EVIDENCE_LEVELS.get(evidence.level, 0) < EVIDENCE_LEVELS["exposed"]:
                    evidence.level = "exposed"
                evidence.source_type = task.task_type
                evidence.source_id = task.id
                evidence.description = str(payload.get("deliverable_note") or task.deliverable)
                evidence.confirmed = False
                evidence.metadata_json = {"deliverable_url": str(payload.get("deliverable_url") or ""), "completion_is_not_verification": True}
            task.updated_at = utcnow()
            self._audit(session, user_id, f"development.task_{command}", "development_task", task.id, payload)
            session.flush()
            return self._task_view(task)

    def start_assessment(self, task_id: str, assessment_type: str, user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        with SessionLocal.begin() as session:
            task = session.get(DevelopmentTask, task_id)
            if task is None or task.user_id != user_id:
                raise KeyError("Development task was not found.")
            if task.status not in {"awaiting_assessment", "in_progress"}:
                raise ValueError("Complete the task deliverable before starting its assessment.")
            existing = session.scalar(select(SkillAssessment).where(SkillAssessment.task_id == task.id, SkillAssessment.status == "active"))
            if existing:
                return self._assessment_view(session, existing)
            kind = assessment_type if assessment_type in {"concept", "scenario", "project_defense", "mixed"} else "mixed"
            assessment = SkillAssessment(
                user_id=user_id,
                task_id=task.id,
                skill_key=task.skill_key,
                assessment_type=kind,
                rubric={"relevance": 20, "correctness": 25, "reasoning": 25, "evidence": 20, "clarity": 10, "pass_score": 70},
                provenance={"generator": "deterministic-v1", "task_id": task.id, "skill_key": task.skill_key},
            )
            session.add(assessment)
            session.flush()
            question = self._assessment_question(task.skill_key, kind, 1)
            session.add(AssessmentTurn(assessment_id=assessment.id, sequence=1, question_type="concept", question=question))
            session.flush()
            return self._assessment_view(session, assessment)

    def answer_assessment(self, assessment_id: str, answer: str, evidence: dict[str, Any], user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        clean = " ".join(answer.split())
        if len(clean) < 12:
            raise ValueError("Give enough detail for the assessment to evaluate your reasoning.")
        with SessionLocal.begin() as session:
            assessment = session.get(SkillAssessment, assessment_id)
            if assessment is None or assessment.user_id != user_id:
                raise KeyError("Skill assessment was not found.")
            if assessment.status != "active":
                raise ValueError("This assessment is already complete.")
            turn = session.scalar(select(AssessmentTurn).where(AssessmentTurn.assessment_id == assessment.id, AssessmentTurn.answer == "").order_by(AssessmentTurn.sequence.asc()))
            if turn is None:
                sequence = int(session.scalar(select(func.max(AssessmentTurn.sequence)).where(AssessmentTurn.assessment_id == assessment.id)) or 0) + 1
                turn = AssessmentTurn(assessment_id=assessment.id, sequence=sequence, question_type="follow_up", question=self._assessment_question(assessment.skill_key, assessment.assessment_type, sequence))
                session.add(turn)
                session.flush()
            evaluation = self._evaluate_answer(assessment.skill_key, turn.question, clean, evidence)
            turn.answer = clean
            turn.evaluation = evaluation
            turn.evidence = evidence or {}
            next_question = None
            if turn.sequence < 3:
                next_sequence = turn.sequence + 1
                next_question = self._assessment_question(assessment.skill_key, assessment.assessment_type, next_sequence, weak=next((key for key, value in evaluation["scores"].items() if value < 60), "reasoning"))
                session.add(AssessmentTurn(assessment_id=assessment.id, sequence=next_sequence, question_type="scenario" if next_sequence == 2 else "project_defense", question=next_question))
            session.flush()
            return {"turn": self._turn_view(turn), "next_question": next_question, "assessment_id": assessment.id}

    def finish_assessment(self, assessment_id: str, user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        with SessionLocal.begin() as session:
            assessment = session.get(SkillAssessment, assessment_id)
            if assessment is None or assessment.user_id != user_id:
                raise KeyError("Skill assessment was not found.")
            turns = session.scalars(select(AssessmentTurn).where(AssessmentTurn.assessment_id == assessment.id, AssessmentTurn.answer != "").order_by(AssessmentTurn.sequence.asc())).all()
            if not turns:
                raise ValueError("Answer at least one assessment question before finishing.")
            metrics = ("relevance", "correctness", "reasoning", "evidence", "clarity")
            scores = {metric: round(sum(float((turn.evaluation or {}).get("scores", {}).get(metric, 0)) for turn in turns) / len(turns), 1) for metric in metrics}
            total = round(sum(scores.values()) / len(metrics), 1)
            outcome = "pass" if len(turns) >= 2 and total >= 70 and scores["evidence"] >= 60 else "partial" if total >= 50 else "not_yet"
            assessment.status = "complete"
            assessment.outcome = outcome
            assessment.scores = {**scores, "overall": total}
            assessment.confidence = min(.95, .55 + .12 * len(turns))
            assessment.completed_at = utcnow()
            task = session.get(DevelopmentTask, assessment.task_id)
            proposal = None
            remediation = None
            if outcome == "pass":
                task.status = "completed"
                evidence = session.scalar(select(SkillEvidence).where(SkillEvidence.user_id == user_id, SkillEvidence.skill_key == assessment.skill_key))
                if evidence is None:
                    evidence = SkillEvidence(user_id=user_id, skill_key=assessment.skill_key, label=assessment.skill_key.replace("_", " ").title())
                    session.add(evidence)
                evidence.level = "interview_verified" if task.task_type == "project" else "knowledge_verified"
                evidence.source_type = "assessment"
                evidence.source_id = assessment.id
                evidence.confirmed = True
                evidence.metadata_json = {"scores": assessment.scores, "assessment_type": assessment.assessment_type}
                if evidence.level in {"applied", "interview_verified"}:
                    proposal = CVChangeProposal(
                        user_id=user_id,
                        assessment_id=assessment.id,
                        skill_key=assessment.skill_key,
                        section="projects" if task.task_type == "project" else "skills",
                        old_text="",
                        proposed_text=f"Demonstrated {evidence.label} through an assessed project; explain the exact project scope and result before publishing.",
                        evidence={"assessment_id": assessment.id, "task_id": task.id, "scores": assessment.scores, "level": evidence.level},
                    )
                    session.add(proposal)
            else:
                task.status = "needs_revision"
                remediation = DevelopmentTask(
                    user_id=user_id,
                    plan_id=task.plan_id,
                    skill_key=task.skill_key,
                    task_type="remediation",
                    title=f"Strengthen {task.skill_key.replace('_', ' ').title()} before reassessment",
                    detail="The assessment found a specific proof or reasoning gap. Your previous readiness score is unchanged.",
                    priority=min(100, task.priority + 5),
                    dependencies=[task.id],
                    deliverable="Revise the weakest answer and add one concrete, inspectable example.",
                    assessment_method="Short reassessment focused on the weakest rubric dimensions.",
                    readiness_impact=0,
                    market_evidence={"assessment_id": assessment.id, "weak_scores": {key: value for key, value in scores.items() if value < 70}},
                    unlocks=["Reassessment"],
                )
                session.add(remediation)
            self._audit(session, user_id, "development.assessment_finished", "skill_assessment", assessment.id, {"outcome": outcome, "scores": assessment.scores})
            session.flush()
            return {"assessment": self._assessment_view(session, assessment), "cv_proposal": self._proposal_view(proposal) if proposal else None, "remediation_task": self._task_view(remediation) if remediation else None, "readiness_changed": False, "note": "Passing creates verified evidence and a proposal; readiness changes only after recalculation."}

    def decide_cv_proposal(self, proposal_id: str, decision: str, user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        if decision not in {"approved", "rejected"}:
            raise ValueError("Decision must be approved or rejected.")
        with SessionLocal.begin() as session:
            proposal = session.get(CVChangeProposal, proposal_id)
            if proposal is None or proposal.user_id != user_id:
                raise KeyError("CV change proposal was not found.")
            if proposal.status != "pending":
                return self._proposal_view(proposal)
            proposal.status = decision
            proposal.decided_at = utcnow()
            if decision == "approved":
                fact_key = f"verified_skill_{proposal.skill_key}"
                fact = session.scalar(select(CareerFact).where(CareerFact.user_id == user_id, CareerFact.fact_key == fact_key))
                if fact is None:
                    fact = CareerFact(user_id=user_id, fact_key=fact_key, value=proposal.proposed_text)
                    session.add(fact)
                fact.value = proposal.proposed_text
                fact.category = proposal.section
                fact.source = "approved_skill_assessment"
                fact.evidence = proposal.evidence
                fact.confirmed = True
                fact.cv_safe = True
            self._audit(session, user_id, f"development.cv_proposal_{decision}", "cv_change_proposal", proposal.id, {"skill_key": proposal.skill_key})
            session.flush()
            return self._proposal_view(proposal)

    def recalculate(self, user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        with SessionLocal.begin() as session:
            role = session.scalar(select(TargetRole).where(TargetRole.user_id == user_id, TargetRole.active.is_(True)).order_by(TargetRole.updated_at.desc()))
            if role is None:
                raise ValueError("Choose a target role first.")
            requirements = session.scalars(select(MarketRequirement).where(MarketRequirement.target_role_id == role.id)).all()
            facts = session.scalars(select(CareerFact).where(CareerFact.user_id == user_id, CareerFact.confirmed.is_(True))).all()
            evidence = session.scalars(select(SkillEvidence).where(SkillEvidence.user_id == user_id)).all()
            evidence_map = self._evidence_map(facts, evidence, requirements)
            snapshot = self._build_snapshot(session, role, requirements, evidence_map, user_id, source="recalculate")
            for opportunity in session.scalars(select(Opportunity).where(Opportunity.user_id == user_id)).all():
                ranking = self._rank_opportunity(opportunity, requirements, evidence_map)
                opportunity.payload = {**(opportunity.payload or {}), **ranking}
                opportunity.updated_at = utcnow()
            session.flush()
            return self._snapshot_view(snapshot, role, requirements, evidence_map)

    def opportunity_readiness(self, opportunity_id: str, user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        with SessionLocal() as session:
            opportunity = session.get(Opportunity, opportunity_id)
            if opportunity is None or opportunity.user_id != user_id:
                raise KeyError("Opportunity was not found.")
            role = session.scalar(select(TargetRole).where(TargetRole.user_id == user_id, TargetRole.active.is_(True)))
            requirements = session.scalars(select(MarketRequirement).where(MarketRequirement.target_role_id == role.id)).all() if role else []
            payload_text = " ".join(str(value) for value in (opportunity.payload or {}).values())
            relevant = [req for req in requirements if _matches_skill(payload_text, req.skill_key)] or list(requirements)
            evidence = {item.skill_key: item for item in session.scalars(select(SkillEvidence).where(SkillEvidence.user_id == user_id)).all()}
            total_weight = sum(max(.1, req.importance) for req in relevant) or 1
            def verified_value(skill_key: str) -> float:
                item = evidence.get(skill_key)
                return EVIDENCE_LEVELS.get(item.level, 0) if item and item.confirmed else 0
            score = _clamp(100 * sum(max(.1, req.importance) * verified_value(req.skill_key) for req in relevant) / total_weight)
            hard_gaps = [req.label for req in relevant if req.hard_requirement and verified_value(req.skill_key) < .5]
            track = "unlock_later" if hard_gaps or score < 65 else "apply_while_improving" if score < 80 else "apply_now"
            return {"opportunity_id": opportunity.id, "readiness": score, "track": track, "hard_gaps": hard_gaps, "recommend_apply": track != "unlock_later", "label": "Readiness based on verifiable requirements — not acceptance probability.", "requirements": [req.label for req in relevant]}

    def learning_opportunities(self, include_watchlist: bool = True, user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        with SessionLocal.begin() as session:
            self._ensure_user(session, user_id)
            if include_watchlist:
                self._seed_program_watchlist(session, user_id)
            now = utcnow()
            rows = session.scalars(select(LearningOpportunity).where(LearningOpportunity.user_id == user_id).order_by(LearningOpportunity.relevance.desc(), LearningOpportunity.updated_at.desc())).all()
            items = []
            for row in rows:
                expired = bool(row.deadline and self._aware(row.deadline) < now)
                verified_recently = bool(row.verified_at and self._aware(row.verified_at) >= now - timedelta(days=14))
                recommendable = row.status == "open" and verified_recently and not expired
                items.append({**self._learning_view(row), "expired": expired, "recommendable": recommendable, "verification_note": "Verified from the official source within 14 days." if recommendable else "Open the official source to verify the current intake, deadline, and eligibility before treating this as active."})
            return {"items": items, "score_note": "Relevance and eligibility readiness are separate. Neither is an acceptance probability."}

    def sync_learning_opportunities(self, items: Iterable[dict[str, Any]], user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        """Store externally verified results without guessing missing fields."""
        with SessionLocal.begin() as session:
            self._ensure_user(session, user_id)
            output = []
            for item in items:
                url = str(item.get("url") or "").strip()
                title = str(item.get("title") or "").strip()
                if not url or not title:
                    continue
                row = session.scalar(select(LearningOpportunity).where(LearningOpportunity.user_id == user_id, LearningOpportunity.url == url))
                if row is None:
                    row = LearningOpportunity(user_id=user_id, provider=str(item.get("provider") or "Unknown provider"), title=title, url=url)
                    session.add(row)
                row.provider = str(item.get("provider") or row.provider)
                row.title = title
                row.source_type = str(item.get("source_type") or "official")
                row.opportunity_type = str(item.get("opportunity_type") or "training")
                row.status = str(item.get("status") or "needs_verification")
                row.requirements = list(item.get("requirements") or [])
                row.skill_tags = [_skill_key(str(value)) for value in item.get("skill_tags") or []]
                row.cost = str(item.get("cost") or "Not stated")
                row.location = str(item.get("location") or "Not stated")
                row.deadline = self._parse_datetime(item.get("deadline"))
                row.relevance = _clamp(float(item.get("relevance") or 0))
                row.eligibility_readiness = _clamp(float(item.get("eligibility_readiness") or 0))
                row.source_evidence = dict(item.get("source_evidence") or {})
                row.verified_at = self._parse_datetime(item.get("verified_at"))
                row.updated_at = utcnow()
                session.flush()
                output.append(self._learning_view(row))
            return {"items": output}

    def get_assessment(self, assessment_id: str, user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        with SessionLocal() as session:
            assessment = session.get(SkillAssessment, assessment_id)
            if assessment is None or assessment.user_id != user_id:
                raise KeyError("Skill assessment was not found.")
            return self._assessment_view(session, assessment)

    def _normalise_requirements(self, role_title: str, supplied: list[dict[str, Any]], jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if supplied:
            result = []
            for item in supplied:
                label = str(item.get("label") or item.get("skill") or "").strip()
                if not label:
                    continue
                frequency = float(item.get("frequency") or 0)
                if frequency > 1:
                    frequency /= 100
                result.append({"skill_key": _skill_key(str(item.get("skill") or label)), "label": label, "frequency": max(0, min(1, frequency)), "sample_size": int(item.get("sample_size") or len(jobs) or 1), "importance": max(0, min(1, float(item.get("importance") or .5))), "hard_requirement": bool(item.get("hard_requirement")), "evidence": list(item.get("evidence") or [])[:10], "last_seen_at": utcnow()})
            if result:
                return result
        texts = [" ".join(str(value) for value in job.values()) for job in jobs]
        if texts:
            result = []
            for key, aliases in SKILL_ALIASES.items():
                hits = [index for index, text in enumerate(texts) if _matches_skill(text, key)]
                if hits:
                    frequency = len(hits) / len(texts)
                    result.append({"skill_key": key, "label": aliases[0].replace("_", " ").title(), "frequency": frequency, "sample_size": len(texts), "importance": min(1, .45 + frequency * .55), "hard_requirement": frequency >= .7, "evidence": [{"job_index": index, "quote": self._quote_for_skill(texts[index], key)} for index in hits[:5]], "last_seen_at": utcnow()})
            if result:
                return sorted(result, key=lambda item: item["frequency"], reverse=True)[:12]
        title = role_title.casefold()
        for markers, requirements in ROLE_BLUEPRINTS:
            if any(marker in title for marker in markers):
                return [{"skill_key": key, "label": label, "frequency": importance, "sample_size": 0, "importance": importance, "hard_requirement": hard, "evidence": [{"source": "role_blueprint", "note": "Starter requirement only; replace with a current market sample."}], "last_seen_at": utcnow()} for key, label, importance, hard in requirements]
        return [
            {"skill_key": "communication", "label": "Role communication", "frequency": .5, "sample_size": 0, "importance": .5, "hard_requirement": False, "evidence": [{"source": "role_blueprint", "note": "No current market sample was supplied."}], "last_seen_at": utcnow()},
            {"skill_key": "portfolio_evidence", "label": "Relevant work evidence", "frequency": .8, "sample_size": 0, "importance": .8, "hard_requirement": True, "evidence": [{"source": "role_blueprint", "note": "Generic starter requirement."}], "last_seen_at": utcnow()},
        ]

    def _evidence_map(self, facts: Iterable[CareerFact], stored: Iterable[SkillEvidence], requirements: Iterable[Any]) -> dict[str, dict[str, Any]]:
        fact_rows = list(facts)
        result = {item.skill_key: self._evidence_view(item) for item in stored}
        for requirement in requirements:
            key = requirement.skill_key if hasattr(requirement, "skill_key") else requirement["skill_key"]
            label = requirement.label if hasattr(requirement, "label") else requirement["label"]
            matching = [fact for fact in fact_rows if _matches_skill(f"{fact.fact_key} {fact.value}", key)]
            if matching and EVIDENCE_LEVELS.get(result.get(key, {}).get("level", "none"), 0) < .5:
                has_applied = any(fact.category in {"project", "projects", "experience", "work"} for fact in matching)
                result[key] = {"skill_key": key, "label": label, "level": "applied" if has_applied else "knowledge_verified", "confirmed": True, "source_type": "career_fact", "source_ids": [fact.id for fact in matching], "cv_represented": any(fact.cv_safe for fact in matching)}
        return result

    def _build_snapshot(self, session, role: TargetRole, requirements: Iterable[Any], evidence_map: dict[str, dict[str, Any]], user_id: str, source: str) -> ReadinessSnapshot:
        reqs = list(requirements)
        weights = [max(.1, float(req.importance if hasattr(req, "importance") else req["importance"])) for req in reqs]
        total_weight = sum(weights) or 1
        covered, missing, hard_gaps = [], [], []
        role_points = evidence_points = represented_points = represented_total = 0.0
        for req, weight in zip(reqs, weights):
            key = req.skill_key if hasattr(req, "skill_key") else req["skill_key"]
            label = req.label if hasattr(req, "label") else req["label"]
            hard = bool(req.hard_requirement if hasattr(req, "hard_requirement") else req["hard_requirement"])
            evidence = evidence_map.get(key, {})
            level = evidence.get("level", "none")
            # Exposure is useful context but cannot raise readiness until the
            # evidence has passed a verification step.
            value = EVIDENCE_LEVELS.get(level, 0) if evidence.get("confirmed") else 0
            role_points += weight * value
            evidence_points += weight * (1 if value >= .8 else .6 if value >= .5 else .25 if value > 0 else 0)
            if value > 0:
                represented_total += weight
                if evidence.get("cv_represented"):
                    represented_points += weight
            record = {"skill_key": key, "label": label, "level": level, "weight": round(weight, 2), "evidence": evidence}
            (covered if value >= .5 else missing).append(record)
            if hard and value < .5:
                hard_gaps.append(record)
        version = int(session.scalar(select(func.max(ReadinessSnapshot.version)).where(ReadinessSnapshot.target_role_id == role.id)) or 0) + 1
        role_readiness = _clamp(100 * role_points / total_weight)
        snapshot = ReadinessSnapshot(
            user_id=user_id,
            target_role_id=role.id,
            version=version,
            role_readiness=role_readiness,
            evidence_strength=_clamp(100 * evidence_points / total_weight),
            cv_representation=_clamp(100 * represented_points / represented_total) if represented_total else 0,
            covered_requirements=covered,
            missing_requirements=missing,
            hard_gaps=hard_gaps,
            explanation=f"Current readiness for {role.title} is {role_readiness:.0f}% based only on requirements and evidence that could be checked. This is not an acceptance probability.",
            provenance={"calculator": "readiness-v1", "source": source, "weights": "importance weighted", "requirement_count": len(reqs), "calculated_at": _iso(utcnow())},
        )
        session.add(snapshot)
        return snapshot

    @staticmethod
    def _task_priority(req: MarketRequirement, evidence: SkillEvidence | None) -> float:
        frequency = max(0, min(1, req.frequency))
        importance = max(0, min(1, req.importance))
        weakness = 1 - EVIDENCE_LEVELS.get(evidence.level if evidence else "none", 0)
        deadline = 0
        preference = .5
        return _clamp(frequency * 35 + importance * 25 + weakness * 20 + deadline * 10 + preference * 10)

    @staticmethod
    def _readiness_impact(req: MarketRequirement, requirements: Iterable[MarketRequirement], current: float) -> float:
        total = sum(max(.1, item.importance) for item in requirements) or 1
        return round(100 * max(.1, req.importance) * (min(.8, current + .5) - current) / total, 1)

    @staticmethod
    def _assessment_question(skill: str, kind: str, sequence: int, weak: str = "") -> str:
        label = skill.replace("_", " ")
        if sequence == 1:
            return f"Explain one core concept in {label}, when you would use it, and one limitation or trade-off."
        if sequence == 2:
            return f"You need to use {label} in a small real project. Walk through your approach, the checks you would make, and how you would know it worked."
        return f"Defend the deliverable you completed for {label}: what exactly did you build, which decision was yours, what evidence can be inspected, and what would you improve? Focus especially on {weak or 'reasoning'}."

    @staticmethod
    def _evaluate_answer(skill: str, question: str, answer: str, evidence: dict[str, Any]) -> dict[str, Any]:
        words = answer.split()
        text = answer.casefold()
        mentions_skill = _matches_skill(answer, skill) or skill.replace("_", " ") in text
        reasoning_markers = sum(token in text for token in ("because", "therefore", "trade-off", "instead", "so that", "لأن", "لذلك", "مقارنة", "بدلاً"))
        applied_markers = sum(token in text for token in ("built", "implemented", "tested", "measured", "result", "project", "بنيت", "نفذت", "اختبرت", "النتيجة", "مشروع"))
        evidence_link = bool(evidence.get("url") or evidence.get("deliverable_url") or evidence.get("repository"))
        scores = {
            "relevance": min(100, 55 + (20 if mentions_skill else 0) + min(20, len(words) // 8)),
            "correctness": min(100, 50 + min(30, len(words) // 5) + (10 if reasoning_markers else 0)),
            "reasoning": min(100, 45 + reasoning_markers * 15 + min(20, len(words) // 10)),
            "evidence": min(100, 35 + applied_markers * 12 + (25 if evidence_link else 0)),
            "clarity": 85 if 35 <= len(words) <= 220 else 65 if 20 <= len(words) <= 300 else 45,
        }
        weak = [key for key, value in scores.items() if value < 60]
        return {"scores": scores, "strengths": ["The answer is tied to the assessed skill."] if mentions_skill else ["The answer contains assessable detail."], "improvements": [f"Add stronger {item.replace('_', ' ')}." for item in weak[:2]], "source_note": "Deterministic assessment of the supplied answer and explicit deliverable evidence only."}

    def _create_milestones(self, session, plan: DevelopmentPlan, role: TargetRole, has_tasks: bool) -> None:
        specs = (
            ("foundation", "Build the foundations", "Complete the first prerequisite and explain the core concepts."),
            ("project", "Create a small proof project", "Produce something inspectable instead of relying on course completion."),
            ("entry_training", "Enter a suitable training step", "Use relevance and eligibility readiness separately."),
            ("internship", "Unlock a stronger internship", "Apply selectively while continuing to improve."),
            ("advanced_program", "Prepare for an advanced program", "Close hard prerequisites before a selective program such as ITI."),
            ("junior_role", f"Compete for {role.title}", "Apply when evidence covers the role's hard requirements."),
        )
        for index, (kind, title, detail) in enumerate(specs, start=1):
            session.add(CareerMilestone(user_id=plan.user_id, plan_id=plan.id, sequence=index, kind=kind, title=title, description=detail, status="active" if index == 1 and has_tasks else "locked", unlock_rule={"previous_milestone_required": index > 1}))

    @staticmethod
    def _rank_opportunity(opportunity: Opportunity, requirements: Iterable[MarketRequirement], evidence_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
        reqs = list(requirements)
        text = " ".join(str(value) for value in (opportunity.payload or {}).values())
        relevant = [req for req in reqs if _matches_skill(text, req.skill_key)] or reqs
        total = sum(max(.1, req.importance) for req in relevant) or 1
        def verified(skill_key: str) -> float:
            item = evidence_map.get(skill_key, {})
            return EVIDENCE_LEVELS.get(str(item.get("level") or "none"), 0) if item.get("confirmed") else 0
        score = _clamp(100 * sum(max(.1, req.importance) * verified(req.skill_key) for req in relevant) / total)
        hard_gaps = [req.label for req in relevant if req.hard_requirement and verified(req.skill_key) < .5]
        track = "unlock_later" if hard_gaps or score < 65 else "apply_while_improving" if score < 80 else "apply_now"
        return {"readiness": score, "readiness_track": track, "readiness_hard_gaps": hard_gaps, "readiness_is_not_acceptance_probability": True}

    def _seed_program_watchlist(self, session, user_id: str) -> None:
        existing_urls = set(session.scalars(select(LearningOpportunity.url).where(LearningOpportunity.user_id == user_id)).all())
        for item in OFFICIAL_PROGRAM_WATCHLIST:
            # Two ITI program names intentionally share the source document, so
            # use a stable fragment while keeping the official document URL.
            url = item["url"] + ("#intensive-code-camp" if "Intensive" in item["title"] else "")
            if url in existing_urls:
                continue
            session.add(LearningOpportunity(user_id=user_id, provider=item["provider"], title=item["title"], url=url, source_type="official", status="needs_verification", requirements=item["requirements"], skill_tags=item["skill_tags"], location=item["location"], cost="Not stated", relevance=0, eligibility_readiness=0, source_evidence={"official_source": item["url"], "missing": ["current intake", "deadline", "application status"]}))
            existing_urls.add(url)

    def _plan_view(self, session, plan: DevelopmentPlan) -> dict[str, Any]:
        tasks = session.scalars(select(DevelopmentTask).where(DevelopmentTask.plan_id == plan.id).order_by(DevelopmentTask.status == "completed", DevelopmentTask.priority.desc(), DevelopmentTask.created_at.asc())).all()
        milestones = session.scalars(select(CareerMilestone).where(CareerMilestone.plan_id == plan.id).order_by(CareerMilestone.sequence.asc())).all()
        return {"configured": True, "id": plan.id, "version": plan.version, "status": plan.status, "summary": plan.summary, "rationale": plan.rationale or {}, "items": [self._task_view(item) for item in tasks], "milestones": [{"id": item.id, "sequence": item.sequence, "kind": item.kind, "title": item.title, "description": item.description, "status": item.status, "unlock_rule": item.unlock_rule or {}} for item in milestones], "updated_at": _iso(plan.updated_at)}

    def _snapshot_view(self, snapshot: ReadinessSnapshot, role: TargetRole, requirements: Iterable[Any], evidence_map: dict[str, Any]) -> dict[str, Any]:
        requirement_views = []
        for req in requirements:
            if isinstance(req, MarketRequirement):
                requirement_views.append({"id": req.id, "skill_key": req.skill_key, "label": req.label, "frequency": req.frequency, "sample_size": req.sample_size, "importance": req.importance, "hard_requirement": req.hard_requirement, "evidence": req.evidence or []})
            else:
                requirement_views.append(req)
        score = snapshot.role_readiness
        track = "development" if snapshot.hard_gaps or score < 65 else "apply_while_improving" if score < 80 else "apply_now"
        return {"configured": True, "id": snapshot.id, "version": snapshot.version, "target_role": {"id": role.id, "title": role.title, "domain": role.domain, "level": role.level, "location": role.location, "country": role.country}, "scores": {"role_readiness": snapshot.role_readiness, "evidence_strength": snapshot.evidence_strength, "cv_representation": snapshot.cv_representation}, "track": track, "covered_requirements": snapshot.covered_requirements or [], "missing_requirements": snapshot.missing_requirements or [], "hard_gaps": snapshot.hard_gaps or [], "requirements": requirement_views, "skill_evidence": list(evidence_map.values()), "explanation": snapshot.explanation, "provenance": snapshot.provenance or {}, "created_at": _iso(snapshot.created_at), "score_note": "Readiness describes verified coverage. It is not an acceptance probability or a hiring promise."}

    @staticmethod
    def _task_view(task: DevelopmentTask | None) -> dict[str, Any] | None:
        if task is None:
            return None
        return {"id": task.id, "plan_id": task.plan_id, "skill_key": task.skill_key, "task_type": task.task_type, "title": task.title, "detail": task.detail, "priority": task.priority, "status": task.status, "dependencies": task.dependencies or [], "deliverable": task.deliverable, "assessment_method": task.assessment_method, "readiness_impact": task.readiness_impact, "market_evidence": task.market_evidence or {}, "unlocks": task.unlocks or [], "due_at": _iso(task.due_at), "completed_at": _iso(task.completed_at), "created_at": _iso(task.created_at)}

    def _assessment_view(self, session, assessment: SkillAssessment) -> dict[str, Any]:
        turns = session.scalars(select(AssessmentTurn).where(AssessmentTurn.assessment_id == assessment.id).order_by(AssessmentTurn.sequence.asc())).all()
        return {"id": assessment.id, "task_id": assessment.task_id, "skill_key": assessment.skill_key, "assessment_type": assessment.assessment_type, "status": assessment.status, "outcome": assessment.outcome, "rubric": assessment.rubric or {}, "scores": assessment.scores or {}, "confidence": assessment.confidence, "provenance": assessment.provenance or {}, "turns": [self._turn_view(item) for item in turns], "created_at": _iso(assessment.created_at), "completed_at": _iso(assessment.completed_at)}

    @staticmethod
    def _turn_view(turn: AssessmentTurn) -> dict[str, Any]:
        return {"id": turn.id, "sequence": turn.sequence, "question_type": turn.question_type, "question": turn.question, "answer": turn.answer, "evaluation": turn.evaluation or {}, "evidence": turn.evidence or {}}

    @staticmethod
    def _proposal_view(proposal: CVChangeProposal | None) -> dict[str, Any] | None:
        if proposal is None:
            return None
        return {"id": proposal.id, "assessment_id": proposal.assessment_id, "skill_key": proposal.skill_key, "section": proposal.section, "old_text": proposal.old_text, "proposed_text": proposal.proposed_text, "evidence": proposal.evidence or {}, "status": proposal.status, "decided_at": _iso(proposal.decided_at), "created_at": _iso(proposal.created_at)}

    @staticmethod
    def _evidence_view(item: SkillEvidence) -> dict[str, Any]:
        return {"id": item.id, "skill_key": item.skill_key, "label": item.label, "level": item.level, "source_type": item.source_type, "source_id": item.source_id, "description": item.description, "confirmed": item.confirmed, "metadata": item.metadata_json or {}, "cv_represented": False}

    @staticmethod
    def _learning_view(item: LearningOpportunity) -> dict[str, Any]:
        return {"id": item.id, "provider": item.provider, "title": item.title, "url": item.url, "source_type": item.source_type, "opportunity_type": item.opportunity_type, "status": item.status, "requirements": item.requirements or [], "skill_tags": item.skill_tags or [], "cost": item.cost or "Not stated", "location": item.location or "Not stated", "deadline": _iso(item.deadline), "relevance": item.relevance, "eligibility_readiness": item.eligibility_readiness, "source_evidence": item.source_evidence or {}, "verified_at": _iso(item.verified_at)}

    @staticmethod
    def _ensure_user(session, user_id: str) -> None:
        if session.get(UserProfile, user_id) is None:
            session.add(UserProfile(id=user_id, locale="en", country="EG", profile={}, preferences={}))
            session.flush()

    @staticmethod
    def _audit(session, user_id: str, action: str, target_type: str, target_id: str, detail: dict[str, Any]) -> None:
        session.add(AuditEvent(user_id=user_id, actor="development_agent", action=action, target_type=target_type, target_id=target_id, detail=detail))

    @staticmethod
    def _quote_for_skill(text: str, skill_key: str) -> str:
        aliases = SKILL_ALIASES.get(skill_key, (skill_key.replace("_", " "),))
        position = min((text.casefold().find(alias) for alias in aliases if alias in text.casefold()), default=-1)
        if position < 0:
            return text[:220]
        return text[max(0, position - 80): position + 140].strip()

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


development = DevelopmentService()
