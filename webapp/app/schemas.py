from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Provider = Literal["voipms", "twilio"]
DestinationType = Literal["extension", "ring_group", "voicemail"]


# ------------------------------------------------------------------ #
# Auth                                                                 #
# ------------------------------------------------------------------ #

class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str


# ------------------------------------------------------------------ #
# Extensions                                                           #
# ------------------------------------------------------------------ #

class ExtensionBase(BaseModel):
    extension: str = Field(pattern=r"^\d{2,10}$")
    display_name: str | None = None
    context: str = "internal"
    voicemail_enabled: bool = True
    voicemail_pin: str | None = None
    voicemail_email: str | None = None


class ExtensionCreate(ExtensionBase):
    sip_password: str = Field(min_length=8)


class ExtensionUpdate(BaseModel):
    display_name: str | None = None
    context: str | None = None
    sip_password: str | None = Field(default=None, min_length=8)
    voicemail_enabled: bool | None = None
    voicemail_pin: str | None = None
    voicemail_email: str | None = None


class ExtensionOut(ExtensionBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


# ------------------------------------------------------------------ #
# Trunks                                                               #
# ------------------------------------------------------------------ #

class TrunkBase(BaseModel):
    name: str
    provider: Provider
    sip_server: str
    username: str
    did_numbers: list[str] = Field(default_factory=list)
    max_channels: int = 5
    enabled: bool = True
    # Overrides the default codec offer (opus,g722,ulaw,alaw) for this trunk.
    # None/empty means "use the default".
    codecs: list[str] | None = None


class TrunkCreate(TrunkBase):
    secret: str = Field(min_length=4)


class TrunkUpdate(BaseModel):
    provider: Provider | None = None
    sip_server: str | None = None
    username: str | None = None
    secret: str | None = None
    did_numbers: list[str] | None = None
    max_channels: int | None = None
    enabled: bool | None = None
    codecs: list[str] | None = None


class TrunkOut(TrunkBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ------------------------------------------------------------------ #
# Routes                                                               #
# ------------------------------------------------------------------ #

class InboundRouteBase(BaseModel):
    did_number: str
    trunk_id: int | None = None
    destination_type: DestinationType
    destination_value: str
    time_condition: dict[str, Any] | None = None


class InboundRouteCreate(InboundRouteBase):
    pass


class InboundRouteUpdate(BaseModel):
    did_number: str | None = None
    trunk_id: int | None = None
    destination_type: DestinationType | None = None
    destination_value: str | None = None
    time_condition: dict[str, Any] | None = None


class InboundRouteOut(InboundRouteBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class OutboundRouteBase(BaseModel):
    pattern: str
    trunk_id: int | None = None
    priority: int = 1
    strip_digits: int = 0
    prepend: str | None = None


class OutboundRouteCreate(OutboundRouteBase):
    pass


class OutboundRouteUpdate(BaseModel):
    pattern: str | None = None
    trunk_id: int | None = None
    priority: int | None = None
    strip_digits: int | None = None
    prepend: str | None = None


class OutboundRouteOut(OutboundRouteBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ------------------------------------------------------------------ #
# Voicemail                                                            #
# ------------------------------------------------------------------ #

class VoicemailUpdate(BaseModel):
    voicemail_enabled: bool | None = None
    voicemail_pin: str | None = None
    voicemail_email: str | None = None


class VoicemailOut(BaseModel):
    extension: str
    voicemail_enabled: bool
    voicemail_pin: str | None
    voicemail_email: str | None


# ------------------------------------------------------------------ #
# CDR                                                                  #
# ------------------------------------------------------------------ #

class CDROut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    calldate: datetime
    clid: str
    src: str
    dst: str
    dcontext: str
    channel: str
    dstchannel: str
    lastapp: str
    duration: int
    billsec: int
    disposition: str
    accountcode: str
    uniqueid: str
    recordingfile: str | None = None


class CDRPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[CDROut]
