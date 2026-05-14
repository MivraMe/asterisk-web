import asyncio
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import func, select

from asterisk_ami import ami
from asterisk_cli import core_show_channels, core_show_uptime, pjsip_show_endpoints
from database import AsyncSessionLocal
from models import Call, Log

router = APIRouter()


@router.get("/status", summary="Asterisk server status")
async def get_status() -> dict:
    connected = ami.is_connected
    uptime = {}
    endpoint_count = 0
    endpoints_up = 0

    if connected:
        try:
            uptime = await core_show_uptime()
        except Exception:
            pass
        try:
            eps = await pjsip_show_endpoints()
            endpoint_count = len(eps)
            endpoints_up = sum(1 for e in eps if e.get("state", "").lower() not in ("unavailable", "unknown"))
        except Exception:
            pass

    return {
        "ami_connected": connected,
        "uptime": uptime,
        "endpoint_count": endpoint_count,
        "endpoints_up": endpoints_up,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/stats", summary="Call statistics")
async def get_stats() -> dict:
    async with AsyncSessionLocal() as db:
        total = (await db.execute(select(func.count(Call.id)))).scalar() or 0
        active = (await db.execute(
            select(func.count(Call.id)).where(Call.status == "active")
        )).scalar() or 0
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today = (await db.execute(
            select(func.count(Call.id)).where(Call.start_time >= today_start)
        )).scalar() or 0
    return {
        "total_calls": total,
        "active_calls": active,
        "calls_today": today,
    }


@router.get("/logs", summary="Fetch application log entries")
async def get_logs(
    level: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    module: str | None = Query(default=None),
) -> list[dict]:
    async with AsyncSessionLocal() as db:
        stmt = select(Log).order_by(Log.timestamp.desc()).limit(limit)
        if level:
            stmt = stmt.where(Log.level == level.upper())
        if module:
            stmt = stmt.where(Log.module == module)
        rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": r.id,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "level": r.level,
            "message": r.message,
            "module": r.module,
        }
        for r in rows
    ]


@router.websocket("/ws/events")
async def ws_events(websocket: WebSocket) -> None:
    await websocket.accept()
    queue = await ami.subscribe()
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_json(event)
            except asyncio.TimeoutError:
                await websocket.send_json({"Event": "Ping"})
    except WebSocketDisconnect:
        pass
    finally:
        await ami.unsubscribe(queue)
