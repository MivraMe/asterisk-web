"""add trunks.callerid (outbound CallerID override)

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("trunks", sa.Column("callerid", sa.String(length=20)))


def downgrade() -> None:
    op.drop_column("trunks", "callerid")
