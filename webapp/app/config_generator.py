"""Renders pjsip.conf / extensions.conf / voicemail.conf from DB state.

The database is the source of truth. Every time an extension, trunk or
route changes, the CRUD routers call `regenerate_and_reload()` which
re-renders all three files and asks Asterisk (over AMI) to reload just the
affected modules — no container restart, no dropped calls.
"""
import logging
from itertools import groupby
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ami_client import ami
from app.config import settings
from app.models import Extension, InboundRoute, OutboundRoute, Trunk

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates" / "asterisk"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    trim_blocks=True,
    lstrip_blocks=True,
    autoescape=select_autoescape(disabled_extensions=("j2",), default=False),
)


async def _load_data(db: AsyncSession) -> dict:
    extensions = (await db.execute(select(Extension).order_by(Extension.extension))).scalars().all()
    trunks = (await db.execute(select(Trunk).order_by(Trunk.name))).scalars().all()
    inbound_routes = (await db.execute(select(InboundRoute))).scalars().all()
    outbound_routes = (
        await db.execute(select(OutboundRoute).order_by(OutboundRoute.pattern, OutboundRoute.priority))
    ).scalars().all()

    trunk_by_id = {t.id: t for t in trunks}
    outbound_by_pattern = []
    for pattern, group in groupby(outbound_routes, key=lambda r: r.pattern):
        routes = []
        for r in sorted(group, key=lambda r: r.priority):
            trunk = trunk_by_id.get(r.trunk_id)
            if trunk is None or not trunk.enabled:
                continue
            routes.append(
                type("Route", (), {
                    "strip_digits": r.strip_digits,
                    "prepend": r.prepend,
                    "trunk_name": trunk.name,
                })()
            )
        if routes:
            outbound_by_pattern.append((pattern, routes))

    return {
        "extensions": extensions,
        "trunks": trunks,
        "inbound_routes": inbound_routes,
        "outbound_by_pattern": outbound_by_pattern,
        "voicemail_from_email": settings.voicemail_from_email,
    }


def _write(name: str, content: str) -> None:
    dest = Path(settings.asterisk_etc_dir) / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content)
    logger.info("Wrote %s (%d bytes)", dest, len(content))


async def regenerate_configs(db: AsyncSession) -> None:
    data = await _load_data(db)
    _write("pjsip.conf", _env.get_template("pjsip.conf.j2").render(**data))
    _write("extensions.conf", _env.get_template("extensions.conf.j2").render(**data))
    _write("voicemail.conf", _env.get_template("voicemail.conf.j2").render(**data))


async def regenerate_and_reload(db: AsyncSession) -> None:
    await regenerate_configs(db)
    try:
        await ami.pjsip_reload()
        await ami.dialplan_reload()
        await ami.voicemail_reload()
    except Exception:
        logger.exception("AMI reload failed after config regeneration — files were written, "
                          "Asterisk will need a manual reload once AMI is reachable again")
