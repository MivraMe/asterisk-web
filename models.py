from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Extension(Base):
    __tablename__ = "extensions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(20), default="pjsip")
    password: Mapped[str | None] = mapped_column(String(100))
    context: Mapped[str] = mapped_column(String(50), default="from-internal")
    last_call: Mapped[datetime | None] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    devices: Mapped[list["PolycomDevice"]] = relationship("PolycomDevice", back_populates="extension")


class PolycomDevice(Base):
    __tablename__ = "polycom_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mac_address: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)
    extension_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("extensions.id"))
    model: Mapped[str] = mapped_column(String(50), default="VVX250")
    firmware: Mapped[str | None] = mapped_column(String(50))
    ip_address: Mapped[str | None] = mapped_column(String(45))
    asterisk_ip: Mapped[str] = mapped_column(String(45), default="192.168.0.107")
    config_file_path: Mapped[str | None] = mapped_column(String(255))
    last_provision: Mapped[datetime | None] = mapped_column(DateTime)
    last_reboot: Mapped[datetime | None] = mapped_column(DateTime)
    config_json: Mapped[str | None] = mapped_column(Text)
    provisioning_status: Mapped[str] = mapped_column(String(20), default="pending")
    error_msg: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    extension: Mapped["Extension | None"] = relationship("Extension", back_populates="devices")


class Feature(Base):
    __tablename__ = "features"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(100))
    destination: Mapped[str | None] = mapped_column(String(100))
    context: Mapped[str | None] = mapped_column(String(50))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    callid: Mapped[str | None] = mapped_column(String(100))
    from_ext: Mapped[str | None] = mapped_column(String(20))
    to_ext: Mapped[str | None] = mapped_column(String(20))
    start_time: Mapped[datetime | None] = mapped_column(DateTime)
    end_time: Mapped[datetime | None] = mapped_column(DateTime)
    duration: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str | None] = mapped_column(String(20))
    codec: Mapped[str | None] = mapped_column(String(20))


class Log(Base):
    __tablename__ = "logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    level: Mapped[str | None] = mapped_column(String(10))
    message: Mapped[str | None] = mapped_column(Text)
    module: Mapped[str | None] = mapped_column(String(50))
