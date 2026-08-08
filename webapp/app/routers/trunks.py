from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.database import get_db
from app.schemas import TrunkCreate, TrunkOut, TrunkUpdate

router = APIRouter()


@router.get("", response_model=list[TrunkOut])
async def list_trunks(db: AsyncSession = Depends(get_db)):
    return await crud.list_trunks(db)


@router.post("", response_model=TrunkOut, status_code=201)
async def create_trunk(payload: TrunkCreate, db: AsyncSession = Depends(get_db)):
    try:
        return await crud.create_trunk(db, payload.model_dump())
    except crud.ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put("/{trunk_id}", response_model=TrunkOut)
async def update_trunk(trunk_id: int, payload: TrunkUpdate, db: AsyncSession = Depends(get_db)):
    try:
        return await crud.update_trunk(db, trunk_id, payload.model_dump(exclude_unset=True))
    except crud.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{trunk_id}", status_code=204)
async def delete_trunk(trunk_id: int, db: AsyncSession = Depends(get_db)):
    try:
        await crud.delete_trunk(db, trunk_id)
    except crud.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
