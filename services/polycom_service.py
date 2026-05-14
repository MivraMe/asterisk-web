"""
Polycom provisioning service — orchestrates DB + file operations.

Extension password/name are always read from pjsip.conf (source of truth).
The SQLite Extension table may be empty; we never rely on it for SIP credentials.
The extension_number is stored in config_json so it survives even without a DB join.
"""
import json
import logging
import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from config import settings
from database import AsyncSessionLocal
from models import Extension, Log, PolycomDevice
from polycom_provisioning import (
    delete_device_config,
    get_device_config_path,
    list_device_macs,
    normalize_mac,
    read_extension_from_device_cfg,
    read_site_config,
    render_device_config,
    render_site_config,
    write_device_config,
    write_site_config,
)
from services.asterisk_service import get_extension as get_pjsip_extension

logger = logging.getLogger(__name__)


async def _audit(msg: str) -> None:
    async with AsyncSessionLocal() as db:
        db.add(Log(level="INFO", message=msg, module="polycom"))
        await db.commit()


async def get_all_devices() -> list[dict]:
    """Return all devices from DB + orphaned .cfg files not tracked in DB."""
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(PolycomDevice).options(selectinload(PolycomDevice.extension))
        )).scalars().all()

    db_macs = {row.mac_address for row in rows}
    file_macs = set(list_device_macs())

    result = []
    for row in rows:
        d = _device_to_dict(row)
        d["file_exists"] = row.mac_address in file_macs
        result.append(d)

    # Surface .cfg files that exist on disk but have no DB entry
    for mac in file_macs - db_macs:
        result.append({
            "id": None,
            "mac_address": mac,
            "extension_id": None,
            "extension_number": None,
            "model": "Unknown",
            "firmware": None,
            "ip_address": None,
            "asterisk_ip": None,
            "config_file_path": None,
            "last_provision": None,
            "last_reboot": None,
            "provisioning_status": "orphan",
            "error_msg": "Config file exists but device not in database",
            "created_at": None,
            "file_exists": True,
        })

    return result


async def get_device(mac: str) -> dict | None:
    mac = normalize_mac(mac)
    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(PolycomDevice)
            .where(PolycomDevice.mac_address == mac)
            .options(selectinload(PolycomDevice.extension))
        )).scalar_one_or_none()
    if row is None:
        return None
    d = _device_to_dict(row)
    d["file_exists"] = (await _file_exists(mac))
    return d


async def create_device(
    mac: str,
    extension_number: str,
    model: str = "VVX250",
    asterisk_ip: str | None = None,
    display_name: str = "",
) -> dict:
    mac = normalize_mac(mac)

    # pjsip.conf is the source of truth for SIP credentials (DB extensions table may be empty)
    pjsip_ext = get_pjsip_extension(extension_number)
    password = (pjsip_ext.get("password") if pjsip_ext else None) or ""
    dn = display_name or (pjsip_ext.get("name") if pjsip_ext else None) or extension_number
    eff_ip = asterisk_ip or settings.asterisk_ip

    xml_str = render_device_config(
        mac=mac,
        extension=extension_number,
        password=password,
        display_name=dn,
        asterisk_ip=eff_ip,
    )
    dest = write_device_config(mac, xml_str)

    async with AsyncSessionLocal() as db:
        # Try to link to the Extension row if it exists in DB (optional)
        ext_row = (await db.execute(
            select(Extension).where(Extension.number == extension_number)
        )).scalar_one_or_none()

        device = PolycomDevice(
            mac_address=mac,
            extension_id=ext_row.id if ext_row else None,
            model=model,
            asterisk_ip=eff_ip,
            config_file_path=str(dest),
            provisioning_status="ok",
            last_provision=datetime.utcnow(),
            config_json=json.dumps({"extension_number": extension_number}),
        )
        db.add(device)
        await db.commit()
        await db.refresh(device)

    await _audit(f"Created Polycom device {mac} → ext {extension_number}")
    return _device_to_dict(device)


async def update_device(mac: str, **kwargs) -> dict:
    mac = normalize_mac(mac)
    async with AsyncSessionLocal() as db:
        device = (await db.execute(
            select(PolycomDevice).where(PolycomDevice.mac_address == mac)
        )).scalar_one_or_none()
        if device is None:
            raise ValueError(f"Device {mac} not found")

        extension_number = kwargs.get("extension_number")
        if extension_number:
            ext_row = (await db.execute(
                select(Extension).where(Extension.number == extension_number)
            )).scalar_one_or_none()
            device.extension_id = ext_row.id if ext_row else None
        else:
            # resolve current extension_number from config_json first, then DB FK
            if device.config_json:
                try:
                    extension_number = json.loads(device.config_json).get("extension_number") or ""
                except (json.JSONDecodeError, TypeError):
                    extension_number = ""
            if not extension_number and device.extension_id:
                ext_row = (await db.execute(
                    select(Extension).where(Extension.id == device.extension_id)
                )).scalar_one_or_none()
                extension_number = ext_row.number if ext_row else ""

        # Always persist extension_number to config_json so it survives without a DB join
        if extension_number:
            device.config_json = json.dumps({"extension_number": extension_number})

        if "asterisk_ip" in kwargs:
            device.asterisk_ip = kwargs["asterisk_ip"]
        if "model" in kwargs:
            device.model = kwargs["model"]
        if "ip_address" in kwargs:
            device.ip_address = kwargs["ip_address"]

        # pjsip.conf is the source of truth for SIP credentials
        pjsip_ext = get_pjsip_extension(extension_number) if extension_number else None
        password = (pjsip_ext.get("password") if pjsip_ext else None) or ""
        display_name = (pjsip_ext.get("name") if pjsip_ext else None) or extension_number

        xml_str = render_device_config(
            mac=mac,
            extension=extension_number,
            password=password,
            display_name=display_name,
            asterisk_ip=device.asterisk_ip,
        )
        dest = write_device_config(mac, xml_str)
        device.config_file_path = str(dest)
        device.last_provision = datetime.utcnow()
        device.provisioning_status = "ok"

        await db.commit()
        await db.refresh(device)

    await _audit(f"Updated Polycom device {mac}")
    return _device_to_dict(device)


