import ipaddress
import re

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, field_validator

from polycom_provisioning import (
    list_device_macs,
    normalize_mac,
    read_site_config,
    render_site_config,
    write_site_config,
)
from services.polycom_service import (
    create_device,
    delete_device,
    get_all_devices,
    get_device,
    sync_asterisk_ip,
    update_device,
)

router = APIRouter()


class DeviceCreate(BaseModel):
    mac_address: str
    extension_number: str
    model: str = "VVX250"
    asterisk_ip: str | None = None
    display_name: str = ""

    @field_validator("mac_address")
    @classmethod
    def validate_mac(cls, v: str) -> str:
        return normalize_mac(v)

    @field_validator("asterisk_ip")
    @classmethod
    def validate_ip(cls, v: str | None) -> str | None:
        if v is not None:
            ipaddress.ip_address(v)
        return v


class DeviceUpdate(BaseModel):
    extension_number: str | None = None
    asterisk_ip: str | None = None
    model: str | None = None

    @field_validator("extension_number")
    @classmethod
    def validate_ext(cls, v: str | None) -> str | None:
        if v is not None and v.strip() == "":
            return None
        return v

    @field_validator("asterisk_ip")
    @classmethod
    def validate_ip(cls, v: str | None) -> str | None:
        if v is not None:
            ipaddress.ip_address(v)
        return v


class SiteConfigUpdate(BaseModel):
    provisioning_ip: str
    prov_user: str = "admin"
    prov_password: str = ""

    @field_validator("provisioning_ip")
    @classmethod
    def validate_ip(cls, v: str) -> str:
        ipaddress.ip_address(v)
        return v


class SyncIPRequest(BaseModel):
    new_ip: str

    @field_validator("new_ip")
    @classmethod
    def validate_ip(cls, v: str) -> str:
        ipaddress.ip_address(v)
        return v


# ------------------------------------------------------------------ #
# Devices                                                              #
# ------------------------------------------------------------------ #

@router.get("/devices", summary="List all provisioned Polycom devices")
async def list_devices() -> list[dict]:
    return await get_all_devices()


@router.get("/devices/{mac}", summary="Get a single device")
async def get_dev(mac: str) -> dict:
    device = await get_device(mac)
    if device is None:
        raise HTTPException(status_code=404, detail=f"Device {mac} not found")
    return device


@router.post("/devices", status_code=status.HTTP_201_CREATED, summary="Create and provision a device")
async def create_dev(body: DeviceCreate) -> dict:
    try:
        return await create_device(
            mac=body.mac_address,
            extension_number=body.extension_number,
            model=body.model,
            asterisk_ip=body.asterisk_ip,
            display_name=body.display_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.put("/devices/{mac}", summary="Update device and regenerate config")
async def update_dev(mac: str, body: DeviceUpdate) -> dict:
    kwargs = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        return await update_device(mac, **kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/devices/{mac}", summary="Delete device and remove config file")
async def delete_dev(mac: str) -> dict:
    try:
        await delete_device(mac)
        return {"mac_address": mac, "status": "deleted"}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/devices/{mac}/reboot", summary="Request device reboot (Phase 2 — HTTP POST to phone)")
async def reboot_dev(mac: str) -> dict:
    device = await get_device(mac)
    if device is None:
        raise HTTPException(status_code=404, detail=f"Device {mac} not found")
    if not device.get("ip_address"):
        raise HTTPException(status_code=422, detail="Device IP address unknown — cannot reboot")
    # Phase 2: send HTTP POST to phone's built-in web server
    return {"mac_address": mac, "status": "reboot_not_implemented", "message": "Phase 2 feature"}


# ------------------------------------------------------------------ #
# Site config                                                          #
# ------------------------------------------------------------------ #

@router.get("/config", summary="Read site.cfg")
async def get_site_config() -> dict:
    return read_site_config()


@router.put("/config", summary="Write new site.cfg")
async def put_site_config(body: SiteConfigUpdate) -> dict:
    try:
        xml_str = render_site_config(body.provisioning_ip, body.prov_user, body.prov_password)
        write_site_config(xml_str)
        return {"status": "updated"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/config/sync-ip", summary="Change Asterisk IP everywhere (site.cfg + all device configs)")
async def sync_ip(body: SyncIPRequest) -> dict:
    try:
        count = await sync_asterisk_ip(body.new_ip)
        return {"status": "synced", "devices_updated": count, "new_ip": body.new_ip}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/status", summary="Provisioning status summary")
async def provisioning_status() -> dict:
    devices = await get_all_devices()
    file_macs = list_device_macs()
    return {
        "total_devices": len(devices),
        "files_on_disk": len(file_macs),
        "provisioned_ok": sum(1 for d in devices if d["provisioning_status"] == "ok"),
        "errors": sum(1 for d in devices if d["provisioning_status"] == "error"),
    }
