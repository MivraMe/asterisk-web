"""Renders pjsip.conf / extensions.conf / voicemail.conf from DB state.

The database is the source of truth. Every time an extension, trunk or
route changes, the CRUD routers call `regenerate_and_reload()` which
re-renders all three files and asks Asterisk (over AMI) to reload just the
affected modules — no container restart, no dropped calls.
"""
import logging
import random
from itertools import groupby
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ami_client import ami
from app.config import settings
from app.models import Extension, InboundRoute, OutboundRoute, RingGroup, Trunk

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates" / "asterisk"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    trim_blocks=True,
    lstrip_blocks=True,
    autoescape=select_autoescape(disabled_extensions=("j2",), default=False),
)


def _shuffle_filter(seq):
    # Used by ring groups with strategy="random" — reshuffled on every
    # regeneration, not per-call (Asterisk's dialplan has no native random
    # dial order without app_queue), but good enough to vary who's first.
    items = list(seq)
    random.shuffle(items)
    return items


_env.filters["shuffle"] = _shuffle_filter


async def _load_data(db: AsyncSession) -> dict:
    extensions = (await db.execute(select(Extension).order_by(Extension.extension))).scalars().all()
    trunks = (await db.execute(select(Trunk).order_by(Trunk.name))).scalars().all()
    ring_groups = (await db.execute(select(RingGroup).order_by(RingGroup.name))).scalars().all()
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
        "ring_groups": ring_groups,
        "inbound_routes": inbound_routes,
        "outbound_by_pattern": outbound_by_pattern,
        "voicemail_from_email": settings.voicemail_from_email,
    }


def _write(name: str, content: str) -> None:
    dest = Path(settings.asterisk_etc_dir) / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content)
    logger.info("Wrote %s (%d bytes)", dest, len(content))


async def regenerate_configs(db: AsyncSession, reason: str = "unspecified") -> None:
    # Every call re-renders all three files in full from current DB state —
    # there is no partial/incremental regeneration. Any manual edit to
    # pjsip.conf/extensions.conf/voicemail.conf is lost the next time *any*
    # extension, trunk, inbound route or outbound route is created, updated
    # or deleted (or POST /api/reload is called) — not just when the record
    # you edited around changes. The reason is logged so it's traceable in
    # the webapp's own logs which action caused a given regeneration.
    logger.info("Regenerating pjsip.conf/extensions.conf/voicemail.conf from DB state (reason: %s)", reason)
    data = await _load_data(db)
    _write("pjsip.conf", _env.get_template("pjsip.conf.j2").render(**data))
    _write("extensions.conf", _env.get_template("extensions.conf.j2").render(**data))
    _write("voicemail.conf", _env.get_template("voicemail.conf.j2").render(**data))


async def regenerate_and_reload(db: AsyncSession, reason: str = "unspecified") -> None:
    await regenerate_configs(db, reason=reason)
    try:
        await ami.pjsip_reload()
        await ami.dialplan_reload()
        await ami.voicemail_reload()
    except Exception:
        logger.exception("AMI reload failed after config regeneration — files were written, "
                          "Asterisk will need a manual reload once AMI is reachable again")
