"""add ring_groups table

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ring_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("extensions", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("strategy", sa.String(length=20), server_default="ringall"),
        sa.Column("ring_timeout", sa.Integer(), server_default="20"),
        sa.Column("fallback_destination_type", sa.String(length=20), server_default="voicemail"),
        sa.Column("fallback_destination_value", sa.Text()),
        sa.UniqueConstraint("name"),
    )


def downgrade() -> None:
    op.drop_table("ring_groups")
