"""Create the local-first employment operating system schema."""

from alembic import op

from employment.database import Base
from employment import models  # noqa: F401


revision = "0001_employment_os"
down_revision = None
branch_labels = None
depends_on = None


TABLES = (
    "user_profiles",
    "career_facts",
    "documents",
    "opportunities",
    "applications",
    "application_events",
    "application_artifacts",
    "next_actions",
    "approval_requests",
    "agent_runs",
    "audit_events",
    "contacts",
    "communication_threads",
    "message_drafts",
    "interviews",
    "interview_turns",
    "offers",
    "offer_components",
    "negotiation_drafts",
    "integration_accounts",
    "notifications",
    "outcome_metrics",
)


def upgrade() -> None:
    bind = op.get_bind()
    for name in TABLES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
