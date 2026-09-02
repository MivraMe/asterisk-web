"""add ivr_settings table (singleton auto-attendant config)

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ivr_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("timeout_seconds", sa.Integer(), server_default="8"),
        sa.Column("fallback_destination_type", sa.String(length=20), server_default="voicemail"),
        sa.Column("fallback_destination_value", sa.Text()),
    )


def downgrade() -> None:
    op.drop_table("ivr_settings")
