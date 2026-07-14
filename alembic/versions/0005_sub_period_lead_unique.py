"""assinatura: período/pending + lead único por e-mail

Revision ID: 0005_sub_period_lead_unique
Revises: 0004_leads
Create Date: 2026-07-14

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_sub_period_lead_unique"
down_revision: str | None = "0004_leads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "subscriptions", sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("subscriptions", sa.Column("pending_plan", sa.String(50), nullable=True))

    # Deduplica leads por e-mail (mantém o mais recente) e cria índice único.
    op.execute(
        "DELETE FROM leads WHERE id NOT IN "
        "(SELECT id FROM leads l WHERE l.created_at = "
        "(SELECT MAX(l2.created_at) FROM leads l2 WHERE l2.email = l.email))"
    )
    op.drop_index("ix_leads_email", table_name="leads")
    op.create_index("ix_leads_email", "leads", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_leads_email", table_name="leads")
    op.create_index("ix_leads_email", "leads", ["email"])
    op.drop_column("subscriptions", "pending_plan")
    op.drop_column("subscriptions", "current_period_start")
