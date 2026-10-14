"""Idempotent import of legacy local Jobflow memory into the relational store."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text, update

from .database import SessionLocal, init_database
from .models import CareerFact, Document, Opportunity, UserAccount, UserProfile
from .repository import LOCAL_USER_ID, EmploymentRepository, repository


_ROOT = Path(__file__).resolve().parents[1]
_MEMORY = _ROOT / "memory"


def _read(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def migrate_legacy_data(repo: EmploymentRepository | None = None) -> dict[str, int]:
    repo = repo or repository
    init_database()
    counts = {"profile": 0, "facts": 0, "answers": 0, "documents": 0}
    import_user_id = LOCAL_USER_ID
    enabled_default = "false" if os.getenv("JOBFLOW_ENV", "development").lower() == "production" else "true"
    if os.getenv("JOBFLOW_CLAIM_LOCAL_DATA", enabled_default).lower() == "true":
        with SessionLocal() as session:
            account_ids = session.scalars(select(UserAccount.user_id)).all()
        if len(account_ids) == 1:
            import_user_id = account_ids[0]
    if import_user_id != LOCAL_USER_ID:
        with SessionLocal() as session:
            already_imported = session.scalar(select(CareerFact.id).where(CareerFact.user_id == import_user_id, CareerFact.source.in_(("legacy_career_memory", "legacy_application_memory"))))
            has_documents = session.scalar(select(Document.id).where(Document.user_id == import_user_id))
        if already_imported and has_documents:
            counts["claimed"] = claim_legacy_workspace_data(repo)
            return counts

    profiles = _read(_MEMORY / "profiles.json")
    if profiles:
        best = next((value for value in reversed(list(profiles.values())) if isinstance(value, dict)), None)
        if best:
            repo.update_profile({"profile": best}, import_user_id)
            counts["profile"] = 1

    career = _read(_MEMORY / "career_answers.json").get("documents", {})
    if isinstance(career, dict):
        for document in career.values():
            answers = document.get("answers", {}) if isinstance(document, dict) else {}
            for key, item in answers.items():
                if not isinstance(item, dict) or not str(item.get("value") or "").strip():
                    continue
                repo.upsert_fact(
                    str(key), str(item["value"]), category=str(item.get("kind") or "profile"),
                    source="legacy_career_memory", evidence={"question": item.get("question"), "subject": item.get("subject")},
                    confirmed=True, cv_safe=bool(item.get("cv_safe")),
                    user_id=import_user_id,
                )
                counts["facts"] += 1

    application = _read(_MEMORY / "application_answers.json").get("answers", {})
    if isinstance(application, dict):
        for key, item in application.items():
            if isinstance(item, dict) and str(item.get("value") or "").strip():
                repo.upsert_fact(str(key), str(item["value"]), category="application_answer", source="legacy_application_memory", evidence={"question": item.get("question"), "aliases": item.get("aliases")}, confirmed=True, cv_safe=False, user_id=import_user_id)
                counts["answers"] += 1

    documents_path = _MEMORY / "documents"
    if documents_path.is_dir():
        with SessionLocal.begin() as session:
            for meta_path in documents_path.glob("*.json"):
                document_id = meta_path.stem
                if session.get(Document, document_id):
                    continue
                metadata = _read(meta_path)
                session.add(Document(
                    id=document_id,
                    user_id=import_user_id,
                    kind="cv",
                    language=str(metadata.get("language") or "en"),
                    source_name=str(metadata.get("source_name") or "Saved CV"),
                    text_path=str(documents_path / f"{document_id}.txt"),
                    file_path=str(documents_path / f"{document_id}.pdf"),
                    metadata_json=metadata,
                    active=False,
                ))
                counts["documents"] += 1
    counts["claimed"] = claim_legacy_workspace_data(repo)
    return counts


def claim_legacy_workspace_data(repo: EmploymentRepository | None = None) -> int:
    """Attach pre-account employment data to the sole local development account.

    This is deliberately disabled by default in production and only runs when the
    destination account has no career data, avoiding ambiguous ownership.
    """
    repo = repo or repository
    enabled_default = "false" if os.getenv("JOBFLOW_ENV", "development").lower() == "production" else "true"
    if os.getenv("JOBFLOW_CLAIM_LOCAL_DATA", enabled_default).lower() != "true":
        return 0
    with SessionLocal() as session:
        account_ids = session.scalars(select(UserAccount.user_id)).all()
        if len(account_ids) != 1:
            return 0
        target_id = account_ids[0]
        if target_id == LOCAL_USER_ID:
            return 0
        target_has_data = any((
            session.scalar(select(func.count()).select_from(Document).where(Document.user_id == target_id)) or 0,
            session.scalar(select(func.count()).select_from(CareerFact).where(CareerFact.user_id == target_id)) or 0,
            session.scalar(select(func.count()).select_from(Opportunity).where(Opportunity.user_id == target_id)) or 0,
        ))
        if target_has_data:
            return 0
        legacy_count = session.scalar(select(func.count()).select_from(Document).where(Document.user_id == LOCAL_USER_ID)) or 0
        legacy_count += session.scalar(select(func.count()).select_from(CareerFact).where(CareerFact.user_id == LOCAL_USER_ID)) or 0
        legacy_count += session.scalar(select(func.count()).select_from(Opportunity).where(Opportunity.user_id == LOCAL_USER_ID)) or 0
        if not legacy_count:
            return 0

    employment_tables = (
        "agent_runs", "application_artifacts", "applications", "approval_requests", "audit_events",
        "career_facts", "career_milestones", "communication_threads", "contacts", "cv_change_proposals",
        "development_plans", "development_tasks", "documents", "interviews", "learning_opportunities",
        "message_drafts", "next_actions", "notifications", "offers", "opportunities", "outcome_metrics",
        "readiness_snapshots", "skill_assessments", "skill_evidence", "target_roles",
    )
    moved = 0
    with SessionLocal.begin() as session:
        legacy = session.get(UserProfile, LOCAL_USER_ID)
        target = session.get(UserProfile, target_id)
        if legacy and target:
            existing = dict(target.profile or {})
            for key, value in dict(legacy.profile or {}).items():
                if value not in (None, "", [], {}) and key not in existing:
                    existing[key] = value
            target.profile = existing
            if not target.country and legacy.country:
                target.country = legacy.country
        for table in employment_tables:
            result = session.execute(text(f'UPDATE "{table}" SET user_id = :target WHERE user_id = :legacy'), {"target": target_id, "legacy": LOCAL_USER_ID})
            moved += int(result.rowcount or 0)
        active_id = str(_read(_MEMORY / "active_cv.json").get("document_id") or "")
        if active_id:
            session.execute(update(Document).where(Document.user_id == target_id).values(active=False))
            session.execute(update(Document).where(Document.user_id == target_id, Document.id == active_id).values(active=True))
    return moved
