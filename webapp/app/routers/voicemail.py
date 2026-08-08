from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.database import get_db
from app.schemas import VoicemailOut, VoicemailUpdate

router = APIRouter()


@router.get("/{extension}", response_model=VoicemailOut)
async def get_voicemail(extension: str, db: AsyncSession = Depends(get_db)):
    try:
        ext = await crud.get_extension_by_number(db, extension)
    except crud.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return VoicemailOut(
        extension=ext.extension,
        voicemail_enabled=ext.voicemail_enabled,
        voicemail_pin=ext.voicemail_pin,
        voicemail_email=ext.voicemail_email,
    )


@router.put("/{extension}", response_model=VoicemailOut)
async def update_voicemail(extension: str, payload: VoicemailUpdate, db: AsyncSession = Depends(get_db)):
    try:
        ext = await crud.get_extension_by_number(db, extension)
        ext = await crud.update_extension(db, ext.id, payload.model_dump(exclude_unset=True))
    except crud.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return VoicemailOut(
        extension=ext.extension,
        voicemail_enabled=ext.voicemail_enabled,
        voicemail_pin=ext.voicemail_pin,
        voicemail_email=ext.voicemail_email,
    )
