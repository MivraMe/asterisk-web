import ipaddress

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from asterisk_ami import ami
from asterisk_cli import run_asterisk_command
from config import settings

router = APIRouter()


class ConfigRead(BaseModel):
    ami_host: str
    ami_port: int
    asterisk_ip: str
    pjsip_conf: str
    extensions_conf: str
    features_conf: str
    polycom_cfg_dir: str
    backup_dir: str
    log_level: str


class ConfigUpdate(BaseModel):
    ami_host: str | None = None
    ami_port: int | None = None
    asterisk_ip: str | None = None
    log_level: str | None = None

    @field_validator("asterisk_ip")
    @classmethod
    def validate_ip(cls, v: str | None) -> str | None:
        if v is not None:
            ipaddress.ip_address(v)
        return v


@router.get("/", response_model=ConfigRead, summary="Get current app configuration")
async def get_config() -> ConfigRead:
    return ConfigRead(
        ami_host=settings.ami_host,
        ami_port=settings.ami_port,
        asterisk_ip=settings.asterisk_ip,
        pjsip_conf=settings.pjsip_conf,
        extensions_conf=settings.extensions_conf,
        features_conf=settings.features_conf,
        polycom_cfg_dir=settings.polycom_cfg_dir,
        backup_dir=settings.backup_dir,
        log_level=settings.log_level,
    )


@router.put("/", summary="Update runtime configuration (restarts may be needed)")
async def update_config(body: ConfigUpdate) -> dict:
    # Note: pydantic-settings reads from env; runtime overrides aren't persisted
    # across restarts. This endpoint updates the in-memory settings object.
    if body.ami_host is not None:
        settings.ami_host = body.ami_host
    if body.ami_port is not None:
        settings.ami_port = body.ami_port
    if body.asterisk_ip is not None:
        settings.asterisk_ip = body.asterisk_ip
    if body.log_level is not None:
        settings.log_level = body.log_level
    return {"status": "updated", "note": "changes are in-memory only; update .env for persistence"}


@router.post("/reload", summary="Trigger Asterisk core reload via AMI")
async def reload_asterisk() -> dict:
    try:
        resp = await ami.core_reload()
        return {"status": "reloaded", "ami_response": resp}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))
