"""add extensions.follow_me_* (follow-me / call forwarding)

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("extensions", sa.Column("follow_me_enabled", sa.Boolean(), server_default=sa.text("false")))
    op.add_column("extensions", sa.Column("follow_me_numbers", postgresql.ARRAY(sa.String())))
    op.add_column("extensions", sa.Column("follow_me_timeout", sa.Integer(), server_default="20"))
    op.add_column("extensions", sa.Column("follow_me_strategy", sa.String(length=20), server_default="simultaneous"))


def downgrade() -> None:
    op.drop_column("extensions", "follow_me_strategy")
    op.drop_column("extensions", "follow_me_timeout")
    op.drop_column("extensions", "follow_me_numbers")
    op.drop_column("extensions", "follow_me_enabled")
