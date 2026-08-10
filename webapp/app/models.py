from datetime import datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Extension(Base):
    __tablename__ = "extensions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    extension: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text)
    sip_password: Mapped[str] = mapped_column(Text, nullable=False)
    voicemail_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    voicemail_pin: Mapped[str | None] = mapped_column(String(10))
    voicemail_email: Mapped[str | None] = mapped_column(Text)
    context: Mapped[str] = mapped_column(String(50), default="internal")
    # Follow-me / call forwarding — external numbers rung (in addition to
    # the desk phone) before falling back to voicemail. follow_me_timeout is
    # how long the desk phone rings alone before follow-me kicks in.
    follow_me_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    follow_me_numbers: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    follow_me_timeout: Mapped[int] = mapped_column(Integer, default=20)
    follow_me_strategy: Mapped[str] = mapped_column(String(20), default="simultaneous")  # simultaneous | sequential
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Trunk(Base):
    __tablename__ = "trunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)  # voipms | twilio
    sip_server: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[str] = mapped_column(Text, nullable=False)
    secret: Mapped[str] = mapped_column(Text, nullable=False)
    did_numbers: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    # Overrides the global default codec offer (opus,g722,ulaw,alaw) for this
    # trunk's endpoint — some providers/accounts only accept a subset (e.g. a
    # VoIP.ms account limited to G722). NULL means "use the default".
    codecs: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    # Outbound CallerID (a real DID) used for from_user/callerid on this
    # trunk's endpoint. Some providers reject outbound calls unless this is
    # a real number they recognize — trunk.username (the account/subaccount
    # id) is not always acceptable. NULL falls back to trunk.username.
    callerid: Mapped[str | None] = mapped_column(String(20))
    max_channels: Mapped[int] = mapped_column(Integer, default=5)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    inbound_routes: Mapped[list["InboundRoute"]] = relationship(back_populates="trunk")
    outbound_routes: Mapped[list["OutboundRoute"]] = relationship(back_populates="trunk")


class RingGroup(Base):
    __tablename__ = "ring_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    extensions: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    strategy: Mapped[str] = mapped_column(String(20), default="ringall")  # ringall | hunt | random
    ring_timeout: Mapped[int] = mapped_column(Integer, default=20)
    fallback_destination_type: Mapped[str] = mapped_column(String(20), default="voicemail")  # extension|voicemail|hangup
    fallback_destination_value: Mapped[str | None] = mapped_column(Text)


class InboundRoute(Base):
    __tablename__ = "inbound_routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    did_number: Mapped[str] = mapped_column(String(20), nullable=False)
    trunk_id: Mapped[int | None] = mapped_column(ForeignKey("trunks.id"))
    destination_type: Mapped[str] = mapped_column(String(20), nullable=False)  # extension|ring_group|voicemail
    destination_value: Mapped[str] = mapped_column(Text, nullable=False)
    time_condition: Mapped[dict | None] = mapped_column(JSONB)

    trunk: Mapped["Trunk | None"] = relationship(back_populates="inbound_routes")


class OutboundRoute(Base):
    __tablename__ = "outbound_routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pattern: Mapped[str] = mapped_column(String(50), nullable=False)
    trunk_id: Mapped[int | None] = mapped_column(ForeignKey("trunks.id"))
    priority: Mapped[int] = mapped_column(Integer, default=1)
    strip_digits: Mapped[int] = mapped_column(Integer, default=0)
    prepend: Mapped[str | None] = mapped_column(Text)

    trunk: Mapped["Trunk | None"] = relationship(back_populates="outbound_routes")


class CDR(Base):
    """Mirrors the standard cdr_pgsql schema so Asterisk's cdr_pgsql module
    can write rows directly — the webapp only ever reads from this table."""

    __tablename__ = "cdr"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    calldate: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    clid: Mapped[str] = mapped_column(String(80), default="")
    src: Mapped[str] = mapped_column(String(80), default="")
    dst: Mapped[str] = mapped_column(String(80), default="")
    dcontext: Mapped[str] = mapped_column(String(80), default="")
    channel: Mapped[str] = mapped_column(String(80), default="")
    dstchannel: Mapped[str] = mapped_column(String(80), default="")
    lastapp: Mapped[str] = mapped_column(String(80), default="")
    lastdata: Mapped[str] = mapped_column(String(80), default="")
    duration: Mapped[int] = mapped_column(Integer, default=0)
    billsec: Mapped[int] = mapped_column(Integer, default=0)
    disposition: Mapped[str] = mapped_column(String(45), default="")
    amaflags: Mapped[int] = mapped_column(Integer, default=0)
    accountcode: Mapped[str] = mapped_column(String(20), default="")
    uniqueid: Mapped[str] = mapped_column(String(150), default="")
    userfield: Mapped[str] = mapped_column(String(255), default="")
    peeraccount: Mapped[str] = mapped_column(String(20), default="")
    linkedid: Mapped[str] = mapped_column(String(150), default="")
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    recordingfile: Mapped[str | None] = mapped_column(String(255))
