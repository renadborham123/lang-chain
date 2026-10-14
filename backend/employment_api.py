"""FastAPI routes for the complete AI employment journey."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from employment.agents import supervisor
from employment.development import development
from employment.integrations import integrations
from employment.repository import APPLICATION_STATES, repository
from backend.auth import current_user_id
from document_store import get_active_document, get_cv_text
from profile_questions import generate_profile_questions


router = APIRouter(prefix="/api", tags=["employment-os"])


def _raise(exc: Exception) -> None:
    if isinstance(exc, KeyError):
        raise HTTPException(404, str(exc).strip("'")) from exc
    raise HTTPException(422, str(exc)) from exc


class ProfileUpdate(BaseModel):
    locale: str | None = None
    country: str | None = None
    profile: dict[str, Any] | None = None
    preferences: dict[str, Any] | None = None


class ProfileAnswersRequest(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)


class FactRequest(BaseModel):
    fact_key: str
    value: str
    category: str = "profile"
    source: str = "user_confirmed"
    evidence: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = True
    cv_safe: bool = False


class OpportunitySyncRequest(BaseModel):
    jobs: list[dict[str, Any]] = Field(default_factory=list)


class OpportunityStatusRequest(BaseModel):
    status: Literal["discovered", "saved", "dismissed"]


class ApplicationCreateRequest(BaseModel):
    opportunity_id: str | None = None
    title: str
    company: str = ""
    location: str = ""
    url: str = ""
    status: str = "preparing"
    document_id: str | None = None
    source: str = ""
    match_score: float = 0
    payload: dict[str, Any] = Field(default_factory=dict)


class TransitionRequest(BaseModel):
    status: str
    source: str = "user"
    message: str = ""
    evidence: dict[str, Any] = Field(default_factory=dict)


class ActionCommandRequest(BaseModel):
    command: Literal["done", "dismiss", "snooze", "undo"]
    snooze_hours: int = 24


class ActionFeedbackRequest(BaseModel):
    rating: Literal["useful", "wrong", "already_done", "not_relevant"]
    note: str = ""


class ApprovalCreateRequest(BaseModel):
    action_type: str
    summary: str
    target_type: str = ""
    target_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    channel: str = "app"
    idempotency_key: str = ""


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    channel: str = "app"


class FollowUpRequest(BaseModel):
    application_id: str
    language: Literal["en", "ar"] = "en"


class MessageClassificationRequest(BaseModel):
    subject: str = ""
    body: str
    known_company: str = ""
    application_id: str | None = None
    apply_confident_transition: bool = False


class SendMessageRequest(BaseModel):
    provider: Literal["gmail", "outlook"]
    approval_id: str
    to: str


class CalendarEventRequest(BaseModel):
    provider: Literal["gmail", "outlook"]
    application_id: str | None = None
    title: str
    start: str
    end: str
    timezone: str = "Africa/Cairo"
    description: str = ""
    location: str = ""


class CalendarEventExecuteRequest(CalendarEventRequest):
    approval_id: str


class InterviewCreateRequest(BaseModel):
    application_id: str | None = None
    title: str = ""
    company: str = ""
    description: str = ""
    profile: dict[str, Any] = Field(default_factory=dict)
    mode: Literal["hr", "behavioral", "technical", "case", "final"] = "behavioral"
    language: Literal["en", "ar"] = "en"


class InterviewTurnRequest(BaseModel):
    question: str
    answer: str
    duration_seconds: float = 0
    transcript_source: Literal["text", "voice"] = "text"
    evidence: dict[str, Any] = Field(default_factory=dict)
    language: Literal["en", "ar"] = "en"


class OfferCreateRequest(BaseModel):
    application_id: str | None = None
    company: str
    title: str
    currency: str = "EGP"
    pay_period: Literal["monthly", "annual", "hourly"] = "monthly"
    base_salary: float | None = None
    bonus: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    components: list[dict[str, Any]] = Field(default_factory=list)
    source_evidence: dict[str, Any] = Field(default_factory=dict)


class OfferDraftRequest(BaseModel):
    purpose: Literal["negotiate", "accept", "decline", "clarify"] = "negotiate"
    language: Literal["en", "ar"] = "en"


class OfferCompareRequest(BaseModel):
    offer_ids: list[str]
    weights: dict[str, float] = Field(default_factory=lambda: {"money": .3, "growth": .25, "stability": .15, "flexibility": .15, "location": .1, "role": .05})


class IntegrationUpdateRequest(BaseModel):
    account_label: str = ""
    status: str = "disconnected"
    scopes: list[str] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)


class OAuthStartRequest(BaseModel):
    redirect_uri: str


class OAuthCallbackRequest(BaseModel):
    code: str
    state: str
    redirect_uri: str


class TelegramConfigureRequest(BaseModel):
    bot_token: str
    chat_id: str


class TelegramSendRequest(BaseModel):
    title: str
    body: str
    buttons: list[dict[str, str]] = Field(default_factory=list)


class DevelopmentDiagnoseRequest(BaseModel):
    target_role: str
    domain: str = ""
    level: str = "entry"
    location: str = "Egypt"
    market_requirements: list[dict[str, Any]] = Field(default_factory=list)
    jobs: list[dict[str, Any]] = Field(default_factory=list)


class DevelopmentTaskProgressRequest(BaseModel):
    command: Literal["start", "complete", "snooze", "skip", "resume"]
    deliverable_url: str = ""
    deliverable_note: str = ""


class SkillAssessmentStartRequest(BaseModel):
    assessment_type: Literal["concept", "scenario", "project_defense", "mixed"] = "mixed"


class SkillAssessmentTurnRequest(BaseModel):
    answer: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class CVProposalDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]


class LearningOpportunitySyncRequest(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)


@router.get("/profile")
def get_profile(request: Request) -> dict[str, Any]:
    return repository.profile(current_user_id(request))


@router.patch("/profile")
def update_profile(payload: ProfileUpdate, request: Request) -> dict[str, Any]:
    try:
        return repository.update_profile(payload.model_dump(exclude_none=True), current_user_id(request))
    except Exception as exc:
        _raise(exc)


_PROFILE_QUESTIONS = (
    {"key": "full_name", "profile_key": "name", "label": {"en": "Full name", "ar": "الاسم الكامل"}, "question": {"en": "What full name should applications use?", "ar": "ما الاسم الكامل الذي تريد استخدامه في طلبات التقديم؟"}, "type": "text", "contexts": ["profile", "application"]},
    {"key": "phone", "profile_key": "phone", "label": {"en": "Phone number", "ar": "رقم الهاتف"}, "question": {"en": "What phone number should employers use?", "ar": "ما رقم الهاتف الذي يمكن لأصحاب العمل استخدامه؟"}, "type": "tel", "contexts": ["profile", "application"]},
    {"key": "location", "profile_key": "location", "label": {"en": "Current location", "ar": "الموقع الحالي"}, "question": {"en": "Where are you currently based?", "ar": "أين تقيم حاليًا؟"}, "type": "text", "contexts": ["profile", "search", "application"]},
    {"key": "target_role", "profile_key": "headline", "label": {"en": "Target role", "ar": "الوظيفة المستهدفة"}, "question": {"en": "What role are you targeting now?", "ar": "ما الوظيفة التي تستهدفها الآن؟"}, "type": "text", "contexts": ["profile", "search"]},
    {"key": "preferred_work_mode", "label": {"en": "Preferred work mode", "ar": "نظام العمل المفضل"}, "question": {"en": "Which work setup do you prefer?", "ar": "ما نظام العمل الذي تفضله؟"}, "type": "select", "options": {"en": ["Remote", "Hybrid", "On-site"], "ar": ["عن بُعد", "هجين", "من مقر العمل"]}, "contexts": ["profile", "search", "application"]},
    {"key": "work_authorization", "label": {"en": "Work authorization", "ar": "تصريح العمل"}, "question": {"en": "Are you legally authorized to work in your target market?", "ar": "هل لديك تصريح قانوني للعمل في السوق المستهدف؟"}, "type": "select", "options": {"en": ["Yes", "No"], "ar": ["نعم", "لا"]}, "contexts": ["profile", "application"]},
    {"key": "sponsorship_required", "label": {"en": "Visa sponsorship", "ar": "رعاية التأشيرة"}, "question": {"en": "Will you require visa sponsorship?", "ar": "هل ستحتاج إلى رعاية تأشيرة عمل؟"}, "type": "select", "options": {"en": ["Yes", "No"], "ar": ["نعم", "لا"]}, "contexts": ["profile", "application"]},
    {"key": "notice_period", "label": {"en": "Notice period", "ar": "مدة الإشعار"}, "question": {"en": "When could you start a new role?", "ar": "متى يمكنك بدء وظيفة جديدة؟"}, "type": "text", "contexts": ["profile", "application"]},
)


def _profile_completeness(user_id: str, context: str = "profile", requested_locale: str | None = None) -> dict[str, Any]:
    data = repository.profile(user_id)
    profile = dict(data.get("profile") or {})
    fact_items = list(data.get("facts") or [])
    facts = {str(item.get("fact_key") or ""): item for item in fact_items}
    locale = "ar" if (requested_locale or data.get("locale")) == "ar" else "en"
    known: dict[str, dict[str, str]] = {}
    candidates: list[dict[str, Any]] = []
    for spec in _PROFILE_QUESTIONS:
        key = str(spec["key"])
        profile_key = str(spec.get("profile_key") or "")
        related_facts = [item for alias in {key, profile_key} if alias and (item := facts.get(alias))]
        confirmed_fact = next((item for item in related_facts if item.get("confirmed")), None)
        cv_fact = next((item for item in related_facts if item.get("source") == "cv" and not item.get("confirmed")), None)
        value = str(
            (confirmed_fact or {}).get("value")
            or profile.get(profile_key)
            or (cv_fact or {}).get("value")
            or ""
        ).strip()
        if value and not cv_fact:
            known[key] = {"value": value, "source": "confirmed_answer" if confirmed_fact else "profile"}
            continue
        if context not in spec["contexts"] and context != "all":
            continue
        candidates.append({
            "memory_key": key,
            "label": spec["label"][locale],
            "fallback_question": spec["question"][locale],
            "input_type": spec["type"],
            "options": (spec.get("options") or {}).get(locale, []),
            "contexts": spec["contexts"],
            "existing_value": value if cv_fact else "",
        })
    active = get_active_document(user_id)
    cv_text = ""
    if active:
        try:
            cv_text = get_cv_text(str(active.get("document_id") or ""), user_id)
        except FileNotFoundError:
            active = None
    generated, analysis_source = generate_profile_questions(cv_text=cv_text, candidates=candidates, locale=locale)
    generated_by_key = {item["memory_key"]: item for item in generated}
    missing = []
    for candidate in candidates:
        question = generated_by_key.get(candidate["memory_key"], {})
        missing.append({
            "memory_key": candidate["memory_key"],
            "label": candidate["label"],
            "question": question.get("question") or candidate["fallback_question"],
            "reason": question.get("reason") or "",
            "kind": question.get("kind") or "missing",
            "inferred_value": question.get("inferred_value") or "",
            "generated_by": question.get("generated_by") or "fallback",
            "basis": question.get("basis") or ("explicit" if candidate.get("existing_value") else "missing"),
            "input_type": candidate["input_type"],
            "options": candidate["options"],
            "contexts": candidate["contexts"],
        })
    total = len(_PROFILE_QUESTIONS)
    return {
        "known": known,
        "missing": missing,
        "completed": len(known),
        "total": total,
        "percent": round(len(known) / total * 100),
        "context": context,
        "cv_reviewed": bool(active),
        "analysis_source": analysis_source,
    }


@router.get("/profile/completeness")
def profile_completeness(request: Request, context: str = "profile", locale: str | None = None) -> dict[str, Any]:
    return _profile_completeness(current_user_id(request), context, locale)


@router.post("/profile/answers")
def save_profile_answers(payload: ProfileAnswersRequest, request: Request) -> dict[str, Any]:
    from application_memory import application_answers, canonical_answer_key
    user_id = current_user_id(request)
    specs = {str(item["key"]): item for item in _PROFILE_QUESTIONS}
    profile_patch: dict[str, str] = {}
    saved: list[str] = []
    for raw_key, raw_value in payload.values.items():
        key = canonical_answer_key(raw_key)
        value = " ".join(str(raw_value).split())[:2000]
        if not key or not value or key not in specs:
            continue
        spec = specs[key]
        application_answers.remember(key, value, question=spec["question"]["en"], aliases=[spec["label"]["en"], spec["label"]["ar"]], user_id=user_id)
        repository.upsert_fact(
            key,
            value,
            category="profile",
            source="user_confirmed",
            evidence={"confirmation": "profile_prompt"},
            confirmed=True,
            cv_safe=False,
            user_id=user_id,
        )
        if spec.get("profile_key"):
            profile_patch[str(spec["profile_key"])] = value
        saved.append(key)
    if profile_patch:
        repository.update_profile({"profile": profile_patch}, user_id)
    return {"saved": saved, **_profile_completeness(user_id, "profile")}


@router.post("/career-facts")
def save_fact(payload: FactRequest, request: Request) -> dict[str, Any]:
    try:
        return repository.upsert_fact(**payload.model_dump(), user_id=current_user_id(request))
    except Exception as exc:
        _raise(exc)


@router.post("/development/diagnose")
def diagnose_readiness(payload: DevelopmentDiagnoseRequest, request: Request) -> dict[str, Any]:
    try:
        return development.diagnose(payload.model_dump(), current_user_id(request))
    except Exception as exc:
        _raise(exc)


@router.get("/development/readiness")
def get_readiness(request: Request) -> dict[str, Any]:
    return development.latest_readiness(current_user_id(request))


@router.post("/development/plan")
def create_development_plan(request: Request) -> dict[str, Any]:
    try:
        return development.create_plan(current_user_id(request))
    except Exception as exc:
        _raise(exc)


@router.get("/development/tasks")
def get_development_tasks(request: Request) -> dict[str, Any]:
    return development.list_tasks(current_user_id(request))


@router.post("/development/tasks/{task_id}/progress")
def update_development_task(task_id: str, payload: DevelopmentTaskProgressRequest, request: Request) -> dict[str, Any]:
    try:
        return development.update_task(task_id, payload.command, payload.model_dump(exclude={"command"}), current_user_id(request))
    except Exception as exc:
        _raise(exc)


@router.get("/development/opportunities")
def get_learning_opportunities(request: Request, include_watchlist: bool = True) -> dict[str, Any]:
    return development.learning_opportunities(include_watchlist, current_user_id(request))


@router.post("/development/opportunities/sync")
def sync_learning_opportunities(payload: LearningOpportunitySyncRequest, request: Request) -> dict[str, Any]:
    try:
        return development.sync_learning_opportunities(payload.items, current_user_id(request))
    except Exception as exc:
        _raise(exc)


@router.post("/development/tasks/{task_id}/assessment")
def start_skill_assessment(task_id: str, payload: SkillAssessmentStartRequest, request: Request) -> dict[str, Any]:
    try:
        return development.start_assessment(task_id, payload.assessment_type, current_user_id(request))
    except Exception as exc:
        _raise(exc)


@router.get("/development/assessments/{assessment_id}")
def get_skill_assessment(assessment_id: str, request: Request) -> dict[str, Any]:
    try:
        return development.get_assessment(assessment_id, current_user_id(request))
    except Exception as exc:
        _raise(exc)


@router.post("/development/assessments/{assessment_id}/turns")
def answer_skill_assessment(assessment_id: str, payload: SkillAssessmentTurnRequest, request: Request) -> dict[str, Any]:
    try:
        return development.answer_assessment(assessment_id, payload.answer, payload.evidence, current_user_id(request))
    except Exception as exc:
        _raise(exc)


@router.post("/development/assessments/{assessment_id}/finish")
def finish_skill_assessment(assessment_id: str, request: Request) -> dict[str, Any]:
    try:
        return development.finish_assessment(assessment_id, current_user_id(request))
    except Exception as exc:
        _raise(exc)


@router.post("/development/cv-proposals/{proposal_id}/decision")
def decide_cv_proposal(proposal_id: str, payload: CVProposalDecisionRequest, request: Request) -> dict[str, Any]:
    try:
        return development.decide_cv_proposal(proposal_id, payload.decision, current_user_id(request))
    except Exception as exc:
        _raise(exc)


@router.post("/development/recalculate")
def recalculate_readiness(request: Request) -> dict[str, Any]:
    try:
        return development.recalculate(current_user_id(request))
    except Exception as exc:
        _raise(exc)


@router.get("/opportunities/{opportunity_id}/readiness")
def get_opportunity_readiness(opportunity_id: str, request: Request) -> dict[str, Any]:
    try:
        return development.opportunity_readiness(opportunity_id, current_user_id(request))
    except Exception as exc:
        _raise(exc)


@router.get("/opportunities")
def list_opportunities(request: Request, status: str | None = None, limit: int = 100) -> dict[str, Any]:
    return {"items": repository.list_opportunities(status=status, limit=min(max(limit, 1), 500), user_id=current_user_id(request))}


@router.post("/opportunities/sync")
def sync_opportunities(payload: OpportunitySyncRequest, request: Request) -> dict[str, Any]:
    return {"items": repository.sync_opportunities(payload.jobs, user_id=current_user_id(request))}


@router.post("/opportunities/{opportunity_id}/status")
def set_opportunity_status(opportunity_id: str, payload: OpportunityStatusRequest, request: Request) -> dict[str, Any]:
    try:
        return repository.set_opportunity_status(opportunity_id, payload.status, current_user_id(request))
    except Exception as exc:
        _raise(exc)


@router.get("/applications")
def list_applications(request: Request, status: str | None = None) -> dict[str, Any]:
    return {"items": repository.list_applications(status=status, user_id=current_user_id(request)), "states": sorted(APPLICATION_STATES)}


@router.post("/applications")
def create_application(payload: ApplicationCreateRequest, request: Request) -> dict[str, Any]:
    try:
        return repository.create_application(payload.model_dump(), user_id=current_user_id(request))
    except Exception as exc:
        _raise(exc)


@router.get("/applications/{application_id}")
def get_application(application_id: str, request: Request) -> dict[str, Any]:
    try:
        return repository.get_application(application_id, current_user_id(request))
    except Exception as exc:
        _raise(exc)


@router.post("/applications/{application_id}/transition")
def transition_application(application_id: str, payload: TransitionRequest, request: Request) -> dict[str, Any]:
    try:
        return repository.transition_application(application_id, payload.status, source=payload.source, message=payload.message, evidence=payload.evidence, user_id=current_user_id(request))
    except Exception as exc:
        _raise(exc)


@router.get("/agent/actions")
def get_actions(request: Request, refresh: bool = True) -> dict[str, Any]:
    return {"items": repository.generate_next_actions(current_user_id(request)) if refresh else []}


@router.post("/agent/actions/{action_id}")
def command_action(action_id: str, payload: ActionCommandRequest, request: Request) -> dict[str, Any]:
    try:
        return repository.update_action(action_id, payload.command, snooze_hours=payload.snooze_hours, user_id=current_user_id(request))
    except Exception as exc:
        _raise(exc)


@router.post("/agent/actions/{action_id}/feedback")
def feedback_action(action_id: str, payload: ActionFeedbackRequest, request: Request) -> dict[str, Any]:
    try:
        return repository.feedback_action(action_id, payload.rating, payload.note, user_id=current_user_id(request))
    except Exception as exc:
        _raise(exc)


@router.get("/agent/approvals")
def get_approvals(request: Request, status: str = "pending") -> dict[str, Any]:
    return {"items": repository.list_approvals(status=status, user_id=current_user_id(request))}


@router.post("/agent/approvals")
def create_approval(payload: ApprovalCreateRequest, request: Request) -> dict[str, Any]:
    try:
        return repository.create_approval(**payload.model_dump(), user_id=current_user_id(request))
    except Exception as exc:
        _raise(exc)


@router.post("/agent/approvals/{approval_id}/decision")
def decide_approval(approval_id: str, payload: ApprovalDecisionRequest, request: Request) -> dict[str, Any]:
    try:
        return repository.decide_approval(approval_id, payload.decision, channel=payload.channel, user_id=current_user_id(request))
    except Exception as exc:
        _raise(exc)


@router.get("/agent-runs")
def get_agent_runs(request: Request) -> dict[str, Any]:
    return {"items": repository.list_agent_runs(current_user_id(request))}


@router.post("/communications/follow-up")
def create_follow_up(payload: FollowUpRequest, request: Request) -> dict[str, Any]:
    user_id = current_user_id(request)
    try:
        application = repository.get_application(payload.application_id, user_id)
        result = supervisor.follow_up_draft(application, language=payload.language)
        draft = repository.create_message_draft({"application_id": payload.application_id, "channel": "email", "purpose": "follow_up", **result.output, "evidence": {"application_id": payload.application_id, "provider": result.provider, "model": result.model}}, user_id=user_id)
        approval = repository.create_approval(action_type="send_message", summary=f"Send follow-up to {application['company'] or application['title']}", target_type="message_draft", target_id=draft["id"], payload={"subject": draft["subject"], "body": draft["body"]}, user_id=user_id)
        return {"draft": draft, "approval": approval, "generated": result.generated, "confidence": result.confidence}
    except Exception as exc:
        _raise(exc)


@router.post("/communications/classify")
def classify_message(payload: MessageClassificationRequest, request: Request) -> dict[str, Any]:
    user_id = current_user_id(request)
    try:
        result = supervisor.classify_recruiting_message(subject=payload.subject, body=payload.body, known_company=payload.known_company)
        transition = None
        mapping = {"rejected": "rejected", "interview": "interview", "offer": "offer", "reply": "recruiter_reply", "assessment": "screening"}
        if payload.application_id and payload.apply_confident_transition and result.confidence >= .85:
            transition = repository.transition_application(payload.application_id, mapping[result.output["kind"]], source="communication_agent", message=f"Detected {result.output['kind']} from recruiting message.", evidence={"quote": result.output["evidence_quote"], "confidence": result.confidence}, user_id=user_id)
        return {**result.output, "transition": transition}
    except Exception as exc:
        _raise(exc)


@router.post("/communications/{draft_id}/send")
async def send_approved_message(draft_id: str, payload: SendMessageRequest, request: Request) -> dict[str, Any]:
    user_id = current_user_id(request)
    try:
        draft = repository.get_message_draft(draft_id, user_id)
        if draft["status"] == "sent":
            return {"id": draft_id, "status": "sent", "already_sent": True}
        if not repository.approval_is_valid(payload.approval_id, "send_message", draft_id, user_id=user_id):
            raise ValueError("Sending requires an approved message request.")
        external_id = await integrations.send_email(payload.provider, to=payload.to, subject=draft["subject"], body=draft["body"], user_id=user_id)
        return repository.mark_message_sent(draft_id, payload.provider, external_id, user_id)
    except Exception as exc:
        _raise(exc)


@router.post("/communications/calendar/propose")
def propose_calendar_event(payload: CalendarEventRequest, request: Request) -> dict[str, Any]:
    user_id = current_user_id(request)
    try:
        event = payload.model_dump()
        target_id = payload.application_id or "unlinked"
        approval = repository.create_approval(
            action_type="create_calendar_event",
            summary=f"Add {payload.title} to {payload.provider.title()} calendar",
            target_type="application" if payload.application_id else "calendar_event",
            target_id=target_id,
            payload=event,
            user_id=user_id,
        )
        return {"event": event, "approval": approval}
    except Exception as exc:
        _raise(exc)


@router.post("/communications/calendar/create")
async def create_approved_calendar_event(payload: CalendarEventExecuteRequest, request: Request) -> dict[str, Any]:
    user_id = current_user_id(request)
    try:
        target_id = payload.application_id or "unlinked"
        approval = repository.get_approval(payload.approval_id, user_id)
        event_payload = payload.model_dump(exclude={"approval_id"})
        if not repository.approval_is_valid(payload.approval_id, "create_calendar_event", target_id, user_id=user_id):
            raise ValueError("Creating a calendar event requires an approved request.")
        if approval.get("payload") != event_payload:
            raise ValueError("Calendar details changed after approval. Create a new approval request.")
        result = await integrations.create_calendar_event(payload.provider, event_payload, user_id)
        return {**result, "approval_id": payload.approval_id}
    except Exception as exc:
        _raise(exc)


@router.get("/interviews")
def list_interviews(request: Request) -> dict[str, Any]:
    return {"items": repository.list_interviews(current_user_id(request))}


@router.post("/interviews")
def create_interview(payload: InterviewCreateRequest, request: Request) -> dict[str, Any]:
    user_id = current_user_id(request)
    try:
        result = supervisor.interview_plan(title=payload.title, company=payload.company, description=payload.description, profile=payload.profile, mode=payload.mode, language=payload.language)
        interview = repository.create_interview({"application_id": payload.application_id, "mode": payload.mode, "language": payload.language, "plan": {**result.output, "provider": result.provider, "model": result.model, "confidence": result.confidence}}, user_id=user_id)
        return interview
    except Exception as exc:
        _raise(exc)


@router.get("/interviews/{interview_id}")
def get_interview(interview_id: str, request: Request) -> dict[str, Any]:
    try:
        return repository.get_interview(interview_id, current_user_id(request))
    except Exception as exc:
        _raise(exc)


@router.post("/interviews/{interview_id}/turns")
def add_interview_turn(interview_id: str, payload: InterviewTurnRequest, request: Request) -> dict[str, Any]:
    user_id = current_user_id(request)
    try:
        result = supervisor.evaluate_interview_answer(question=payload.question, answer=payload.answer, duration_seconds=payload.duration_seconds, evidence=payload.evidence, language=payload.language)
        return repository.add_interview_turn(interview_id, payload.model_dump(), result.output, user_id=user_id)
    except Exception as exc:
        _raise(exc)


@router.post("/interviews/transcribe")
async def transcribe_interview_audio(request: Request, audio: UploadFile = File(...), language: str = "en") -> dict[str, Any]:
    current_user_id(request)
    suffix = Path(audio.filename or "answer.webm").suffix or ".webm"
    temp_path = ""
    try:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise HTTPException(503, "Voice transcription is not installed. Install the faster-whisper dependency.") from exc
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            temp_path = handle.name
            handle.write(await audio.read())
        model_name = os.getenv("WHISPER_MODEL", "base")
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
        segments, info = model.transcribe(temp_path, language=language if language in {"en", "ar"} else None, vad_filter=True)
        text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
        return {"text": text, "language": info.language, "duration": info.duration, "model": model_name, "local": True}
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)


@router.get("/offers")
def list_offers(request: Request) -> dict[str, Any]:
    return {"items": repository.list_offers(current_user_id(request))}


@router.post("/offers")
def create_offer(payload: OfferCreateRequest, request: Request) -> dict[str, Any]:
    try:
        return repository.create_offer(payload.model_dump(), user_id=current_user_id(request))
    except Exception as exc:
        _raise(exc)


@router.post("/offers/{offer_id}/draft")
def create_offer_draft(offer_id: str, payload: OfferDraftRequest, request: Request) -> dict[str, Any]:
    user_id = current_user_id(request)
    try:
        offer = next((item for item in repository.list_offers(user_id) if item["id"] == offer_id), None)
        if not offer:
            raise KeyError("Offer was not found.")
        result = supervisor.negotiation_draft(offer, purpose=payload.purpose, language=payload.language)
        sensitive = "respond_offer" if payload.purpose in {"accept", "decline"} else "send_negotiation"
        approval = repository.create_approval(action_type=sensitive, summary=f"Review {payload.purpose} response for {offer['company']}", target_type="offer", target_id=offer_id, payload=result.output, user_id=user_id)
        return {"draft": result.output, "approval": approval, "generated": result.generated, "confidence": result.confidence}
    except Exception as exc:
        _raise(exc)


@router.post("/offers/compare")
def compare_offers(payload: OfferCompareRequest, request: Request) -> dict[str, Any]:
    offers = [item for item in repository.list_offers(current_user_id(request)) if item["id"] in payload.offer_ids]
    if len(offers) < 2:
        raise HTTPException(422, "Choose at least two offers to compare.")
    currencies = {item["currency"] for item in offers}
    if len(currencies) != 1:
        return {"comparable": False, "reason": "Offers use different currencies. Add a dated, verified exchange rate before comparing money.", "items": offers}
    normalized = []
    for offer in offers:
        base = offer.get("base_salary")
        annual = None
        if isinstance(base, (int, float)):
            annual = base * 12 if offer["pay_period"] == "monthly" else base if offer["pay_period"] == "annual" else None
        details = offer.get("details") or {}
        normalized.append({**offer, "annual_base": annual, "non_monetary": {key: details.get(key, "Not stated") for key in ("growth", "stability", "flexibility", "location", "role")}})
    return {"comparable": True, "currency": next(iter(currencies)), "items": normalized, "weights": payload.weights, "source_note": "Only directly comparable base compensation was normalized. No exchange rate or benefit value was guessed."}


@router.get("/integrations")
def integration_status(request: Request) -> dict[str, Any]:
    return {"items": repository.integration_status(current_user_id(request))}


@router.get("/integrations/readiness")
def integration_readiness(request: Request) -> dict[str, Any]:
    current_user_id(request)
    google = bool(os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET"))
    microsoft = bool(os.getenv("MICROSOFT_CLIENT_ID") and os.getenv("MICROSOFT_CLIENT_SECRET"))
    smtp = bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM"))
    return {
        "providers": {
            "gmail": {"configured": google},
            "google_calendar": {"configured": google},
            "outlook": {"configured": microsoft},
            "outlook_calendar": {"configured": microsoft},
            "telegram": {"configured": True},
        },
        "password_email": {"configured": smtp},
    }


@router.put("/integrations/{provider}")
def update_integration(provider: str, payload: IntegrationUpdateRequest, request: Request) -> dict[str, Any]:
    try:
        return repository.update_integration(provider, payload.model_dump(), user_id=current_user_id(request))
    except Exception as exc:
        _raise(exc)


@router.post("/integrations/{provider}/oauth/start")
def start_oauth(provider: str, payload: OAuthStartRequest, request: Request) -> dict[str, str]:
    try:
        return integrations.oauth_authorization_url(provider, payload.redirect_uri, current_user_id(request))
    except Exception as exc:
        _raise(exc)


@router.post("/integrations/{provider}/oauth/callback")
async def oauth_callback(provider: str, payload: OAuthCallbackRequest, request: Request) -> dict[str, Any]:
    try:
        return await integrations.oauth_callback(provider, code=payload.code, state=payload.state, redirect_uri=payload.redirect_uri, user_id=current_user_id(request))
    except Exception as exc:
        _raise(exc)


@router.post("/integrations/{provider}/sync")
async def sync_provider(provider: str, request: Request) -> dict[str, Any]:
    try:
        return await integrations.sync_recruiting_mail(provider, supervisor, current_user_id(request))
    except Exception as exc:
        _raise(exc)


@router.post("/integrations/telegram/configure")
def configure_telegram(payload: TelegramConfigureRequest, request: Request) -> dict[str, Any]:
    try:
        return integrations.configure_telegram(**payload.model_dump(), user_id=current_user_id(request))
    except Exception as exc:
        _raise(exc)


@router.post("/integrations/telegram/send")
async def send_telegram(payload: TelegramSendRequest, request: Request) -> dict[str, Any]:
    try:
        return await integrations.send_telegram(**payload.model_dump(), user_id=current_user_id(request))
    except Exception as exc:
        _raise(exc)


@router.get("/analytics")
def analytics(request: Request) -> dict[str, Any]:
    return repository.analytics(current_user_id(request))
