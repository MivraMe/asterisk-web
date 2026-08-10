from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.database import get_db
from app.schemas import RingGroupCreate, RingGroupOut, RingGroupUpdate

router = APIRouter()


@router.get("", response_model=list[RingGroupOut])
async def list_ring_groups(db: AsyncSession = Depends(get_db)):
    return await crud.list_ring_groups(db)


@router.post("", response_model=RingGroupOut, status_code=201)
async def create_ring_group(payload: RingGroupCreate, db: AsyncSession = Depends(get_db)):
    try:
        return await crud.create_ring_group(db, payload.model_dump())
    except crud.ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put("/{ring_group_id}", response_model=RingGroupOut)
async def update_ring_group(ring_group_id: int, payload: RingGroupUpdate, db: AsyncSession = Depends(get_db)):
    try:
        return await crud.update_ring_group(db, ring_group_id, payload.model_dump(exclude_unset=True))
    except crud.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{ring_group_id}", status_code=204)
async def delete_ring_group(ring_group_id: int, db: AsyncSession = Depends(get_db)):
    try:
        await crud.delete_ring_group(db, ring_group_id)
    except crud.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
