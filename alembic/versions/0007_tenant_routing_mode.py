"""routing_mode por tenant (heuristic | classifier)

Revision ID: 0007_tenant_routing_mode
Revises: 0006_guardrails
Create Date: 2026-07-14

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_tenant_routing_mode"
down_revision: str | None = "0006_guardrails"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "routing_mode",
            sa.String(20),
            nullable=False,
            server_default="heuristic",
        ),
    )


def downgrade() -> None:
    op.drop_column("tenants", "routing_mode")
