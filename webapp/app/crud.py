"""Shared DB operations for extensions/trunks/routes, used by both the JSON
API routers and the HTMX page routers so business logic (including
regenerating Asterisk config after a write) lives in exactly one place."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config_generator import regenerate_and_reload
from app.models import Extension, InboundRoute, OutboundRoute, RingGroup, Trunk


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
    await regenerate_and_reload(db, reason=f"extension {ext.extension} created")
    return ext


async def update_extension(db: AsyncSession, extension_id: int, data: dict) -> Extension:
    ext = await get_extension(db, extension_id)
    for k, v in data.items():
        if v is not None:
            setattr(ext, k, v)
    await db.commit()
    await db.refresh(ext)
    await regenerate_and_reload(db, reason=f"extension {ext.extension} updated")
    return ext


async def delete_extension(db: AsyncSession, extension_id: int) -> None:
    ext = await get_extension(db, extension_id)
    number = ext.extension
    await db.delete(ext)
    await db.commit()
    await regenerate_and_reload(db, reason=f"extension {number} deleted")


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
    await regenerate_and_reload(db, reason=f"trunk {trunk.name} created")
    return trunk


async def update_trunk(db: AsyncSession, trunk_id: int, data: dict) -> Trunk:
    trunk = await get_trunk(db, trunk_id)
    for k, v in data.items():
        if v is not None:
            setattr(trunk, k, v)
    await db.commit()
    await db.refresh(trunk)
    await regenerate_and_reload(db, reason=f"trunk {trunk.name} updated")
    return trunk


async def delete_trunk(db: AsyncSession, trunk_id: int) -> None:
    trunk = await get_trunk(db, trunk_id)
    name = trunk.name
    await db.delete(trunk)
    await db.commit()
    await regenerate_and_reload(db, reason=f"trunk {name} deleted")


# ------------------------------------------------------------------ #
# Ring groups                                                          #
# ------------------------------------------------------------------ #

async def list_ring_groups(db: AsyncSession) -> list[RingGroup]:
    return (await db.execute(select(RingGroup).order_by(RingGroup.name))).scalars().all()


async def get_ring_group(db: AsyncSession, ring_group_id: int) -> RingGroup:
    rg = await db.get(RingGroup, ring_group_id)
    if rg is None:
        raise NotFoundError(f"Ring group {ring_group_id} not found")
    return rg


async def create_ring_group(db: AsyncSession, data: dict) -> RingGroup:
    existing = (await db.execute(select(RingGroup).where(RingGroup.name == data["name"]))).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(f"Ring group {data['name']} already exists")
    rg = RingGroup(**data)
    db.add(rg)
    await db.commit()
    await db.refresh(rg)
    await regenerate_and_reload(db, reason=f"ring group {rg.name} created")
    return rg


async def update_ring_group(db: AsyncSession, ring_group_id: int, data: dict) -> RingGroup:
    rg = await get_ring_group(db, ring_group_id)
    for k, v in data.items():
        if v is not None:
            setattr(rg, k, v)
    await db.commit()
    await db.refresh(rg)
    await regenerate_and_reload(db, reason=f"ring group {rg.name} updated")
    return rg


async def delete_ring_group(db: AsyncSession, ring_group_id: int) -> None:
    rg = await get_ring_group(db, ring_group_id)
    name = rg.name
    await db.delete(rg)
    await db.commit()
    await regenerate_and_reload(db, reason=f"ring group {name} deleted")


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
    await regenerate_and_reload(db, reason=f"inbound route {route.did_number} created")
    return route


async def update_inbound_route(db: AsyncSession, route_id: int, data: dict) -> InboundRoute:
    route = await get_inbound_route(db, route_id)
    for k, v in data.items():
        if v is not None:
            setattr(route, k, v)
    await db.commit()
    await db.refresh(route)
    await regenerate_and_reload(db, reason=f"inbound route {route.did_number} updated")
    return route


async def delete_inbound_route(db: AsyncSession, route_id: int) -> None:
    route = await get_inbound_route(db, route_id)
    did = route.did_number
    await db.delete(route)
    await db.commit()
    await regenerate_and_reload(db, reason=f"inbound route {did} deleted")


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
    await regenerate_and_reload(db, reason=f"outbound route {route.pattern} created")
    return route


async def update_outbound_route(db: AsyncSession, route_id: int, data: dict) -> OutboundRoute:
    route = await get_outbound_route(db, route_id)
    for k, v in data.items():
        if v is not None:
            setattr(route, k, v)
    await db.commit()
    await db.refresh(route)
    await regenerate_and_reload(db, reason=f"outbound route {route.pattern} updated")
    return route


async def delete_outbound_route(db: AsyncSession, route_id: int) -> None:
    route = await get_outbound_route(db, route_id)
    pattern = route.pattern
    await db.delete(route)
    await db.commit()
    await regenerate_and_reload(db, reason=f"outbound route {pattern} deleted")