async def delete_device(mac: str) -> None:
    mac = normalize_mac(mac)
    async with AsyncSessionLocal() as db:
        device = (await db.execute(
            select(PolycomDevice).where(PolycomDevice.mac_address == mac)
        )).scalar_one_or_none()
        if device is None:
            raise ValueError(f"Device {mac} not found")
        await db.delete(device)
        await db.commit()
    delete_device_config(mac)
    await _audit(f"Deleted Polycom device {mac}")


async def sync_asterisk_ip(new_ip: str) -> int:
    """Update IP in site.cfg and regenerate all device configs. Returns count updated."""
    # update site.cfg
    site = read_site_config()
    user = site.get("device.prov.user", "admin")
    pw = site.get("device.prov.password", "")
    xml_str = render_site_config(new_ip, user, pw)
    write_site_config(xml_str)

    async with AsyncSessionLocal() as db:
        devices = (await db.execute(select(PolycomDevice))).scalars().all()
        count = 0
        for device in devices:
            device.asterisk_ip = new_ip
            # resolve extension number from config_json (source of truth)
            ext_num = ""
            if device.config_json:
                try:
                    ext_num = json.loads(device.config_json).get("extension_number") or ""
                except (json.JSONDecodeError, TypeError):
                    pass
            if not ext_num and device.extension_id:
                ext_row = (await db.execute(
                    select(Extension).where(Extension.id == device.extension_id)
                )).scalar_one_or_none()
                ext_num = ext_row.number if ext_row else ""
            # pjsip.conf is source of truth for SIP credentials
            pjsip_ext = get_pjsip_extension(ext_num) if ext_num else None
            try:
                xml = render_device_config(
                    mac=device.mac_address,
                    extension=ext_num,
                    password=(pjsip_ext.get("password") if pjsip_ext else None) or "",
                    display_name=(pjsip_ext.get("name") if pjsip_ext else None) or ext_num,
                    asterisk_ip=new_ip,
                )
                write_device_config(device.mac_address, xml)
                device.last_provision = datetime.utcnow()
                device.provisioning_status = "ok"
                count += 1
            except Exception as exc:
                device.error_msg = str(exc)
                device.provisioning_status = "error"
        await db.commit()

    await _audit(f"Synced Asterisk IP to {new_ip} for {count} devices")
    return count


async def import_orphan_devices() -> int:
    """Import .cfg files on disk that have no DB entry. Returns count imported."""
    async with AsyncSessionLocal() as db:
        existing = {
            row.mac_address
            for row in (await db.execute(select(PolycomDevice))).scalars().all()
        }

    file_macs = set(list_device_macs())
    orphans = file_macs - existing
    count = 0
    for mac in orphans:
        ext_num = read_extension_from_device_cfg(mac) or ""
        async with AsyncSessionLocal() as db:
            ext_row = None
            if ext_num:
                ext_row = (await db.execute(
                    select(Extension).where(Extension.number == ext_num)
                )).scalar_one_or_none()
            device = PolycomDevice(
                mac_address=mac,
                extension_id=ext_row.id if ext_row else None,
                model="Unknown",
                asterisk_ip=settings.asterisk_ip,
                config_file_path=str(get_device_config_path(mac)),
                provisioning_status="ok",
                config_json=json.dumps({"extension_number": ext_num}) if ext_num else None,
            )
            db.add(device)
            await db.commit()
        count += 1
        logger.info("Imported orphan Polycom device %s → ext %s", mac, ext_num or "(unknown)")

    if count:
        await _audit(f"Imported {count} orphan Polycom device(s) from disk")
    return count


async def _file_exists(mac: str) -> bool:
    return get_device_config_path(mac).exists()


def _device_to_dict(d: PolycomDevice) -> dict:
    # extension_number is stored in config_json; fall back to extension relationship
    ext_num: str | None = None
    if d.config_json:
        try:
            ext_num = json.loads(d.config_json).get("extension_number")
        except (json.JSONDecodeError, TypeError):
            pass
    if not ext_num and hasattr(d, "extension") and d.extension:
        ext_num = d.extension.number

    return {
        "id": d.id,
        "mac_address": d.mac_address,
        "extension_id": d.extension_id,
        "extension_number": ext_num,
        "model": d.model,
        "firmware": d.firmware,
        "ip_address": d.ip_address,
        "asterisk_ip": d.asterisk_ip,
        "config_file_path": d.config_file_path,
        "last_provision": d.last_provision.isoformat() if d.last_provision else None,
        "last_reboot": d.last_reboot.isoformat() if d.last_reboot else None,
        "provisioning_status": d.provisioning_status,
        "error_msg": d.error_msg,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }
