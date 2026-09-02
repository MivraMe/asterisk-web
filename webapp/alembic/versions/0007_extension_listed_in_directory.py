"""add extensions.listed_in_directory (IVR directory list visibility)

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("extensions", sa.Column("listed_in_directory", sa.Boolean(), server_default=sa.text("true")))


def downgrade() -> None:
    op.drop_column("extensions", "listed_in_directory")
