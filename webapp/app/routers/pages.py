from datetime import date, datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.ami_client import AMIError, ami
from app.database import get_db
from app.models import CDR, Trunk
from app.routers.cdr import _apply_filters
from sqlalchemy import func
from app.schemas import (
    CDRPage,
    ExtensionCreate,
    ExtensionUpdate,
    InboundRouteCreate,
    InboundRouteUpdate,
    OutboundRouteCreate,
    OutboundRouteUpdate,
    RingGroupCreate,
    RingGroupUpdate,
    TrunkCreate,
    TrunkUpdate,
    VoicemailUpdate,
)
from app.security import read_session_token
from app.config import settings
from app.templating import templates

router = APIRouter()


def _err(exc: ValidationError) -> str:
    first = exc.errors()[0]
    loc = ".".join(str(p) for p in first["loc"])
    return f"{loc}: {first['msg']}"


# ------------------------------------------------------------------ #
# Login page (GET only — POST handled by routers/auth.py)             #
# ------------------------------------------------------------------ #

@router.get("/login")
async def login_page(request: Request, next: str = "/"):
    token = request.cookies.get(settings.session_cookie_name)
    if token and read_session_token(token) is not None:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request, "pages/login.html", {"next": next})


# ------------------------------------------------------------------ #
# Dashboard                                                            #
# ------------------------------------------------------------------ #

@router.get("/")
async def dashboard(request: Request):
    return templates.TemplateResponse(request, "pages/dashboard.html", {"nav_active": "dashboard"})


@router.get("/partials/ami-status")
async def partial_ami_status(request: Request):
    return templates.TemplateResponse(request, "partials/ami_status.html", {"connected": ami.is_connected})


@router.get("/partials/registrations")
async def partial_registrations(request: Request):
    try:
        events = await ami.get_endpoints()
        endpoints = [
            {"endpoint": e.get("ObjectName"), "device_state": e.get("DeviceState"), "active_channels": e.get("ActiveChannels")}
            for e in events
        ]
        return templates.TemplateResponse(request, "partials/registrations.html", {"endpoints": endpoints})
    except (AMIError, TimeoutError) as exc:
        return templates.TemplateResponse(request, "partials/registrations.html", {"error": str(exc)})


@router.get("/partials/active-calls")
async def partial_active_calls(request: Request):
    try:
        events = await ami.get_channels()
        calls = [
            {
                "channel": e.get("Channel"), "caller_id": e.get("CallerIDNum"),
                "context": e.get("Context"), "extension": e.get("Extension"),
                "application": e.get("Application"), "duration": e.get("Duration"),
            }
            for e in events
        ]
        return templates.TemplateResponse(request, "partials/active_calls.html", {"calls": calls})
    except (AMIError, TimeoutError) as exc:
        return templates.TemplateResponse(request, "partials/active_calls.html", {"error": str(exc)})


# ------------------------------------------------------------------ #
# Extensions                                                           #
# ------------------------------------------------------------------ #

@router.get("/extensions")
async def extensions_list(request: Request, db: AsyncSession = Depends(get_db)):
    extensions = await crud.list_extensions(db)
    return templates.TemplateResponse(request, "pages/extensions.html", {"nav_active": "extensions", "extensions": extensions})


@router.get("/extensions/new")
async def extension_new_form(request: Request):
    return templates.TemplateResponse(request, "pages/extension_form.html", {"nav_active": "extensions", "ext": None})


