"""Persistent local background work for proactive employment actions."""

from __future__ import annotations

import os

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler

from .database import DATABASE_URL
from .database import SessionLocal
from .models import IntegrationAccount
from .repository import repository
from sqlalchemy import select


_scheduler: BackgroundScheduler | None = None


def refresh_next_actions() -> None:
    with SessionLocal() as session:
        user_ids = session.scalars(select(IntegrationAccount.user_id).distinct()).all()
        # Profiles without integrations still need their local action queue.
        from .models import UserProfile
        user_ids.extend(session.scalars(select(UserProfile.id)).all())
    for user_id in set(user_ids):
        repository.generate_next_actions(user_id)


def poll_telegram_controls() -> None:
    try:
        from .integrations import integrations
        with SessionLocal() as session:
            user_ids = session.scalars(select(IntegrationAccount.user_id).where(IntegrationAccount.provider == "telegram", IntegrationAccount.status == "connected")).all()
        for user_id in set(user_ids):
            integrations.poll_telegram_controls(user_id)
    except Exception:
        # Integrations are optional. A network or keyring failure must not stop local work.
        return


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler and _scheduler.running:
        return _scheduler
    job_url = DATABASE_URL
    _scheduler = BackgroundScheduler(
        jobstores={"default": SQLAlchemyJobStore(url=job_url)},
        timezone=os.getenv("JOBFLOW_TIMEZONE", "Africa/Cairo"),
        daemon=True,
    )
    _scheduler.add_job(refresh_next_actions, "interval", minutes=30, id="refresh-next-actions", replace_existing=True, max_instances=1, coalesce=True)
    _scheduler.add_job(poll_telegram_controls, "interval", seconds=10, id="telegram-controls", replace_existing=True, max_instances=1, coalesce=True)
    _scheduler.start()
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None
