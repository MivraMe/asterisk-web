import asyncio
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import func, select

from asterisk_ami import ami
from asterisk_cli import (
    core_show_uptime,
    parse_pjsip_endpoints_output,
    pjsip_show_endpoints,
    run_asterisk_command,
)
from database import AsyncSessionLocal
from models import Call, Log

# Commands allowed through the diagnostics endpoint (sent via AMI Command action)
_DIAG_ALLOWED = {
    "core show uptime",
    "pjsip show endpoints",
    "core show channels concise",
    "dialplan show",
    "core show version",
    "core show channels",
}

router = APIRouter()


@router.get("/status", summary="Asterisk server status")
async def get_status() -> dict:
    connected = ami.is_connected
    uptime: dict = {}
    endpoint_count = 0
    endpoints_up = 0

    if connected:
        # Prefer AMI Command (works even when Asterisk is on a remote host)
        try:
            lines = await ami.send_command("core show uptime")
            for line in lines:
                if ":" in line and "--END" not in line:
                    key, _, val = line.partition(":")
                    uptime[key.strip()] = val.strip()
        except Exception:
            try:
                uptime = await core_show_uptime()
            except Exception:
                pass
        try:
            lines = await ami.send_command("pjsip show endpoints")
            eps = parse_pjsip_endpoints_output(lines)
            endpoint_count = len(eps)
            endpoints_up = sum(
                1 for e in eps if e.get("state") not in ("Unavailable", "Unknown")
            )
        except Exception:
            try:
                eps = await pjsip_show_endpoints()
                endpoint_count = len(eps)
                endpoints_up = sum(
                    1 for e in eps if e.get("state") not in ("Unavailable", "Unknown")
                )
            except Exception:
                pass

    return {
        "ami_connected": connected,
        "uptime": uptime,
        "endpoint_count": endpoint_count,
        "endpoints_up": endpoints_up,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/diag", summary="Run a diagnostics command via AMI")
async def run_diag(cmd: str = Query(..., description="CLI command to run")) -> dict:
    if cmd not in _DIAG_ALLOWED:
        raise HTTPException(
            status_code=422,
            detail=f"Command not allowed. Permitted: {sorted(_DIAG_ALLOWED)}",
        )
    try:
        lines = await ami.send_command(cmd)
        # Strip the "--END COMMAND--" sentinel Asterisk appends
        output = [l for l in lines if l != "--END COMMAND--"]
        return {"cmd": cmd, "output": output, "source": "ami"}
    except ConnectionError as exc:
        raise HTTPException(status_code=503, detail=f"AMI not connected: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))


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