@router.post("/extensions/new")
async def extension_new_submit(
    request: Request,
    extension: str = Form(...),
    display_name: str = Form(""),
    context: str = Form("internal"),
    sip_password: str = Form(...),
    voicemail_enabled: str | None = Form(None),
    voicemail_pin: str = Form(""),
    voicemail_email: str = Form(""),
    follow_me_enabled: str | None = Form(None),
    follow_me_numbers: str = Form(""),
    follow_me_timeout: int = Form(20),
    follow_me_strategy: str = Form("simultaneous"),
    db: AsyncSession = Depends(get_db),
):
    form = {
        "extension": extension, "display_name": display_name, "context": context,
        "sip_password": sip_password, "voicemail_enabled": bool(voicemail_enabled),
        "voicemail_pin": voicemail_pin, "voicemail_email": voicemail_email,
        "follow_me_enabled": bool(follow_me_enabled), "follow_me_numbers": _parse_dids(follow_me_numbers),
        "follow_me_timeout": follow_me_timeout, "follow_me_strategy": follow_me_strategy,
    }
    try:
        payload = ExtensionCreate(**form)
        await crud.create_extension(db, payload.model_dump())
    except ValidationError as exc:
        return templates.TemplateResponse(request, "pages/extension_form.html", {"ext": None, "form": form, "error": _err(exc)}, status_code=400)
    except crud.ConflictError as exc:
        return templates.TemplateResponse(request, "pages/extension_form.html", {"ext": None, "form": form, "error": str(exc)}, status_code=409)
    return RedirectResponse(url="/extensions", status_code=303)


