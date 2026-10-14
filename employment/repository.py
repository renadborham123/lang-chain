"""Repository and lifecycle rules for local-first employment data."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from .database import SessionLocal, init_database
from .models import (
    AgentRun,
    Application,
    ApplicationArtifact,
    ApplicationEvent,
    ApprovalRequest,
    AuditEvent,
    CareerFact,
    CommunicationThread,
    Document,
    IntegrationAccount,
    Interview,
    InterviewTurn,
    MessageDraft,
    NextAction,
    Notification,
    Offer,
    OfferComponent,
    Opportunity,
    UserAccount,
    UserProfile,
    utcnow,
)


LOCAL_USER_ID = "local-user"

PRIMARY_APPLICATION_STATES = (
    "discovered", "saved", "preparing", "ready_to_apply", "applying", "needs_input",
    "ready_to_submit", "applied", "recruiter_reply", "screening", "interview",
    "final_interview", "offer", "accepted",
)
SIDE_APPLICATION_STATES = ("on_hold", "withdrawn", "rejected", "closed", "blocked", "failed", "expired")
APPLICATION_STATES = set(PRIMARY_APPLICATION_STATES + SIDE_APPLICATION_STATES)

_FORWARD_TRANSITIONS = {
    "discovered": {"saved", "preparing", "closed"},
    "saved": {"preparing", "withdrawn", "closed"},
    "preparing": {"ready_to_apply", "applying", "needs_input", "blocked", "withdrawn", "closed"},
    "ready_to_apply": {"applying", "withdrawn", "closed"},
    "applying": {"needs_input", "ready_to_submit", "blocked", "failed", "expired", "closed"},
    "needs_input": {"applying", "ready_to_submit", "blocked", "withdrawn", "expired"},
    "ready_to_submit": {"applied", "needs_input", "blocked", "failed", "withdrawn"},
    "applied": {"recruiter_reply", "screening", "interview", "rejected", "on_hold", "closed"},
    "recruiter_reply": {"screening", "interview", "rejected", "on_hold"},
    "screening": {"interview", "rejected", "on_hold", "withdrawn"},
    "interview": {"final_interview", "offer", "rejected", "on_hold", "withdrawn"},
    "final_interview": {"offer", "rejected", "on_hold", "withdrawn"},
    "offer": {"accepted", "rejected", "withdrawn", "on_hold"},
    "on_hold": set(APPLICATION_STATES) - {"accepted"},
    "blocked": {"applying", "needs_input", "ready_to_submit", "failed", "expired", "closed"},
    "failed": {"preparing", "applying", "closed"},
    "expired": {"preparing", "closed"},
}


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _safe_json(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return json.loads(json.dumps(value, default=str))


class EmploymentRepository:
    def __init__(self) -> None:
        init_database()
        self.ensure_user()

    def ensure_user(self, user_id: str = LOCAL_USER_ID) -> None:
        with SessionLocal.begin() as session:
            if session.get(UserProfile, user_id) is None:
                session.add(UserProfile(id=user_id, locale="en", country="EG", profile={}, preferences={}))

    def profile(self, user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        self.ensure_user(user_id)
        with SessionLocal() as session:
            row = session.get(UserProfile, user_id)
            facts = session.scalars(select(CareerFact).where(CareerFact.user_id == user_id)).all()
            return {
                "user_id": row.id,
                "locale": row.locale,
                "country": row.country,
                "profile": row.profile or {},
                "preferences": row.preferences or {},
                "facts": [self._fact_view(item) for item in facts],
                "updated_at": _iso(row.updated_at),
            }

    def update_profile(self, payload: dict[str, Any], user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        self.ensure_user(user_id)
        with SessionLocal.begin() as session:
            row = session.get(UserProfile, user_id)
            if "locale" in payload:
                locale = str(payload["locale"]).strip().lower()
                if locale not in {"en", "ar"}:
                    raise ValueError("Locale must be en or ar.")
                row.locale = locale
            if "country" in payload:
                country = str(payload["country"]).strip().upper()
                if country not in {"EG", "SA", "AE"}:
                    raise ValueError("Country must be EG, SA, or AE.")
                row.country = country
            if "profile" in payload:
                row.profile = {**(row.profile or {}), **dict(payload["profile"] or {})}
            if "preferences" in payload:
                row.preferences = {**(row.preferences or {}), **dict(payload["preferences"] or {})}
            row.updated_at = utcnow()
            self._audit(session, user_id, "profile.updated", "profile", user_id, payload)
        return self.profile(user_id)

    def capture_profile_data(self, values: dict[str, Any], *, source: str, user_id: str = LOCAL_USER_ID, document_id: str = "") -> dict[str, Any]:
        """Persist factual profile data discovered in a CV or explicitly entered form."""
        self.ensure_user(user_id)
        clean: dict[str, Any] = {}
        for key, value in dict(values or {}).items():
            if isinstance(value, list):
                normalized = [" ".join(str(item).split()) for item in value if str(item).strip()]
                if normalized:
                    clean[str(key)] = list(dict.fromkeys(normalized))[:100]
            elif isinstance(value, (str, int, float, bool)) and str(value).strip():
                clean[str(key)] = " ".join(str(value).split())[:4000]
        if not clean:
            return self.profile(user_id)
        if clean.get("full_name") and not clean.get("name"):
            clean["name"] = clean["full_name"]
        if clean.get("preferred_location") and not clean.get("location"):
            clean["location"] = clean["preferred_location"]
        if isinstance(clean.get("job_titles"), list) and clean["job_titles"] and not clean.get("headline"):
            clean["headline"] = clean["job_titles"][0]
        profile_keys = set(clean)
        demo_values = {"demo user", "maya hassan", "demo@jobflow.local", "+20 100 000 0000", "product designer", "testing the complete jobflow account flow."}
        with SessionLocal.begin() as session:
            row = session.get(UserProfile, user_id)
            stored = dict(row.profile or {})
            confirmed_keys = set(session.scalars(select(CareerFact.fact_key).where(CareerFact.user_id == user_id, CareerFact.source == "user_confirmed")).all())
            for key in profile_keys:
                old_value = str(stored.get(key) or "").strip()
                if key in clean and (source == "user_confirmed" or (source == "cv" and key not in confirmed_keys) or not old_value or old_value.casefold() in demo_values):
                    stored[key] = clean[key]
            row.profile = stored
            row.updated_at = utcnow()
            account = session.get(UserAccount, user_id)
            if account and clean.get("name") and account.display_name.casefold() in {"demo user", "maya hassan", "taylor"}:
                account.display_name = str(clean["name"])[:160]
                account.updated_at = utcnow()
        for key, value in clean.items():
            fact_value = ", ".join(value) if isinstance(value, list) else str(value)
            if key == "email":
                continue
            self.upsert_fact(
                key,
                fact_value,
                category="cv" if source == "cv" else "profile",
                source=source,
                evidence={"document_id": document_id} if document_id else {},
                confirmed=source == "user_confirmed",
                cv_safe=False,
                user_id=user_id,
            )
        return self.profile(user_id)

    def list_documents(self, user_id: str = LOCAL_USER_ID) -> list[dict[str, Any]]:
        with SessionLocal() as session:
            rows = session.scalars(select(Document).where(Document.user_id == user_id).order_by(Document.created_at.desc())).all()
            return [{
                "id": row.id,
                "kind": row.kind,
                "language": row.language,
                "source_name": row.source_name,
                "active": row.active,
                "metadata": row.metadata_json or {},
                "created_at": _iso(row.created_at),
            } for row in rows]

    def upsert_fact(self, fact_key: str, value: str, *, category: str = "profile", source: str = "user_confirmed", evidence: dict | None = None, confirmed: bool = True, cv_safe: bool = False, user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        self.ensure_user(user_id)
        clean_key = str(fact_key).strip().lower().replace(" ", "_")[:120]
        clean_value = " ".join(str(value).split())[:2000]
        if not clean_key or not clean_value:
            raise ValueError("Fact key and value are required.")
        with SessionLocal.begin() as session:
            row = session.scalar(select(CareerFact).where(CareerFact.user_id == user_id, CareerFact.fact_key == clean_key))
            if row is None:
                row = CareerFact(user_id=user_id, fact_key=clean_key, value=clean_value)
                session.add(row)
            row.value = clean_value
            row.category = category
            row.source = source
            row.evidence = _safe_json(evidence or {})
            row.confirmed = bool(confirmed)
            row.cv_safe = bool(cv_safe and confirmed)
            row.updated_at = utcnow()
            session.flush()
            self._audit(session, user_id, "career_fact.upserted", "career_fact", row.id, {"fact_key": clean_key, "confirmed": confirmed, "cv_safe": row.cv_safe})
            return self._fact_view(row)

    def sync_opportunities(self, jobs: Iterable[dict[str, Any]], *, user_id: str = LOCAL_USER_ID) -> list[dict[str, Any]]:
        self.ensure_user(user_id)
        output: list[dict[str, Any]] = []
        with SessionLocal.begin() as session:
            for job in jobs:
                external_id = str(job.get("id") or "").strip()
                if not external_id:
                    continue
                # Opportunity ids from job boards are not globally unique across
                # accounts. Namespace the storage id while retaining the provider
                # id in the payload for traceability.
                job_id = hashlib.sha256(f"{user_id}:{external_id}".encode()).hexdigest()[:40]
                row = session.get(Opportunity, job_id)
                if row is None:
                    row = Opportunity(id=job_id, user_id=user_id, title=str(job.get("title") or "Untitled"), url=str(job.get("url") or ""))
                    session.add(row)
                row.title = str(job.get("title") or row.title)
                row.company = str(job.get("company") or "")
                row.location = str(job.get("location") or "")
                row.url = str(job.get("url") or row.url)
                row.source = str(job.get("source") or "")
                row.opportunity_type = str(job.get("opportunity_type") or "job")
                row.status = "saved" if row.status == "saved" else "discovered"
                row.match_score = float(job.get("score") or 0)
                row.direct_listing = bool(job.get("direct_listing"))
                row.evidence = {
                    "match_reasons": job.get("match_reasons") or [],
                    "rule_reasons": job.get("rule_reasons") or [],
                    "keywords": job.get("keywords") or [],
                }
                row.payload = _safe_json({**job, "source_opportunity_id": external_id})
                row.updated_at = utcnow()
                output.append(self._opportunity_view(row))
        return output

    def set_opportunity_status(self, opportunity_id: str, status: str, user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        if status not in {"discovered", "saved", "dismissed"}:
            raise ValueError("Opportunity status must be discovered, saved, or dismissed.")
        with SessionLocal.begin() as session:
            row = session.get(Opportunity, opportunity_id)
            if row is None or row.user_id != user_id:
                raise KeyError("Opportunity was not found.")
            row.status = status
            row.updated_at = utcnow()
            self._audit(session, user_id, f"opportunity.{status}", "opportunity", row.id, {})
            return self._opportunity_view(row)

    def list_opportunities(self, *, status: str | None = None, limit: int = 100, user_id: str = LOCAL_USER_ID) -> list[dict[str, Any]]:
        with SessionLocal() as session:
            query = select(Opportunity).where(Opportunity.user_id == user_id)
            if status:
                query = query.where(Opportunity.status == status)
            rows = session.scalars(query.order_by(Opportunity.match_score.desc(), Opportunity.updated_at.desc()).limit(limit)).all()
            return [self._opportunity_view(row) for row in rows]

    def create_application(self, payload: dict[str, Any], *, user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        self.ensure_user(user_id)
        opportunity_id = str(payload.get("opportunity_id") or "").strip() or None
        with SessionLocal.begin() as session:
            existing = None
            if opportunity_id:
                existing = session.scalar(select(Application).where(Application.user_id == user_id, Application.opportunity_id == opportunity_id))
            if existing:
                return self._application_view(existing, events=self._events(session, existing.id))
            row = Application(
                user_id=user_id,
                opportunity_id=opportunity_id,
                title=str(payload.get("title") or "Untitled role"),
                company=str(payload.get("company") or ""),
                location=str(payload.get("location") or ""),
                url=str(payload.get("url") or ""),
                status=str(payload.get("status") or "preparing"),
                document_id=str(payload.get("document_id") or "") or None,
                source=str(payload.get("source") or ""),
                match_score=float(payload.get("match_score") or 0),
                payload=_safe_json(payload.get("payload") or {}),
            )
            if row.status not in APPLICATION_STATES:
                raise ValueError("Unsupported application status.")
            session.add(row)
            session.flush()
            session.add(ApplicationEvent(application_id=row.id, from_status="", to_status=row.status, source="system", message="Application workspace created."))
            self._audit(session, user_id, "application.created", "application", row.id, {"status": row.status})
            return self._application_view(row, events=[])

    def list_applications(self, *, status: str | None = None, user_id: str = LOCAL_USER_ID) -> list[dict[str, Any]]:
        with SessionLocal() as session:
            query = select(Application).where(Application.user_id == user_id)
            if status:
                query = query.where(Application.status == status)
            rows = session.scalars(query.order_by(Application.updated_at.desc())).all()
            return [self._application_view(row, events=self._events(session, row.id)) for row in rows]

    def get_application(self, application_id: str, user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        with SessionLocal() as session:
            row = session.get(Application, application_id)
            if row is None or row.user_id != user_id:
                raise KeyError("Application was not found.")
            return self._application_view(row, events=self._events(session, row.id))

    def save_application_session(self, session_id: str, application_id: str, payload: dict[str, Any], *, user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        """Persist a browser-session recovery checkpoint in the repository."""
        self.ensure_user(user_id)
        with SessionLocal.begin() as session:
            application = session.get(Application, application_id)
            if application is None or application.user_id != user_id:
                raise KeyError("Application was not found.")
            row = session.scalar(select(ApplicationArtifact).where(ApplicationArtifact.user_id == user_id, ApplicationArtifact.kind == "browser_session", ApplicationArtifact.name == session_id))
            if row is None:
                row = ApplicationArtifact(user_id=user_id, application_id=application_id, kind="browser_session", name=session_id)
                session.add(row)
            row.application_id = application_id
            row.payload = _safe_json(payload)
            row.updated_at = utcnow()
            session.flush()
            return {"id": row.id, "session_id": row.name, "application_id": row.application_id, "payload": row.payload, "updated_at": _iso(row.updated_at)}

    def list_application_sessions(self, *, recoverable_only: bool = False, user_id: str = LOCAL_USER_ID) -> list[dict[str, Any]]:
        terminal = {"submitted", "closed", "failed", "expired", "unavailable"}
        with SessionLocal() as session:
            rows = session.scalars(select(ApplicationArtifact).where(ApplicationArtifact.user_id == user_id, ApplicationArtifact.kind == "browser_session").order_by(ApplicationArtifact.updated_at.desc())).all()
            result = [{"id": row.id, "session_id": row.name, "application_id": row.application_id, "payload": row.payload or {}, "updated_at": _iso(row.updated_at)} for row in rows]
            return [item for item in result if str(item["payload"].get("status") or "") not in terminal] if recoverable_only else result

    def transition_application(self, application_id: str, to_status: str, *, source: str = "user", message: str = "", evidence: dict | None = None, force: bool = False, user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        if to_status not in APPLICATION_STATES:
            raise ValueError("Unsupported application status.")
        with SessionLocal.begin() as session:
            row = session.get(Application, application_id)
            if row is None or row.user_id != user_id:
                raise KeyError("Application was not found.")
            previous = row.status
            allowed = _FORWARD_TRANSITIONS.get(previous, set())
            if not force and previous != to_status and to_status not in allowed:
                raise ValueError(f"Cannot move an application from {previous} to {to_status}.")
            if previous != to_status:
                row.status = to_status
                row.updated_at = utcnow()
                if to_status == "applied" and row.applied_at is None:
                    row.applied_at = utcnow()
                session.add(ApplicationEvent(application_id=row.id, from_status=previous, to_status=to_status, source=source, message=message, evidence=_safe_json(evidence or {})))
                self._audit(session, user_id, "application.transitioned", "application", row.id, {"from": previous, "to": to_status, "source": source})
            session.flush()
            return self._application_view(row, events=self._events(session, row.id))

    def generate_next_actions(self, user_id: str = LOCAL_USER_ID) -> list[dict[str, Any]]:
        """Deterministic, evidence-led fallback for the supervisor agent."""
        with SessionLocal.begin() as session:
            existing = session.scalars(select(NextAction).where(NextAction.user_id == user_id, NextAction.status == "pending")).all()
            by_application = {(item.application_id, item.kind): item for item in existing}
            applications = session.scalars(select(Application).where(Application.user_id == user_id).order_by(Application.updated_at.desc())).all()
            now = utcnow()
            specs: list[tuple[Application, str, str, str, int, str, datetime | None]] = []
            for app in applications:
                age_days = max(0, (now - app.updated_at.replace(tzinfo=app.updated_at.tzinfo or timezone.utc)).days)
                if app.status in {"preparing", "ready_to_apply"}:
                    specs.append((app, "finish_application", f"Finish {app.company or app.title}", "Review the tailored CV and complete the application while the listing is current.", 95, "high", now))
                elif app.status in {"needs_input", "blocked"}:
                    specs.append((app, "resolve_blocker", f"Unblock {app.company or app.title}", "The application needs a factual answer, login, or human verification.", 100, "high", now))
                elif app.status == "ready_to_submit":
                    specs.append((app, "approve_submission", f"Review and submit {app.company or app.title}", "Every required field is complete. Final submission still needs your approval.", 100, "high", now))
                elif app.status == "applied" and age_days >= 5:
                    specs.append((app, "follow_up", f"Follow up with {app.company or app.title}", f"No response has been recorded for {age_days} days. Review a concise follow-up draft.", 80, "medium", now))
                elif app.status in {"screening", "interview", "final_interview"}:
                    specs.append((app, "practice_interview", f"Practice for {app.company or app.title}", "Run a role-specific mock interview using the listing and your confirmed evidence.", 90, "high", app.next_action_at or now))
                elif app.status == "offer":
                    specs.append((app, "review_offer", f"Review the offer from {app.company}", "Compare the full offer and prepare clarification or negotiation points before responding.", 100, "high", now))
            for app, kind, title, detail, priority, impact, due_at in specs:
                row = by_application.get((app.id, kind))
                if row is None:
                    row = NextAction(user_id=user_id, application_id=app.id, kind=kind, title=title)
                    session.add(row)
                row.title = title
                row.detail = detail
                row.priority = priority
                row.impact = impact
                row.confidence = 1
                row.due_at = due_at
                row.evidence = {"application_status": app.status, "application_updated_at": _iso(app.updated_at)}
            session.flush()
            rows = session.scalars(select(NextAction).where(NextAction.user_id == user_id, NextAction.status == "pending").order_by(NextAction.priority.desc(), NextAction.due_at.asc())).all()
            return [self._action_view(row) for row in rows]

    def update_action(self, action_id: str, command: str, *, snooze_hours: int = 24, user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        if command not in {"done", "dismiss", "snooze", "undo"}:
            raise ValueError("Command must be done, dismiss, snooze, or undo.")
        with SessionLocal.begin() as session:
            row = session.get(NextAction, action_id)
            if row is None or row.user_id != user_id:
                raise KeyError("Action was not found.")
            row.status = {"done": "done", "dismiss": "dismissed", "snooze": "pending", "undo": "pending"}[command]
            if command == "snooze":
                row.due_at = utcnow() + timedelta(hours=max(1, min(snooze_hours, 720)))
            row.updated_at = utcnow()
            self._audit(session, user_id, f"next_action.{command}", "next_action", row.id, {"snooze_hours": snooze_hours})
            return self._action_view(row)

    def feedback_action(self, action_id: str, rating: str, note: str = "", *, user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        allowed = {"useful", "wrong", "already_done", "not_relevant"}
        if rating not in allowed:
            raise ValueError("Feedback must be useful, wrong, already_done, or not_relevant.")
        with SessionLocal.begin() as session:
            row = session.get(NextAction, action_id)
            if row is None or row.user_id != user_id:
                raise KeyError("Action was not found.")
            evidence = dict(row.evidence or {})
            evidence["user_feedback"] = {"rating": rating, "note": note[:1000], "recorded_at": utcnow().isoformat()}
            row.evidence = evidence
            if rating == "already_done":
                row.status = "done"
            elif rating in {"wrong", "not_relevant"}:
                row.status = "dismissed"
            self._audit(session, user_id, "recommendation.feedback", "next_action", row.id, {"rating": rating, "note": note[:1000]})
            return self._action_view(row)

    def create_approval(self, *, action_type: str, summary: str, target_type: str = "", target_id: str = "", payload: dict | None = None, channel: str = "app", idempotency_key: str = "", user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        raw_key = idempotency_key or f"{user_id}:{action_type}:{target_type}:{target_id}:{json.dumps(payload or {}, sort_keys=True, default=str)}"
        key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        with SessionLocal.begin() as session:
            existing = session.scalar(select(ApprovalRequest).where(ApprovalRequest.idempotency_key == key))
            if existing:
                return self._approval_view(existing)
            row = ApprovalRequest(
                user_id=user_id,
                action_type=action_type,
                target_type=target_type,
                target_id=target_id,
                summary=summary,
                payload=_safe_json(payload or {}),
                channel=channel,
                idempotency_key=key,
                expires_at=utcnow() + timedelta(hours=24),
            )
            session.add(row)
            session.flush()
            self._audit(session, user_id, "approval.requested", "approval", row.id, {"action_type": action_type, "target_id": target_id})
            return self._approval_view(row)

    def decide_approval(self, approval_id: str, decision: str, *, channel: str = "app", user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        if decision not in {"approved", "rejected"}:
            raise ValueError("Decision must be approved or rejected.")
        with SessionLocal.begin() as session:
            row = session.get(ApprovalRequest, approval_id)
            if row is None or row.user_id != user_id:
                raise KeyError("Approval was not found.")
            if row.status != "pending":
                return self._approval_view(row)
            if row.expires_at and _as_utc(row.expires_at) < utcnow():
                row.status = "expired"
                raise ValueError("Approval has expired.")
            row.status = decision
            row.channel = channel
            row.decided_at = utcnow()
            self._audit(session, user_id, f"approval.{decision}", "approval", row.id, {"channel": channel})
            return self._approval_view(row)

    def approval_is_valid(self, approval_id: str, action_type: str, target_id: str = "", user_id: str = LOCAL_USER_ID) -> bool:
        with SessionLocal() as session:
            row = session.get(ApprovalRequest, approval_id)
            return bool(row and row.user_id == user_id and row.action_type == action_type and row.status == "approved" and (not target_id or row.target_id == target_id) and (not row.expires_at or _as_utc(row.expires_at) >= utcnow()))

    def get_approval(self, approval_id: str, user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        with SessionLocal() as session:
            row = session.get(ApprovalRequest, approval_id)
            if row is None or row.user_id != user_id:
                raise KeyError("Approval was not found.")
            return self._approval_view(row)

    def list_approvals(self, *, status: str = "pending", user_id: str = LOCAL_USER_ID) -> list[dict[str, Any]]:
        with SessionLocal() as session:
            rows = session.scalars(select(ApprovalRequest).where(ApprovalRequest.user_id == user_id, ApprovalRequest.status == status).order_by(ApprovalRequest.created_at.desc())).all()
            return [self._approval_view(row) for row in rows]

    def create_interview(self, payload: dict[str, Any], *, user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        with SessionLocal.begin() as session:
            row = Interview(user_id=user_id, application_id=payload.get("application_id"), mode=str(payload.get("mode") or "behavioral"), language=str(payload.get("language") or "en"), status="active", plan=_safe_json(payload.get("plan") or {}))
            session.add(row)
            session.flush()
            self._audit(session, user_id, "interview.created", "interview", row.id, {"mode": row.mode})
            return self._interview_view(row, [])

    def add_interview_turn(self, interview_id: str, payload: dict[str, Any], evaluation: dict[str, Any], *, user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        with SessionLocal.begin() as session:
            interview = session.get(Interview, interview_id)
            if interview is None or interview.user_id != user_id:
                raise KeyError("Interview was not found.")
            count = session.scalar(select(func.count()).select_from(InterviewTurn).where(InterviewTurn.interview_id == interview_id)) or 0
            row = InterviewTurn(interview_id=interview_id, sequence=count + 1, question=str(payload.get("question") or ""), answer=str(payload.get("answer") or ""), duration_seconds=float(payload.get("duration_seconds") or 0), transcript_source=str(payload.get("transcript_source") or "text"), evaluation=_safe_json(evaluation))
            session.add(row)
            session.flush()
            return self._turn_view(row)

    def get_interview(self, interview_id: str, user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        with SessionLocal() as session:
            row = session.get(Interview, interview_id)
            if row is None or row.user_id != user_id:
                raise KeyError("Interview was not found.")
            turns = session.scalars(select(InterviewTurn).where(InterviewTurn.interview_id == interview_id).order_by(InterviewTurn.sequence)).all()
            return self._interview_view(row, [self._turn_view(turn) for turn in turns])

    def list_interviews(self, user_id: str = LOCAL_USER_ID) -> list[dict[str, Any]]:
        with SessionLocal() as session:
            rows = session.scalars(select(Interview).where(Interview.user_id == user_id).order_by(Interview.created_at.desc())).all()
            return [self._interview_view(row, []) for row in rows]

    def create_offer(self, payload: dict[str, Any], *, user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        with SessionLocal.begin() as session:
            row = Offer(user_id=user_id, application_id=payload.get("application_id"), company=str(payload.get("company") or ""), title=str(payload.get("title") or ""), currency=str(payload.get("currency") or "EGP").upper(), pay_period=str(payload.get("pay_period") or "monthly"), base_salary=float(payload["base_salary"]) if payload.get("base_salary") not in {None, ""} else None, bonus=float(payload["bonus"]) if payload.get("bonus") not in {None, ""} else None, details=_safe_json(payload.get("details") or {}), source_evidence=_safe_json(payload.get("source_evidence") or {}))
            if row.currency not in {"EGP", "SAR", "AED", "USD", "EUR", "GBP"}:
                raise ValueError("Unsupported offer currency.")
            if row.pay_period not in {"monthly", "annual", "hourly"}:
                raise ValueError("Unsupported pay period.")
            session.add(row)
            session.flush()
            for item in payload.get("components") or []:
                session.add(OfferComponent(offer_id=row.id, kind=str(item.get("kind") or "benefit"), label=str(item.get("label") or "Benefit"), value=str(item.get("value") or "Not stated"), monetary_value=float(item["monetary_value"]) if item.get("monetary_value") not in {None, ""} else None, evidence=_safe_json(item.get("evidence") or {})))
            if row.application_id:
                app = session.get(Application, row.application_id)
                if app and app.status in {"interview", "final_interview", "recruiter_reply", "screening"}:
                    previous = app.status
                    app.status = "offer"
                    session.add(ApplicationEvent(application_id=app.id, from_status=previous, to_status="offer", source="offer_agent", message="Offer recorded."))
            self._audit(session, user_id, "offer.created", "offer", row.id, {"currency": row.currency, "pay_period": row.pay_period})
            return self._offer_view(session, row)

    def list_offers(self, user_id: str = LOCAL_USER_ID) -> list[dict[str, Any]]:
        with SessionLocal() as session:
            rows = session.scalars(select(Offer).where(Offer.user_id == user_id).order_by(Offer.created_at.desc())).all()
            return [self._offer_view(session, row) for row in rows]

    def create_message_draft(self, payload: dict[str, Any], *, user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        with SessionLocal.begin() as session:
            row = MessageDraft(user_id=user_id, application_id=payload.get("application_id"), channel=str(payload.get("channel") or "email"), purpose=str(payload.get("purpose") or "follow_up"), subject=str(payload.get("subject") or ""), body=str(payload.get("body") or ""), evidence=_safe_json(payload.get("evidence") or {}))
            session.add(row)
            session.flush()
            self._audit(session, user_id, "message.drafted", "message_draft", row.id, {"purpose": row.purpose})
            return {"id": row.id, "application_id": row.application_id, "channel": row.channel, "purpose": row.purpose, "subject": row.subject, "body": row.body, "status": row.status, "evidence": row.evidence, "created_at": _iso(row.created_at)}

    def get_message_draft(self, draft_id: str, user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        with SessionLocal() as session:
            row = session.get(MessageDraft, draft_id)
            if row is None or row.user_id != user_id:
                raise KeyError("Message draft was not found.")
            return {"id": row.id, "application_id": row.application_id, "channel": row.channel, "purpose": row.purpose, "subject": row.subject, "body": row.body, "status": row.status, "evidence": row.evidence or {}, "created_at": _iso(row.created_at)}

    def mark_message_sent(self, draft_id: str, provider: str, external_id: str, user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        with SessionLocal.begin() as session:
            row = session.get(MessageDraft, draft_id)
            if row is None or row.user_id != user_id:
                raise KeyError("Message draft was not found.")
            if row.status == "sent":
                return {"id": row.id, "status": row.status, "external_id": row.evidence.get("external_id")}
            row.status = "sent"
            row.evidence = {**(row.evidence or {}), "provider": provider, "external_id": external_id, "sent_at": _iso(utcnow())}
            self._audit(session, user_id, "message.sent", "message_draft", row.id, {"provider": provider, "external_id": external_id})
            return {"id": row.id, "status": row.status, "external_id": external_id}

    def record_communication(self, *, provider: str, external_id: str, subject: str, participants: dict[str, Any], payload: dict[str, Any], application_id: str | None = None, user_id: str = LOCAL_USER_ID) -> tuple[dict[str, Any], bool]:
        provider_external_id = external_id
        external_id = hashlib.sha256(f"{user_id}:{provider}:{provider_external_id}".encode()).hexdigest()
        with SessionLocal.begin() as session:
            existing = session.scalar(select(CommunicationThread).where(CommunicationThread.user_id == user_id, CommunicationThread.provider == provider, CommunicationThread.external_id == external_id))
            if existing:
                return {"id": existing.id, "application_id": existing.application_id, "provider": existing.provider, "external_id": existing.external_id, "subject": existing.subject}, False
            row = CommunicationThread(user_id=user_id, application_id=application_id, provider=provider, external_id=external_id, subject=subject, participants=_safe_json(participants), last_message_at=utcnow(), payload=_safe_json({**payload, "provider_external_id": provider_external_id}))
            session.add(row)
            session.flush()
            self._audit(session, user_id, "communication.ingested", "communication", row.id, {"provider": provider, "application_id": application_id})
            return {"id": row.id, "application_id": row.application_id, "provider": row.provider, "external_id": row.external_id, "subject": row.subject}, True

    def integration_status(self, user_id: str = LOCAL_USER_ID) -> list[dict[str, Any]]:
        providers = ("gmail", "outlook", "google_calendar", "outlook_calendar", "telegram")
        with SessionLocal.begin() as session:
            rows = {row.provider: row for row in session.scalars(select(IntegrationAccount).where(IntegrationAccount.user_id == user_id)).all()}
            for provider in providers:
                if provider not in rows:
                    row = IntegrationAccount(user_id=user_id, provider=provider)
                    session.add(row)
                    rows[provider] = row
            session.flush()
            return [{"id": row.id, "provider": row.provider, "account_label": row.account_label, "status": row.status, "scopes": row.scopes or [], "settings": row.settings or {}, "last_sync_at": _iso(row.last_sync_at)} for row in rows.values()]

    def update_integration(self, provider: str, payload: dict[str, Any], user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        allowed = {"gmail", "outlook", "google_calendar", "outlook_calendar", "telegram"}
        if provider not in allowed:
            raise ValueError("Unsupported integration provider.")
        with SessionLocal.begin() as session:
            row = session.scalar(select(IntegrationAccount).where(IntegrationAccount.user_id == user_id, IntegrationAccount.provider == provider))
            if row is None:
                row = IntegrationAccount(user_id=user_id, provider=provider)
                session.add(row)
            row.account_label = str(payload.get("account_label") or row.account_label)
            row.status = str(payload.get("status") or row.status)
            row.scopes = list(payload.get("scopes") or row.scopes or [])
            row.settings = _safe_json(payload.get("settings") or row.settings or {})
            row.last_sync_at = utcnow() if row.status == "connected" else row.last_sync_at
            session.flush()
            self._audit(session, user_id, "integration.updated", "integration", row.id, {"provider": provider, "status": row.status})
            return {"id": row.id, "provider": row.provider, "account_label": row.account_label, "status": row.status, "scopes": row.scopes, "settings": row.settings, "last_sync_at": _iso(row.last_sync_at)}

    def analytics(self, user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        with SessionLocal() as session:
            rows = session.scalars(select(Application).where(Application.user_id == user_id)).all()
        total = len(rows)
        applied = sum(row.status in {"applied", "recruiter_reply", "screening", "interview", "final_interview", "offer", "accepted", "rejected"} for row in rows)
        replies = sum(row.status in {"recruiter_reply", "screening", "interview", "final_interview", "offer", "accepted", "rejected"} for row in rows)
        interviews = sum(row.status in {"interview", "final_interview", "offer", "accepted"} for row in rows)
        offers = sum(row.status in {"offer", "accepted"} for row in rows)
        accepted = sum(row.status == "accepted" for row in rows)
        def rate(numerator: int, denominator: int) -> float:
            return round(numerator / denominator, 4) if denominator else 0
        bottleneck = "Build the first qualified application."
        if applied:
            bottleneck = "Improve employer response with tighter targeting and stronger evidence." if rate(replies, applied) < 0.2 else "Keep the current targeting strategy and focus on interview preparation."
        if interviews and rate(offers, interviews) < 0.25:
            bottleneck = "Interview conversion is the current constraint; prioritize role-specific practice."
        now = utcnow()

        def stage_counts(group: list[Application]) -> dict[str, Any]:
            group_total = len(group)
            group_applied = sum(row.status in {"applied", "recruiter_reply", "screening", "interview", "final_interview", "offer", "accepted", "rejected"} for row in group)
            group_replies = sum(row.status in {"recruiter_reply", "screening", "interview", "final_interview", "offer", "accepted", "rejected"} for row in group)
            group_interviews = sum(row.status in {"interview", "final_interview", "offer", "accepted"} for row in group)
            group_offers = sum(row.status in {"offer", "accepted"} for row in group)
            return {
                "tracked": group_total,
                "applied": group_applied,
                "replies": group_replies,
                "interviews": group_interviews,
                "offers": group_offers,
                "rates": {
                    "response": rate(group_replies, group_applied),
                    "interview": rate(group_interviews, group_replies),
                    "offer": rate(group_offers, group_interviews),
                },
            }

        dimensions: dict[str, dict[str, list[Application]]] = {key: {} for key in ("role", "location", "source", "cv_version", "match_band", "application_age")}
        for row in rows:
            match_band = "high" if row.match_score >= .8 else "medium" if row.match_score >= .6 else "low"
            age_days = max(0, (now - _as_utc(row.created_at)).days)
            age_band = "0-7 days" if age_days <= 7 else "8-30 days" if age_days <= 30 else "31+ days"
            values = {
                "role": row.title or "Not stated",
                "location": row.location or "Not stated",
                "source": row.source or "Not stated",
                "cv_version": row.document_id or "Not stated",
                "match_band": match_band,
                "application_age": age_band,
            }
            for dimension, value in values.items():
                dimensions[dimension].setdefault(value, []).append(row)
        segments = {dimension: {value: stage_counts(group) for value, group in groups.items()} for dimension, groups in dimensions.items()}
        return {
            "counts": {"tracked": total, "applied": applied, "replies": replies, "interviews": interviews, "offers": offers, "accepted": accepted},
            "rates": {"application_completion": rate(applied, total), "response": rate(replies, applied), "interview": rate(interviews, replies), "offer": rate(offers, interviews)},
            "segments": segments,
            "bottleneck": bottleneck,
            "sample_note": "Insights use confirmed application events only and become more reliable as outcomes are recorded.",
            "learning_policy": "Explainable calibration only. Protected attributes and demographic data are excluded.",
        }

    def list_agent_runs(self, user_id: str = LOCAL_USER_ID) -> list[dict[str, Any]]:
        with SessionLocal() as session:
            rows = session.scalars(select(AgentRun).where(AgentRun.user_id == user_id).order_by(AgentRun.started_at.desc()).limit(100)).all()
            return [{"id": row.id, "agent": row.agent, "task": row.task, "status": row.status, "provider": row.provider, "model": row.model, "prompt_version": row.prompt_version, "confidence": row.confidence, "evidence": row.evidence, "output": row.output, "error": row.error, "started_at": _iso(row.started_at), "completed_at": _iso(row.completed_at)} for row in rows]

    def record_agent_run(self, *, agent: str, task: str, provider: str, model: str, confidence: float, evidence: dict, output: dict, error: str = "", user_id: str = LOCAL_USER_ID) -> dict[str, Any]:
        with SessionLocal.begin() as session:
            row = AgentRun(user_id=user_id, agent=agent, task=task, status="failed" if error else "completed", provider=provider, model=model, confidence=max(0, min(1, confidence)), evidence=_safe_json(evidence), output=_safe_json(output), error=error, completed_at=utcnow())
            session.add(row)
            session.flush()
            return {"id": row.id, "status": row.status}

    @staticmethod
    def _events(session, application_id: str) -> list[dict[str, Any]]:
        rows = session.scalars(select(ApplicationEvent).where(ApplicationEvent.application_id == application_id).order_by(ApplicationEvent.created_at)).all()
        return [{"id": row.id, "from_status": row.from_status, "to_status": row.to_status, "source": row.source, "message": row.message, "evidence": row.evidence or {}, "created_at": _iso(row.created_at)} for row in rows]

    @staticmethod
    def _application_view(row: Application, events: list[dict[str, Any]]) -> dict[str, Any]:
        return {"id": row.id, "user_id": row.user_id, "opportunity_id": row.opportunity_id, "title": row.title, "company": row.company, "location": row.location, "url": row.url, "status": row.status, "document_id": row.document_id, "source": row.source, "match_score": row.match_score, "next_action_at": _iso(row.next_action_at), "applied_at": _iso(row.applied_at), "payload": row.payload or {}, "events": events, "created_at": _iso(row.created_at), "updated_at": _iso(row.updated_at)}

    @staticmethod
    def _opportunity_view(row: Opportunity) -> dict[str, Any]:
        return {"id": row.id, "title": row.title, "company": row.company, "location": row.location, "url": row.url, "source": row.source, "opportunity_type": row.opportunity_type, "status": row.status, "match_score": row.match_score, "direct_listing": row.direct_listing, "evidence": row.evidence or {}, "payload": row.payload or {}, "discovered_at": _iso(row.discovered_at), "updated_at": _iso(row.updated_at)}

    @staticmethod
    def _fact_view(row: CareerFact) -> dict[str, Any]:
        return {"id": row.id, "fact_key": row.fact_key, "value": row.value, "category": row.category, "source": row.source, "evidence": row.evidence or {}, "confirmed": row.confirmed, "cv_safe": row.cv_safe, "updated_at": _iso(row.updated_at)}

    @staticmethod
    def _action_view(row: NextAction) -> dict[str, Any]:
        return {"id": row.id, "application_id": row.application_id, "kind": row.kind, "title": row.title, "detail": row.detail, "priority": row.priority, "impact": row.impact, "confidence": row.confidence, "status": row.status, "due_at": _iso(row.due_at), "evidence": row.evidence or {}}

    @staticmethod
    def _approval_view(row: ApprovalRequest) -> dict[str, Any]:
        return {"id": row.id, "action_type": row.action_type, "target_type": row.target_type, "target_id": row.target_id, "summary": row.summary, "payload": row.payload or {}, "status": row.status, "channel": row.channel, "expires_at": _iso(row.expires_at), "decided_at": _iso(row.decided_at), "created_at": _iso(row.created_at)}

    @staticmethod
    def _interview_view(row: Interview, turns: list[dict[str, Any]]) -> dict[str, Any]:
        return {"id": row.id, "application_id": row.application_id, "mode": row.mode, "language": row.language, "status": row.status, "plan": row.plan or {}, "scheduled_at": _iso(row.scheduled_at), "turns": turns, "created_at": _iso(row.created_at)}

    @staticmethod
    def _turn_view(row: InterviewTurn) -> dict[str, Any]:
        return {"id": row.id, "sequence": row.sequence, "question": row.question, "answer": row.answer, "duration_seconds": row.duration_seconds, "transcript_source": row.transcript_source, "evaluation": row.evaluation or {}, "created_at": _iso(row.created_at)}

    @staticmethod
    def _offer_view(session, row: Offer) -> dict[str, Any]:
        components = session.scalars(select(OfferComponent).where(OfferComponent.offer_id == row.id)).all()
        return {"id": row.id, "application_id": row.application_id, "company": row.company, "title": row.title, "currency": row.currency, "pay_period": row.pay_period, "base_salary": row.base_salary, "bonus": row.bonus, "status": row.status, "details": row.details or {}, "source_evidence": row.source_evidence or {}, "components": [{"id": item.id, "kind": item.kind, "label": item.label, "value": item.value, "monetary_value": item.monetary_value, "evidence": item.evidence or {}} for item in components], "created_at": _iso(row.created_at), "updated_at": _iso(row.updated_at)}

    @staticmethod
    def _audit(session, user_id: str, action: str, target_type: str, target_id: str, detail: dict[str, Any]) -> None:
        session.add(AuditEvent(user_id=user_id, actor="user" if action.endswith(("updated", "approved", "rejected")) else "system", action=action, target_type=target_type, target_id=target_id, detail=_safe_json(detail)))


repository = EmploymentRepository()
