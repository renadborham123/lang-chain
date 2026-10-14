"""Persistent domain models for the complete employment journey."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class UserProfile(Base):
    __tablename__ = "user_profiles"
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default="local-user")
    locale: Mapped[str] = mapped_column(String(10), default="en")
    country: Mapped[str] = mapped_column(String(3), default="EG")
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class UserAccount(Base):
    __tablename__ = "user_accounts"
    user_id: Mapped[str] = mapped_column(String(80), ForeignKey("user_profiles.id", ondelete="CASCADE"), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(String(160))
    avatar_path: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(80), ForeignKey("user_accounts.user_id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PasswordReset(Base):
    __tablename__ = "password_resets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(80), ForeignKey("user_accounts.user_id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CareerFact(Base):
    __tablename__ = "career_facts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(80), ForeignKey("user_profiles.id"), index=True)
    fact_key: Mapped[str] = mapped_column(String(120))
    value: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(80), default="profile")
    source: Mapped[str] = mapped_column(String(80), default="user_confirmed")
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=True)
    cv_safe: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __table_args__ = (UniqueConstraint("user_id", "fact_key", name="uq_fact_user_key"),)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(80), ForeignKey("user_profiles.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40), default="cv")
    language: Mapped[str] = mapped_column(String(10), default="en")
    source_name: Mapped[str] = mapped_column(String(255), default="document")
    text_path: Mapped[str] = mapped_column(Text, default="")
    file_path: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Opportunity(Base):
    __tablename__ = "opportunities"
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(80), ForeignKey("user_profiles.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    company: Mapped[str] = mapped_column(String(240), default="")
    location: Mapped[str] = mapped_column(String(240), default="")
    url: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(100), default="")
    opportunity_type: Mapped[str] = mapped_column(String(80), default="job")
    status: Mapped[str] = mapped_column(String(40), default="discovered")
    match_score: Mapped[float] = mapped_column(Float, default=0)
    direct_listing: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __table_args__ = (Index("ix_opportunity_user_status", "user_id", "status"),)


class Application(Base):
    __tablename__ = "applications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(80), ForeignKey("user_profiles.id"), index=True)
    opportunity_id: Mapped[str | None] = mapped_column(String(160), ForeignKey("opportunities.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    company: Mapped[str] = mapped_column(String(240), default="")
    location: Mapped[str] = mapped_column(String(240), default="")
    url: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="preparing", index=True)
    document_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source: Mapped[str] = mapped_column(String(100), default="")
    match_score: Mapped[float] = mapped_column(Float, default=0)
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    events: Mapped[list["ApplicationEvent"]] = relationship(back_populates="application", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("user_id", "opportunity_id", name="uq_application_user_opportunity"),)


class ApplicationEvent(Base):
    __tablename__ = "application_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    application_id: Mapped[str] = mapped_column(String(36), ForeignKey("applications.id"), index=True)
    from_status: Mapped[str] = mapped_column(String(40), default="")
    to_status: Mapped[str] = mapped_column(String(40))
    source: Mapped[str] = mapped_column(String(80), default="user")
    message: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    application: Mapped[Application] = relationship(back_populates="events")


class ApplicationArtifact(Base):
    __tablename__ = "application_artifacts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(80), ForeignKey("user_profiles.id"), index=True)
    application_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("applications.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(240))
    file_path: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __table_args__ = (UniqueConstraint("user_id", "kind", "name", name="uq_artifact_user_kind_name"),)


class NextAction(Base):
    __tablename__ = "next_actions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(80), ForeignKey("user_profiles.id"), index=True)
    application_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("applications.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(300))
    detail: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[int] = mapped_column(Integer, default=50)
    impact: Mapped[str] = mapped_column(String(40), default="medium")
    confidence: Mapped[float] = mapped_column(Float, default=1)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(80), ForeignKey("user_profiles.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(80))
    target_type: Mapped[str] = mapped_column(String(80), default="")
    target_id: Mapped[str] = mapped_column(String(160), default="")
    summary: Mapped[str] = mapped_column(String(400))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True)
    channel: Mapped[str] = mapped_column(String(30), default="app")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(80), ForeignKey("user_profiles.id"), index=True)
    agent: Mapped[str] = mapped_column(String(80))
    task: Mapped[str] = mapped_column(String(160), default="")
    status: Mapped[str] = mapped_column(String(30), default="running")
    provider: Mapped[str] = mapped_column(String(80), default="deterministic")
    model: Mapped[str] = mapped_column(String(160), default="")
    prompt_version: Mapped[str] = mapped_column(String(40), default="v1")
    confidence: Mapped[float] = mapped_column(Float, default=1)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(80), ForeignKey("user_profiles.id"), index=True)
    actor: Mapped[str] = mapped_column(String(80), default="system")
    action: Mapped[str] = mapped_column(String(120))
    target_type: Mapped[str] = mapped_column(String(80), default="")
    target_id: Mapped[str] = mapped_column(String(160), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Contact(Base):
    __tablename__ = "contacts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(80), ForeignKey("user_profiles.id"), index=True)
    application_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("applications.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(240), default="")
    role: Mapped[str] = mapped_column(String(240), default="")
    channel: Mapped[str] = mapped_column(String(40), default="email")
    destination: Mapped[str] = mapped_column(String(500), default="")
    source_url: Mapped[str] = mapped_column(Text, default="")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CommunicationThread(Base):
    __tablename__ = "communication_threads"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(80), ForeignKey("user_profiles.id"), index=True)
    application_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("applications.id"), nullable=True)
    provider: Mapped[str] = mapped_column(String(40), default="manual")
    external_id: Mapped[str] = mapped_column(String(300), default="")
    subject: Mapped[str] = mapped_column(String(500), default="")
    participants: Mapped[dict] = mapped_column(JSON, default=dict)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("provider", "external_id", name="uq_communication_external"),)


class MessageDraft(Base):
    __tablename__ = "message_drafts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(80), ForeignKey("user_profiles.id"), index=True)
    application_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("applications.id"), nullable=True)
    channel: Mapped[str] = mapped_column(String(40), default="email")
    purpose: Mapped[str] = mapped_column(String(80), default="follow_up")
    subject: Mapped[str] = mapped_column(String(500), default="")
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Interview(Base):
    __tablename__ = "interviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(80), ForeignKey("user_profiles.id"), index=True)
    application_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("applications.id"), nullable=True)
    mode: Mapped[str] = mapped_column(String(40), default="behavioral")
    language: Mapped[str] = mapped_column(String(10), default="en")
    status: Mapped[str] = mapped_column(String(30), default="planned")
    plan: Mapped[dict] = mapped_column(JSON, default=dict)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InterviewTurn(Base):
    __tablename__ = "interview_turns"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    interview_id: Mapped[str] = mapped_column(String(36), ForeignKey("interviews.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text, default="")
    duration_seconds: Mapped[float] = mapped_column(Float, default=0)
    transcript_source: Mapped[str] = mapped_column(String(40), default="text")
    evaluation: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Offer(Base):
    __tablename__ = "offers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(80), ForeignKey("user_profiles.id"), index=True)
    application_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("applications.id"), nullable=True)
    company: Mapped[str] = mapped_column(String(240))
    title: Mapped[str] = mapped_column(String(300))
    currency: Mapped[str] = mapped_column(String(3), default="EGP")
    pay_period: Mapped[str] = mapped_column(String(20), default="monthly")
    base_salary: Mapped[float | None] = mapped_column(Float, nullable=True)
    bonus: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="received")
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    source_evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class OfferComponent(Base):
    __tablename__ = "offer_components"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    offer_id: Mapped[str] = mapped_column(String(36), ForeignKey("offers.id"), index=True)
    kind: Mapped[str] = mapped_column(String(80))
    label: Mapped[str] = mapped_column(String(240))
    value: Mapped[str] = mapped_column(Text)
    monetary_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)


class NegotiationDraft(Base):
    __tablename__ = "negotiation_drafts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    offer_id: Mapped[str] = mapped_column(String(36), ForeignKey("offers.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(40), default="negotiate")
    subject: Mapped[str] = mapped_column(String(500), default="")
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IntegrationAccount(Base):
    __tablename__ = "integration_accounts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(80), ForeignKey("user_profiles.id"), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    account_label: Mapped[str] = mapped_column(String(240), default="")
    status: Mapped[str] = mapped_column(String(30), default="disconnected")
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_integration_user_provider"),)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(80), ForeignKey("user_profiles.id"), index=True)
    channel: Mapped[str] = mapped_column(String(30), default="app")
    kind: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OutcomeMetric(Base):
    __tablename__ = "outcome_metrics"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(80), ForeignKey("user_profiles.id"), index=True)
    metric: Mapped[str] = mapped_column(String(80))
    dimension: Mapped[str] = mapped_column(String(120), default="all")
    value: Mapped[float] = mapped_column(Float, default=0)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# Qualification-loop models.  The public product is Wazzefni, while these
# internal table names intentionally remain neutral to avoid a destructive
# rebrand migration.
class TargetRole(Base):
    __tablename__ = "target_roles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(80), ForeignKey("user_profiles.id"), index=True)
    title: Mapped[str] = mapped_column(String(240))
    domain: Mapped[str] = mapped_column(String(160), default="")
    level: Mapped[str] = mapped_column(String(40), default="entry")
    location: Mapped[str] = mapped_column(String(160), default="Egypt")
    country: Mapped[str] = mapped_column(String(3), default="EG")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __table_args__ = (Index("ix_target_role_user_active", "user_id", "active"),)


class MarketRequirement(Base):
    __tablename__ = "market_requirements"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    target_role_id: Mapped[str] = mapped_column(String(36), ForeignKey("target_roles.id", ondelete="CASCADE"), index=True)
    skill_key: Mapped[str] = mapped_column(String(120))
    label: Mapped[str] = mapped_column(String(160))
    frequency: Mapped[float] = mapped_column(Float, default=0)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    importance: Mapped[float] = mapped_column(Float, default=.5)
    hard_requirement: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("target_role_id", "skill_key", name="uq_market_requirement_role_skill"),)


class SkillEvidence(Base):
    __tablename__ = "skill_evidence"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(80), ForeignKey("user_profiles.id"), index=True)
    skill_key: Mapped[str] = mapped_column(String(120), index=True)
    label: Mapped[str] = mapped_column(String(160))
    level: Mapped[str] = mapped_column(String(40), default="exposed")
    source_type: Mapped[str] = mapped_column(String(60), default="user_confirmed")
    source_id: Mapped[str] = mapped_column(String(160), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __table_args__ = (UniqueConstraint("user_id", "skill_key", name="uq_skill_evidence_user_skill"),)


class DevelopmentPlan(Base):
    __tablename__ = "development_plans"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(80), ForeignKey("user_profiles.id"), index=True)
    target_role_id: Mapped[str] = mapped_column(String(36), ForeignKey("target_roles.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(30), default="active")
    summary: Mapped[str] = mapped_column(Text, default="")
    rationale: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __table_args__ = (Index("ix_development_plan_user_status", "user_id", "status"),)


class DevelopmentTask(Base):
    __tablename__ = "development_tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(80), ForeignKey("user_profiles.id"), index=True)
    plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("development_plans.id", ondelete="CASCADE"), index=True)
    skill_key: Mapped[str] = mapped_column(String(120), default="")
    task_type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(300))
    detail: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    dependencies: Mapped[list] = mapped_column(JSON, default=list)
    deliverable: Mapped[str] = mapped_column(Text, default="")
    assessment_method: Mapped[str] = mapped_column(Text, default="")
    readiness_impact: Mapped[float] = mapped_column(Float, default=0)
    market_evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    unlocks: Mapped[list] = mapped_column(JSON, default=list)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __table_args__ = (Index("ix_development_task_plan_status", "plan_id", "status"),)


class LearningOpportunity(Base):
    __tablename__ = "learning_opportunities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(80), ForeignKey("user_profiles.id"), index=True)
    provider: Mapped[str] = mapped_column(String(180))
    title: Mapped[str] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(40), default="official")
    opportunity_type: Mapped[str] = mapped_column(String(60), default="training")
    status: Mapped[str] = mapped_column(String(40), default="needs_verification")
    requirements: Mapped[list] = mapped_column(JSON, default=list)
    skill_tags: Mapped[list] = mapped_column(JSON, default=list)
    cost: Mapped[str] = mapped_column(String(120), default="Not stated")
    location: Mapped[str] = mapped_column(String(180), default="Not stated")
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    relevance: Mapped[float] = mapped_column(Float, default=0)
    eligibility_readiness: Mapped[float] = mapped_column(Float, default=0)
    source_evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __table_args__ = (UniqueConstraint("user_id", "url", name="uq_learning_opportunity_user_url"),)


class SkillAssessment(Base):
    __tablename__ = "skill_assessments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(80), ForeignKey("user_profiles.id"), index=True)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("development_tasks.id"), index=True)
    skill_key: Mapped[str] = mapped_column(String(120))
    assessment_type: Mapped[str] = mapped_column(String(50), default="concept")
    status: Mapped[str] = mapped_column(String(30), default="active")
    outcome: Mapped[str] = mapped_column(String(30), default="pending")
    rubric: Mapped[dict] = mapped_column(JSON, default=dict)
    scores: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AssessmentTurn(Base):
    __tablename__ = "assessment_turns"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    assessment_id: Mapped[str] = mapped_column(String(36), ForeignKey("skill_assessments.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    question_type: Mapped[str] = mapped_column(String(40), default="concept")
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text, default="")
    evaluation: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReadinessSnapshot(Base):
    __tablename__ = "readiness_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(80), ForeignKey("user_profiles.id"), index=True)
    target_role_id: Mapped[str] = mapped_column(String(36), ForeignKey("target_roles.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    role_readiness: Mapped[float] = mapped_column(Float, default=0)
    evidence_strength: Mapped[float] = mapped_column(Float, default=0)
    cv_representation: Mapped[float] = mapped_column(Float, default=0)
    covered_requirements: Mapped[list] = mapped_column(JSON, default=list)
    missing_requirements: Mapped[list] = mapped_column(JSON, default=list)
    hard_gaps: Mapped[list] = mapped_column(JSON, default=list)
    explanation: Mapped[str] = mapped_column(Text, default="")
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("target_role_id", "version", name="uq_readiness_role_version"),)


class CareerMilestone(Base):
    __tablename__ = "career_milestones"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(80), ForeignKey("user_profiles.id"), index=True)
    plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("development_plans.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="locked")
    unlock_rule: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CVChangeProposal(Base):
    __tablename__ = "cv_change_proposals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(80), ForeignKey("user_profiles.id"), index=True)
    assessment_id: Mapped[str] = mapped_column(String(36), ForeignKey("skill_assessments.id"), index=True)
    skill_key: Mapped[str] = mapped_column(String(120))
    section: Mapped[str] = mapped_column(String(60), default="skills")
    old_text: Mapped[str] = mapped_column(Text, default="")
    proposed_text: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
