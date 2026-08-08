from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.ami_client import AMIError, ami
from app.config_generator import regenerate_and_reload
from app.database import get_db

router = APIRouter()


@router.get("/status/registrations")
async def registrations():
    try:
        events = await ami.get_endpoints()
    except (AMIError, TimeoutError) as exc:
        raise HTTPException(status_code=503, detail=f"AMI unavailable: {exc}") from exc

    return [
        {
            "endpoint": e.get("ObjectName"),
            "device_state": e.get("DeviceState"),
            "active_channels": e.get("ActiveChannels"),
        }
        for e in events
    ]


@router.get("/status/active-calls")
async def active_calls():
    try:
        events = await ami.get_channels()
    except (AMIError, TimeoutError) as exc:
        raise HTTPException(status_code=503, detail=f"AMI unavailable: {exc}") from exc

    return [
        {
            "channel": e.get("Channel"),
            "caller_id": e.get("CallerIDNum"),
            "connected_line": e.get("ConnectedLineNum"),
            "context": e.get("Context"),
            "extension": e.get("Extension"),
            "application": e.get("Application"),
            "duration": e.get("Duration"),
        }
        for e in events
    ]


@router.post("/reload")
async def reload_config(db: AsyncSession = Depends(get_db)):
    await regenerate_and_reload(db)
    return {"status": "reloaded"}
