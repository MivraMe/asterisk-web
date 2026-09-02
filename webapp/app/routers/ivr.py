from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.config import settings
from app.database import get_db
from app.schemas import IvrGreetingStatus, IvrSettingsOut, IvrSettingsUpdate

router = APIRouter()


@router.get("", response_model=IvrSettingsOut)
async def get_ivr_settings(db: AsyncSession = Depends(get_db)):
    return await crud.get_ivr_settings(db)


@router.put("", response_model=IvrSettingsOut)
async def update_ivr_settings(payload: IvrSettingsUpdate, db: AsyncSession = Depends(get_db)):
    return await crud.update_ivr_settings(db, payload.model_dump(exclude_unset=True))


# ------------------------------------------------------------------ #
# Custom greeting — a pure filesystem artifact (not modeled in the DB),
# recorded from any internal phone by dialing *81 (see [ivr-record-greeting]
# in extensions.conf.j2). [ivr] checks for it live on every call via
# STAT(), so nothing here ever needs to trigger a dialplan regenerate/
# reload — these endpoints just read or remove the file.
# ------------------------------------------------------------------ #

def _greeting_path() -> Path:
    return Path(settings.asterisk_spool_dir) / "ivr-prompts" / "greeting.wav"


@router.get("/greeting", response_model=IvrGreetingStatus)
async def get_ivr_greeting_status():
    path = _greeting_path()
    if not path.is_file():
        return IvrGreetingStatus(configured=False)
    return IvrGreetingStatus(configured=True, recorded_at=datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc))


@router.get("/greeting/audio")
async def get_ivr_greeting_audio():
    path = _greeting_path()
    if not path.is_file():
        raise HTTPException(status_code=404, detail="No custom greeting configured")
    return FileResponse(str(path), media_type="audio/wav", filename="greeting.wav")


@router.delete("/greeting", status_code=204)
async def delete_ivr_greeting():
    _greeting_path().unlink(missing_ok=True)
    return Response(status_code=204)
