"""Shared DB operations for extensions/trunks/routes, used by both the JSON
API routers and the HTMX page routers so business logic (including
regenerating Asterisk config after a write) lives in exactly one place."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config_generator import regenerate_and_reload
from app.models import Extension, InboundRoute, OutboundRoute, Trunk


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass


# ------------------------------------------------------------------ #
# Extensions                                                           #
# ------------------------------------------------------------------ #

async def list_extensions(db: AsyncSession) -> list[Extension]:
    return (await db.execute(select(Extension).order_by(Extension.extension))).scalars().all()


async def get_extension(db: AsyncSession, extension_id: int) -> Extension:
    ext = await db.get(Extension, extension_id)
    if ext is None:
        raise NotFoundError(f"Extension {extension_id} not found")
    return ext


async def get_extension_by_number(db: AsyncSession, number: str) -> Extension:
    ext = (await db.execute(select(Extension).where(Extension.extension == number))).scalar_one_or_none()
    if ext is None:
        raise NotFoundError(f"Extension {number} not found")
    return ext


async def create_extension(db: AsyncSession, data: dict) -> Extension:
    existing = (
        await db.execute(select(Extension).where(Extension.extension == data["extension"]))
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(f"Extension {data['extension']} already exists")
    ext = Extension(**data)
    db.add(ext)
    await db.commit()
    await db.refresh(ext)
    await regenerate_and_reload(db)
    return ext


async def update_extension(db: AsyncSession, extension_id: int, data: dict) -> Extension:
    ext = await get_extension(db, extension_id)
    for k, v in data.items():
        if v is not None:
            setattr(ext, k, v)
    await db.commit()
    await db.refresh(ext)
    await regenerate_and_reload(db)
    return ext


async def delete_extension(db: AsyncSession, extension_id: int) -> None:
    ext = await get_extension(db, extension_id)
    await db.delete(ext)
    await db.commit()
    await regenerate_and_reload(db)


# ------------------------------------------------------------------ #
# Trunks                                                               #
# ------------------------------------------------------------------ #

async def list_trunks(db: AsyncSession) -> list[Trunk]:
    return (await db.execute(select(Trunk).order_by(Trunk.name))).scalars().all()


async def get_trunk(db: AsyncSession, trunk_id: int) -> Trunk:
    trunk = await db.get(Trunk, trunk_id)
    if trunk is None:
        raise NotFoundError(f"Trunk {trunk_id} not found")
    return trunk


async def create_trunk(db: AsyncSession, data: dict) -> Trunk:
    existing = (await db.execute(select(Trunk).where(Trunk.name == data["name"]))).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(f"Trunk {data['name']} already exists")
    trunk = Trunk(**data)
    db.add(trunk)
    await db.commit()
    await db.refresh(trunk)
    await regenerate_and_reload(db)
    return trunk


async def update_trunk(db: AsyncSession, trunk_id: int, data: dict) -> Trunk:
    trunk = await get_trunk(db, trunk_id)
    for k, v in data.items():
        if v is not None:
            setattr(trunk, k, v)
    await db.commit()
    await db.refresh(trunk)
    await regenerate_and_reload(db)
    return trunk


async def delete_trunk(db: AsyncSession, trunk_id: int) -> None:
    trunk = await get_trunk(db, trunk_id)
    await db.delete(trunk)
    await db.commit()
    await regenerate_and_reload(db)


# ------------------------------------------------------------------ #
# Inbound routes                                                       #
# ------------------------------------------------------------------ #

async def list_inbound_routes(db: AsyncSession) -> list[InboundRoute]:
    return (await db.execute(select(InboundRoute).order_by(InboundRoute.did_number))).scalars().all()


async def get_inbound_route(db: AsyncSession, route_id: int) -> InboundRoute:
    route = await db.get(InboundRoute, route_id)
    if route is None:
        raise NotFoundError(f"Inbound route {route_id} not found")
    return route


async def create_inbound_route(db: AsyncSession, data: dict) -> InboundRoute:
    route = InboundRoute(**data)
    db.add(route)
    await db.commit()
    await db.refresh(route)
    await regenerate_and_reload(db)
    return route


async def update_inbound_route(db: AsyncSession, route_id: int, data: dict) -> InboundRoute:
    route = await get_inbound_route(db, route_id)
    for k, v in data.items():
        if v is not None:
            setattr(route, k, v)
    await db.commit()
    await db.refresh(route)
    await regenerate_and_reload(db)
    return route


async def delete_inbound_route(db: AsyncSession, route_id: int) -> None:
    route = await get_inbound_route(db, route_id)
    await db.delete(route)
    await db.commit()
    await regenerate_and_reload(db)


# ------------------------------------------------------------------ #
# Outbound routes                                                      #
# ------------------------------------------------------------------ #

async def list_outbound_routes(db: AsyncSession) -> list[OutboundRoute]:
    return (
        await db.execute(select(OutboundRoute).order_by(OutboundRoute.pattern, OutboundRoute.priority))
    ).scalars().all()


async def get_outbound_route(db: AsyncSession, route_id: int) -> OutboundRoute:
    route = await db.get(OutboundRoute, route_id)
    if route is None:
        raise NotFoundError(f"Outbound route {route_id} not found")
    return route


async def create_outbound_route(db: AsyncSession, data: dict) -> OutboundRoute:
    route = OutboundRoute(**data)
    db.add(route)
    await db.commit()
    await db.refresh(route)
    await regenerate_and_reload(db)
    return route


async def update_outbound_route(db: AsyncSession, route_id: int, data: dict) -> OutboundRoute:
    route = await get_outbound_route(db, route_id)
    for k, v in data.items():
        if v is not None:
            setattr(route, k, v)
    await db.commit()
    await db.refresh(route)
    await regenerate_and_reload(db)
    return route


async def delete_outbound_route(db: AsyncSession, route_id: int) -> None:
    route = await get_outbound_route(db, route_id)
    await db.delete(route)
    await db.commit()
    await regenerate_and_reload(db)
