"""provider_keys: adiciona format, base_url e label (suporte a qualquer LLM/local)

Revision ID: 0002_provider_key_fields
Revises: 0001_initial
Create Date: 2026-07-13

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_provider_key_fields"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "provider_keys",
        sa.Column("format", sa.String(20), nullable=False, server_default="openai"),
    )
    op.add_column("provider_keys", sa.Column("base_url", sa.String(500), nullable=True))
    op.add_column("provider_keys", sa.Column("label", sa.String(255), nullable=True))
    op.add_column("provider_keys", sa.Column("default_model", sa.String(150), nullable=True))


def downgrade() -> None:
    op.drop_column("provider_keys", "default_model")
    op.drop_column("provider_keys", "label")
    op.drop_column("provider_keys", "base_url")
    op.drop_column("provider_keys", "format")
