from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.database import get_db
from app.schemas import IvrSettingsOut, IvrSettingsUpdate

router = APIRouter()


@router.get("", response_model=IvrSettingsOut)
async def get_ivr_settings(db: AsyncSession = Depends(get_db)):
    return await crud.get_ivr_settings(db)


@router.put("", response_model=IvrSettingsOut)
async def update_ivr_settings(payload: IvrSettingsUpdate, db: AsyncSession = Depends(get_db)):
    return await crud.update_ivr_settings(db, payload.model_dump(exclude_unset=True))
