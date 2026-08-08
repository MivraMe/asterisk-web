"""initial schema: users, extensions, trunks, inbound_routes, outbound_routes, cdr

Revision ID: 0001
Revises:
Create Date: 2026-08-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("username"),
    )

    op.create_table(
        "extensions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("extension", sa.String(length=10), nullable=False),
        sa.Column("display_name", sa.Text()),
        sa.Column("sip_password", sa.Text(), nullable=False),
        sa.Column("voicemail_enabled", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("voicemail_pin", sa.String(length=10)),
        sa.Column("voicemail_email", sa.Text()),
        sa.Column("context", sa.String(length=50), server_default="internal"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("extension"),
    )

    op.create_table(
        "trunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("sip_server", sa.Text(), nullable=False),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("secret", sa.Text(), nullable=False),
        sa.Column("did_numbers", postgresql.ARRAY(sa.String())),
        sa.Column("max_channels", sa.Integer(), server_default="5"),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true")),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "inbound_routes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("did_number", sa.String(length=20), nullable=False),
        sa.Column("trunk_id", sa.Integer(), sa.ForeignKey("trunks.id")),
        sa.Column("destination_type", sa.String(length=20), nullable=False),
        sa.Column("destination_value", sa.Text(), nullable=False),
        sa.Column("time_condition", postgresql.JSONB()),
    )

    op.create_table(
        "outbound_routes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pattern", sa.String(length=50), nullable=False),
        sa.Column("trunk_id", sa.Integer(), sa.ForeignKey("trunks.id")),
        sa.Column("priority", sa.Integer(), server_default="1"),
        sa.Column("strip_digits", sa.Integer(), server_default="0"),
        sa.Column("prepend", sa.Text()),
    )

    # Matches the default cdr_pgsql column set exactly so Asterisk's
    # cdr_pgsql module can write into this table directly.
    op.create_table(
        "cdr",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("calldate", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("clid", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("src", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("dst", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("dcontext", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("channel", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("dstchannel", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("lastapp", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("lastdata", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("duration", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("billsec", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("disposition", sa.String(length=45), nullable=False, server_default=""),
        sa.Column("amaflags", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accountcode", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("uniqueid", sa.String(length=150), nullable=False, server_default=""),
        sa.Column("userfield", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("peeraccount", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("linkedid", sa.String(length=150), nullable=False, server_default=""),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recordingfile", sa.String(length=255)),
    )
    op.create_index("ix_cdr_calldate", "cdr", ["calldate"])
    op.create_index("ix_cdr_src", "cdr", ["src"])
    op.create_index("ix_cdr_dst", "cdr", ["dst"])


def downgrade() -> None:
    op.drop_index("ix_cdr_dst", table_name="cdr")
    op.drop_index("ix_cdr_src", table_name="cdr")
    op.drop_index("ix_cdr_calldate", table_name="cdr")
    op.drop_table("cdr")
    op.drop_table("outbound_routes")
    op.drop_table("inbound_routes")
    op.drop_table("trunks")
    op.drop_table("extensions")
    op.drop_table("users")