@router.get("/extensions/{extension_id}/edit")
async def extension_edit_form(extension_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    ext = await crud.get_extension(db, extension_id)
    return templates.TemplateResponse(request, "pages/extension_form.html", {"nav_active": "extensions", "ext": ext})


@router.post("/extensions/{extension_id}/edit")
async def extension_edit_submit(
    extension_id: int,
    request: Request,
    display_name: str = Form(""),
    context: str = Form("internal"),
    sip_password: str = Form(""),
    voicemail_enabled: str | None = Form(None),
    voicemail_pin: str = Form(""),
    voicemail_email: str = Form(""),
    follow_me_enabled: str | None = Form(None),
    follow_me_numbers: str = Form(""),
    follow_me_timeout: int = Form(20),
    follow_me_strategy: str = Form("simultaneous"),
    db: AsyncSession = Depends(get_db),
):
    form = {
        "display_name": display_name, "context": context,
        "sip_password": sip_password or None, "voicemail_enabled": bool(voicemail_enabled),
        "voicemail_pin": voicemail_pin, "voicemail_email": voicemail_email,
        "follow_me_enabled": bool(follow_me_enabled), "follow_me_numbers": _parse_dids(follow_me_numbers),
        "follow_me_timeout": follow_me_timeout, "follow_me_strategy": follow_me_strategy,
    }
    try:
        payload = ExtensionUpdate(**form)
        await crud.update_extension(db, extension_id, payload.model_dump(exclude_unset=True))
    except ValidationError as exc:
        ext = await crud.get_extension(db, extension_id)
        return templates.TemplateResponse(request, "pages/extension_form.html", {"ext": ext, "form": form, "error": _err(exc)}, status_code=400)
    return RedirectResponse(url="/extensions", status_code=303)


# ------------------------------------------------------------------ #
# Trunks                                                               #
# ------------------------------------------------------------------ #

def _parse_dids(raw: str) -> list[str]:
    return [d.strip() for d in raw.split(",") if d.strip()]


def _parse_codecs(raw: str) -> list[str] | None:
    codecs = [c.strip().lower() for c in raw.split(",") if c.strip()]
    return codecs or None


@router.get("/trunks")
async def trunks_list(request: Request, db: AsyncSession = Depends(get_db)):
    trunks = await crud.list_trunks(db)
    return templates.TemplateResponse(request, "pages/trunks.html", {"nav_active": "trunks", "trunks": trunks})


@router.get("/trunks/new")
async def trunk_new_form(request: Request):
    return templates.TemplateResponse(request, "pages/trunk_form.html", {"nav_active": "trunks", "trunk": None})


@router.post("/trunks/new")
async def trunk_new_submit(
    request: Request,
    name: str = Form(...),
    provider: str = Form(...),
    sip_server: str = Form(...),
    username: str = Form(...),
    secret: str = Form(...),
    did_numbers: str = Form(""),
    codecs: str = Form(""),
    callerid: str = Form(""),
    max_channels: int = Form(5),
    enabled: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    form = {
        "name": name, "provider": provider, "sip_server": sip_server, "username": username,
        "did_numbers": _parse_dids(did_numbers), "codecs": _parse_codecs(codecs),
        "callerid": callerid or None, "max_channels": max_channels, "enabled": bool(enabled),
    }
    try:
        payload = TrunkCreate(secret=secret, **form)
        await crud.create_trunk(db, payload.model_dump())
    except ValidationError as exc:
        return templates.TemplateResponse(request, "pages/trunk_form.html", {"trunk": None, "form": form, "error": _err(exc)}, status_code=400)
    except crud.ConflictError as exc:
        return templates.TemplateResponse(request, "pages/trunk_form.html", {"trunk": None, "form": form, "error": str(exc)}, status_code=409)
    return RedirectResponse(url="/trunks", status_code=303)


@router.get("/trunks/{trunk_id}/edit")
async def trunk_edit_form(trunk_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    trunk = await crud.get_trunk(db, trunk_id)
    return templates.TemplateResponse(request, "pages/trunk_form.html", {"nav_active": "trunks", "trunk": trunk})


@router.post("/trunks/{trunk_id}/edit")
async def trunk_edit_submit(
    trunk_id: int,
    request: Request,
    provider: str = Form(...),
    sip_server: str = Form(...),
    username: str = Form(...),
    secret: str = Form(""),
    did_numbers: str = Form(""),
    codecs: str = Form(""),
    callerid: str = Form(""),
    max_channels: int = Form(5),
    enabled: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    form = {
        "provider": provider, "sip_server": sip_server, "username": username,
        "secret": secret or None, "did_numbers": _parse_dids(did_numbers), "codecs": _parse_codecs(codecs),
        "callerid": callerid or None, "max_channels": max_channels, "enabled": bool(enabled),
    }
    try:
        payload = TrunkUpdate(**form)
        await crud.update_trunk(db, trunk_id, payload.model_dump(exclude_unset=True))
    except ValidationError as exc:
        trunk = await crud.get_trunk(db, trunk_id)
        return templates.TemplateResponse(request, "pages/trunk_form.html", {"trunk": trunk, "form": form, "error": _err(exc)}, status_code=400)
    return RedirectResponse(url="/trunks", status_code=303)


# ------------------------------------------------------------------ #
# Ring groups                                                          #
# ------------------------------------------------------------------ #

@router.get("/ring-groups")
async def ring_groups_list(request: Request, db: AsyncSession = Depends(get_db)):
    ring_groups = await crud.list_ring_groups(db)
    return templates.TemplateResponse(request, "pages/ring_groups.html", {"nav_active": "ring-groups", "ring_groups": ring_groups})


@router.get("/ring-groups/new")
async def ring_group_new_form(request: Request, db: AsyncSession = Depends(get_db)):
    all_extensions = await crud.list_extensions(db)
    return templates.TemplateResponse(request, "pages/ring_group_form.html", {"nav_active": "ring-groups", "ring_group": None, "all_extensions": all_extensions})


@router.post("/ring-groups/new")
async def ring_group_new_submit(
    request: Request,
    name: str = Form(...),
    members: list[str] = Form(default=[]),
    strategy: str = Form("ringall"),
    ring_timeout: int = Form(20),
    fallback_destination_type: str = Form("voicemail"),
    fallback_destination_value: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    form = {
        "name": name, "members": members, "strategy": strategy, "ring_timeout": ring_timeout,
        "fallback_destination_type": fallback_destination_type,
        "fallback_destination_value": fallback_destination_value,
    }
    try:
        payload = RingGroupCreate(
            name=name, extensions=members, strategy=strategy, ring_timeout=ring_timeout,
            fallback_destination_type=fallback_destination_type,
            fallback_destination_value=fallback_destination_value or None,
        )
        await crud.create_ring_group(db, payload.model_dump())
    except ValidationError as exc:
        all_extensions = await crud.list_extensions(db)
        return templates.TemplateResponse(request, "pages/ring_group_form.html", {"ring_group": None, "form": form, "all_extensions": all_extensions, "error": _err(exc)}, status_code=400)
    except crud.ConflictError as exc:
        all_extensions = await crud.list_extensions(db)
        return templates.TemplateResponse(request, "pages/ring_group_form.html", {"ring_group": None, "form": form, "all_extensions": all_extensions, "error": str(exc)}, status_code=409)
    return RedirectResponse(url="/ring-groups", status_code=303)


@router.get("/ring-groups/{ring_group_id}/edit")
async def ring_group_edit_form(ring_group_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    ring_group = await crud.get_ring_group(db, ring_group_id)
    all_extensions = await crud.list_extensions(db)
    return templates.TemplateResponse(request, "pages/ring_group_form.html", {"nav_active": "ring-groups", "ring_group": ring_group, "all_extensions": all_extensions})


@router.post("/ring-groups/{ring_group_id}/edit")
async def ring_group_edit_submit(
    ring_group_id: int,
    request: Request,
    members: list[str] = Form(default=[]),
    strategy: str = Form("ringall"),
    ring_timeout: int = Form(20),
    fallback_destination_type: str = Form("voicemail"),
    fallback_destination_value: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = RingGroupUpdate(
            extensions=members, strategy=strategy, ring_timeout=ring_timeout,
            fallback_destination_type=fallback_destination_type,
            fallback_destination_value=fallback_destination_value or None,
        )
        await crud.update_ring_group(db, ring_group_id, payload.model_dump(exclude_unset=True))
    except ValidationError as exc:
        ring_group = await crud.get_ring_group(db, ring_group_id)
        all_extensions = await crud.list_extensions(db)
        return templates.TemplateResponse(request, "pages/ring_group_form.html", {"ring_group": ring_group, "all_extensions": all_extensions, "error": _err(exc)}, status_code=400)
    return RedirectResponse(url="/ring-groups", status_code=303)


# ------------------------------------------------------------------ #
# Inbound routes                                                       #
# ------------------------------------------------------------------ #

async def _trunk_names(db: AsyncSession) -> dict[int, str]:
    trunks = (await db.execute(select(Trunk))).scalars().all()
    return {t.id: t.name for t in trunks}


@router.get("/inbound-routes")
async def inbound_routes_list(request: Request, db: AsyncSession = Depends(get_db)):
    routes = await crud.list_inbound_routes(db)
    return templates.TemplateResponse(
        request, "pages/inbound_routes.html",
        {"nav_active": "inbound-routes", "routes": routes, "trunk_names": await _trunk_names(db)},
    )


async def _destination_hints(db: AsyncSession) -> list[str]:
    extensions = await crud.list_extensions(db)
    ring_groups = await crud.list_ring_groups(db)
    return [e.extension for e in extensions] + [rg.name for rg in ring_groups]


@router.get("/inbound-routes/new")
async def inbound_route_new_form(request: Request, db: AsyncSession = Depends(get_db)):
    trunks = await crud.list_trunks(db)
    return templates.TemplateResponse(
        request, "pages/inbound_route_form.html",
        {"nav_active": "inbound-routes", "route": None, "trunks": trunks, "destination_hints": await _destination_hints(db)},
    )


def _time_condition_from_form(tc_start: str, tc_end: str, tc_days: str, tc_night_value: str) -> dict | None:
    if not (tc_start and tc_end and tc_days):
        return None
    return {
        "start": tc_start, "end": tc_end, "days": tc_days,
        "night_destination_type": "extension", "night_destination_value": tc_night_value or None,
    }


@router.post("/inbound-routes/new")
async def inbound_route_new_submit(
    request: Request,
    did_number: str = Form(...),
    trunk_id: int = Form(...),
    destination_type: str = Form(...),
    destination_value: str = Form(...),
    tc_start: str = Form(""),
    tc_end: str = Form(""),
    tc_days: str = Form(""),
    tc_night_value: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    form = {
        "did_number": did_number, "trunk_id": trunk_id, "destination_type": destination_type,
        "destination_value": destination_value, "tc_start": tc_start, "tc_end": tc_end,
        "tc_days": tc_days, "tc_night_value": tc_night_value,
    }
    try:
        payload = InboundRouteCreate(
            did_number=did_number, trunk_id=trunk_id, destination_type=destination_type,
            destination_value=destination_value,
            time_condition=_time_condition_from_form(tc_start, tc_end, tc_days, tc_night_value),
        )
        await crud.create_inbound_route(db, payload.model_dump())
    except ValidationError as exc:
        trunks = await crud.list_trunks(db)
        return templates.TemplateResponse(
            request, "pages/inbound_route_form.html",
            {"route": None, "form": form, "trunks": trunks, "destination_hints": await _destination_hints(db), "error": _err(exc)},
            status_code=400,
        )
    return RedirectResponse(url="/inbound-routes", status_code=303)


@router.get("/inbound-routes/{route_id}/edit")
async def inbound_route_edit_form(route_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    route = await crud.get_inbound_route(db, route_id)
    trunks = await crud.list_trunks(db)
    return templates.TemplateResponse(
        request, "pages/inbound_route_form.html",
        {"nav_active": "inbound-routes", "route": route, "trunks": trunks, "destination_hints": await _destination_hints(db)},
    )


@router.post("/inbound-routes/{route_id}/edit")
async def inbound_route_edit_submit(
    route_id: int,
    request: Request,
    did_number: str = Form(...),
    trunk_id: int = Form(...),
    destination_type: str = Form(...),
    destination_value: str = Form(...),
    tc_start: str = Form(""),
    tc_end: str = Form(""),
    tc_days: str = Form(""),
    tc_night_value: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = InboundRouteUpdate(
            did_number=did_number, trunk_id=trunk_id, destination_type=destination_type,
            destination_value=destination_value,
            time_condition=_time_condition_from_form(tc_start, tc_end, tc_days, tc_night_value),
        )
        await crud.update_inbound_route(db, route_id, payload.model_dump(exclude_unset=True))
    except ValidationError as exc:
        route = await crud.get_inbound_route(db, route_id)
        trunks = await crud.list_trunks(db)
        return templates.TemplateResponse(
            request, "pages/inbound_route_form.html",
            {"route": route, "trunks": trunks, "destination_hints": await _destination_hints(db), "error": _err(exc)},
            status_code=400,
        )
    return RedirectResponse(url="/inbound-routes", status_code=303)


# ------------------------------------------------------------------ #
# Outbound routes                                                      #
# ------------------------------------------------------------------ #

@router.get("/outbound-routes")
async def outbound_routes_list(request: Request, db: AsyncSession = Depends(get_db)):
    routes = await crud.list_outbound_routes(db)
    return templates.TemplateResponse(
        request, "pages/outbound_routes.html",
        {"nav_active": "outbound-routes", "routes": routes, "trunk_names": await _trunk_names(db)},
    )


@router.get("/outbound-routes/new")
async def outbound_route_new_form(request: Request, db: AsyncSession = Depends(get_db)):
    trunks = await crud.list_trunks(db)
    return templates.TemplateResponse(request, "pages/outbound_route_form.html", {"nav_active": "outbound-routes", "route": None, "trunks": trunks})


@router.post("/outbound-routes/new")
async def outbound_route_new_submit(
    request: Request,
    pattern: str = Form(""),
    simple_patterns: list[str] = Form(default=[]),
    trunk_id: int = Form(...),
    priority: int = Form(1),
    strip_digits: int = Form(0),
    prepend: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    # simple_patterns (mode simple, checkboxes) creates one route per
    # checked pattern; pattern (mode avancé) creates a single route. The
    # form disables whichever field isn't active so only one of the two
    # is ever actually submitted.
    patterns = simple_patterns or ([pattern] if pattern else [])
    if not patterns:
        trunks = await crud.list_trunks(db)
        return templates.TemplateResponse(
            request, "pages/outbound_route_form.html",
            {"route": None, "trunks": trunks, "error": "Sélectionnez au moins un type de numéro ou entrez un pattern."},
            status_code=400,
        )
    try:
        for p in patterns:
            payload = OutboundRouteCreate(pattern=p, trunk_id=trunk_id, priority=priority, strip_digits=strip_digits, prepend=prepend or None)
            await crud.create_outbound_route(db, payload.model_dump())
    except ValidationError as exc:
        trunks = await crud.list_trunks(db)
        return templates.TemplateResponse(request, "pages/outbound_route_form.html", {"route": None, "trunks": trunks, "error": _err(exc)}, status_code=400)
    return RedirectResponse(url="/outbound-routes", status_code=303)


@router.get("/outbound-routes/{route_id}/edit")
async def outbound_route_edit_form(route_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    route = await crud.get_outbound_route(db, route_id)
    trunks = await crud.list_trunks(db)
    return templates.TemplateResponse(request, "pages/outbound_route_form.html", {"nav_active": "outbound-routes", "route": route, "trunks": trunks})


@router.post("/outbound-routes/{route_id}/edit")
async def outbound_route_edit_submit(
    route_id: int,
    request: Request,
    pattern: str = Form(...),
    trunk_id: int = Form(...),
    priority: int = Form(1),
    strip_digits: int = Form(0),
    prepend: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = OutboundRouteUpdate(pattern=pattern, trunk_id=trunk_id, priority=priority, strip_digits=strip_digits, prepend=prepend or None)
        await crud.update_outbound_route(db, route_id, payload.model_dump(exclude_unset=True))
    except ValidationError as exc:
        route = await crud.get_outbound_route(db, route_id)
        trunks = await crud.list_trunks(db)
        return templates.TemplateResponse(request, "pages/outbound_route_form.html", {"route": route, "trunks": trunks, "error": _err(exc)}, status_code=400)
    return RedirectResponse(url="/outbound-routes", status_code=303)


# ------------------------------------------------------------------ #
# Voicemail                                                            #
# ------------------------------------------------------------------ #

@router.get("/voicemail")
async def voicemail_list(request: Request, db: AsyncSession = Depends(get_db)):
    extensions = await crud.list_extensions(db)
    return templates.TemplateResponse(request, "pages/voicemail.html", {"nav_active": "voicemail", "extensions": extensions})


@router.get("/voicemail/{extension}/edit")
async def voicemail_edit_form(extension: str, request: Request, db: AsyncSession = Depends(get_db)):
    ext = await crud.get_extension_by_number(db, extension)
    return templates.TemplateResponse(request, "pages/voicemail_form.html", {"nav_active": "voicemail", "ext": ext})


@router.post("/voicemail/{extension}/edit")
async def voicemail_edit_submit(
    extension: str,
    request: Request,
    voicemail_enabled: str | None = Form(None),
    voicemail_pin: str = Form(""),
    voicemail_email: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    ext = await crud.get_extension_by_number(db, extension)
    payload = VoicemailUpdate(voicemail_enabled=bool(voicemail_enabled), voicemail_pin=voicemail_pin, voicemail_email=voicemail_email)
    await crud.update_extension(db, ext.id, payload.model_dump(exclude_unset=True))
    return RedirectResponse(url="/voicemail", status_code=303)


# ------------------------------------------------------------------ #
# CDR                                                                  #
# ------------------------------------------------------------------ #

def _parse_date(value: str | None, end_of_day: bool = False) -> datetime | None:
    if not value:
        return None
    d = date.fromisoformat(value)
    return datetime.combine(d, datetime.max.time() if end_of_day else datetime.min.time())


@router.get("/cdr")
async def cdr_page(
    request: Request,
    date_from: str | None = None,
    date_to: str | None = None,
    extension: str | None = None,
    direction: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    cdr_page = await _cdr_query(db, date_from, date_to, extension, direction, page=1)
    return templates.TemplateResponse(
        request, "pages/cdr.html",
        {
            "nav_active": "cdr", "cdr_page": cdr_page,
            "filters": {"date_from": date_from, "date_to": date_to, "extension": extension, "direction": direction},
            "query_string": request.url.query,
        },
    )


@router.get("/cdr/table")
async def cdr_table(request: Request, db: AsyncSession = Depends(get_db)):
    params = request.query_params
    cdr_page = await _cdr_query(
        db, params.get("from"), params.get("to"), params.get("extension"),
        params.get("direction") or None, page=int(params.get("page", 1)),
    )
    return templates.TemplateResponse(request, "partials/cdr_table.html", {"cdr_page": cdr_page})


async def _cdr_query(
    db: AsyncSession, date_from: str | None, date_to: str | None,
    extension: str | None, direction: str | None, page: int = 1, page_size: int = 50,
) -> CDRPage:
    stmt = _apply_filters(
        select(CDR), _parse_date(date_from), _parse_date(date_to, end_of_day=True), extension, direction,
    )
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        await db.execute(stmt.order_by(CDR.calldate.desc()).offset((page - 1) * page_size).limit(page_size))
    ).scalars().all()
    return CDRPage(total=total, page=page, page_size=page_size, items=rows)
