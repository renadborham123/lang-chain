"""Add Wazzefni's readiness, development, and skill-proof loop."""

from alembic import op

from employment.database import Base
from employment import models  # noqa: F401


revision = "0003_qualification_loop"
down_revision = "0002_auth_accounts"
branch_labels = None
depends_on = None


TABLES = (
    "target_roles",
    "market_requirements",
    "skill_evidence",
    "development_plans",
    "development_tasks",
    "learning_opportunities",
    "skill_assessments",
    "assessment_turns",
    "readiness_snapshots",
    "career_milestones",
    "cv_change_proposals",
)


def upgrade() -> None:
    bind = op.get_bind()
    for name in TABLES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
