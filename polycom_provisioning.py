"""
Polycom provisioning engine.

Handles rendering Jinja2 XML templates, validating output, and
atomically writing/reading config files under polycom_cfg_dir.
"""
import logging
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import settings
from services.asterisk_service import backup_file

logger = logging.getLogger(__name__)

_jinja_env = Environment(
    loader=FileSystemLoader(str(Path(__file__).parent / "templates")),
    autoescape=select_autoescape(["cfg", "xml", "j2"]),
)


def normalize_mac(mac: str) -> str:
    """Normalize MAC to lowercase 12-hex-char string (no separators)."""
    clean = re.sub(r"[:\-\.]", "", mac).lower()
    if not re.fullmatch(r"[0-9a-f]{12}", clean):
        raise ValueError(f"Invalid MAC address: {mac!r}")
    return clean


def _validate_xml(xml_str: str) -> None:
    """Raise ValueError if xml_str is not parseable XML."""
    try:
        ET.fromstring(xml_str)
    except ET.ParseError as exc:
        raise ValueError(f"Generated config is not valid XML: {exc}") from exc


def _atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically via tempfile + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp_")
    try:
        os.write(fd, content.encode())
        os.close(fd)
        os.replace(tmp, path)
    except Exception:
        os.unlink(tmp)
        raise


def render_device_config(
    mac: str,
    extension: str,
    password: str,
    display_name: str,
    asterisk_ip: str | None = None,
    sip_port: int = 5060,
    http_port: int = 8080,
) -> str:
    """Render a per-device .cfg file. Returns the XML string."""
    tmpl = _jinja_env.get_template("polycom_device.cfg.j2")
    xml_str = tmpl.render(
        mac_address=normalize_mac(mac),
        extension=extension,
        password=password,
        display_name=display_name or extension,
        asterisk_ip=asterisk_ip or settings.asterisk_ip,
        provisioning_ip=asterisk_ip or settings.asterisk_ip,
        sip_port=sip_port,
        http_port=http_port,
    )
    _validate_xml(xml_str)
    return xml_str


def write_device_config(mac: str, xml_str: str) -> Path:
    """Persist device config. Returns the file path."""
    norm = normalize_mac(mac)
    cfg_dir = Path(settings.polycom_cfg_dir)
    dest = cfg_dir / f"{norm}.cfg"
    if dest.exists():
        backup_file(str(dest))
    _atomic_write(dest, xml_str)
    logger.info("Wrote Polycom config: %s", dest)
    return dest


def delete_device_config(mac: str) -> None:
    norm = normalize_mac(mac)
    dest = Path(settings.polycom_cfg_dir) / f"{norm}.cfg"
    if dest.exists():
        backup_file(str(dest))
        dest.unlink()
        logger.info("Deleted Polycom config: %s", dest)


def get_device_config_path(mac: str) -> Path:
    return Path(settings.polycom_cfg_dir) / f"{normalize_mac(mac)}.cfg"


def list_device_macs() -> list[str]:
    """Return list of normalized MAC addresses that have a .cfg file."""
    cfg_dir = Path(settings.polycom_cfg_dir)
    if not cfg_dir.exists():
        return []
    macs = []
    for f in cfg_dir.glob("*.cfg"):
        stem = f.stem
        if re.fullmatch(r"[0-9a-f]{12}", stem):
            macs.append(stem)
    return sorted(macs)


def render_site_config(
    provisioning_ip: str,
    prov_user: str = "admin",
    prov_password: str = "",
) -> str:
    tmpl = _jinja_env.get_template("polycom_site.cfg.j2")
    xml_str = tmpl.render(
        provisioning_ip=provisioning_ip,
        prov_user=prov_user,
        prov_password=prov_password,
    )
    _validate_xml(xml_str)
    return xml_str


def write_site_config(xml_str: str) -> None:
    dest = Path(settings.polycom_cfg_dir) / "site.cfg"
    if dest.exists():
        backup_file(str(dest))
    _atomic_write(dest, xml_str)
    logger.info("Wrote site.cfg")


def read_site_config() -> dict:
    """Parse site.cfg XML into a flat dict of attributes."""
    dest = Path(settings.polycom_cfg_dir) / "site.cfg"
    if not dest.exists():
        return {}
    try:
        tree = ET.parse(dest)
        root = tree.getroot()
        result: dict[str, str] = {}
        for elem in root.iter():
            for k, v in elem.attrib.items():
                result[k] = v
        return result
    except ET.ParseError:
        return {}
