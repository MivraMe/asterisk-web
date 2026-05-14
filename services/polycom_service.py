"""
Polycom provisioning service — orchestrates DB + file operations.
"""
import logging
from datetime import datetime

from sqlalchemy import select

from database import AsyncSessionLocal
from models import Extension, Log, PolycomDevice
from polycom_provisioning import (
    delete_device_config,
    list_device_macs,
    normalize_mac,
    read_site_config,
    render_device_config,
    render_site_config,
    write_device_config,
    write_site_config,
)

logger = logging.getLogger(__name__)


async def _audit(msg: str) -> None:
    async with AsyncSessionLocal() as db:
        db.add(Log(level="INFO", message=msg, module="polycom"))
        await db.commit()


async def get_all_devices() -> list[dict]:
    """Return all devices from DB, enriched with file-system presence."""
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(PolycomDevice))).scalars().all()
    file_macs = set(list_device_macs())
    result = []
    for row in rows:
        d = _device_to_dict(row)
        d["file_exists"] = row.mac_address in file_macs
        result.append(d)
    return result


async def get_device(mac: str) -> dict | None:
    mac = normalize_mac(mac)
    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(PolycomDevice).where(PolycomDevice.mac_address == mac)
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
    async with AsyncSessionLocal() as db:
        # resolve extension
        ext_row = (await db.execute(
            select(Extension).where(Extension.number == extension_number)
        )).scalar_one_or_none()

        password = ext_row.password if ext_row else ""
        dn = display_name or (ext_row.name if ext_row else extension_number)
        ext_id = ext_row.id if ext_row else None
        eff_ip = asterisk_ip or (await _get_asterisk_ip_from_site())

        # render and write file
        xml_str = render_device_config(
            mac=mac,
            extension=extension_number,
            password=password or "",
            display_name=dn,
            asterisk_ip=eff_ip,
        )
        dest = write_device_config(mac, xml_str)

        # persist to DB
        device = PolycomDevice(
            mac_address=mac,
            extension_id=ext_id,
            model=model,
            asterisk_ip=eff_ip,
            config_file_path=str(dest),
            provisioning_status="ok",
            last_provision=datetime.utcnow(),
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
            # find current extension number
            ext_row = None
            if device.extension_id:
                ext_row = (await db.execute(
                    select(Extension).where(Extension.id == device.extension_id)
                )).scalar_one_or_none()
            extension_number = ext_row.number if ext_row else ""

        if "asterisk_ip" in kwargs:
            device.asterisk_ip = kwargs["asterisk_ip"]
        if "model" in kwargs:
            device.model = kwargs["model"]

        # regenerate config file
        ext_row_final = None
        if device.extension_id:
            ext_row_final = (await db.execute(
                select(Extension).where(Extension.id == device.extension_id)
            )).scalar_one_or_none()

        xml_str = render_device_config(
            mac=mac,
            extension=extension_number,
            password=(ext_row_final.password if ext_row_final else "") or "",
            display_name=(ext_row_final.name if ext_row_final else "") or extension_number,
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
            ext_row = None
            if device.extension_id:
                ext_row = (await db.execute(
                    select(Extension).where(Extension.id == device.extension_id)
                )).scalar_one_or_none()
            ext_num = ext_row.number if ext_row else ""
            try:
                xml = render_device_config(
                    mac=device.mac_address,
                    extension=ext_num,
                    password=(ext_row.password if ext_row else "") or "",
                    display_name=(ext_row.name if ext_row else "") or ext_num,
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


async def _file_exists(mac: str) -> bool:
    from polycom_provisioning import get_device_config_path
    return get_device_config_path(mac).exists()


async def _get_asterisk_ip_from_site() -> str:
    from config import settings
    return settings.asterisk_ip


def _device_to_dict(d: PolycomDevice) -> dict:
    return {
        "id": d.id,
        "mac_address": d.mac_address,
        "extension_id": d.extension_id,
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
