from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.database import get_db
from app.schemas import ExtensionCreate, ExtensionOut, ExtensionUpdate

router = APIRouter()


@router.get("", response_model=list[ExtensionOut])
async def list_extensions(db: AsyncSession = Depends(get_db)):
    return await crud.list_extensions(db)


@router.post("", response_model=ExtensionOut, status_code=201)
async def create_extension(payload: ExtensionCreate, db: AsyncSession = Depends(get_db)):
    try:
        return await crud.create_extension(db, payload.model_dump())
    except crud.ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put("/{extension_id}", response_model=ExtensionOut)
async def update_extension(extension_id: int, payload: ExtensionUpdate, db: AsyncSession = Depends(get_db)):
    try:
        return await crud.update_extension(db, extension_id, payload.model_dump(exclude_unset=True))
    except crud.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{extension_id}", status_code=204)
async def delete_extension(extension_id: int, db: AsyncSession = Depends(get_db)):
    try:
        await crud.delete_extension(db, extension_id)
    except crud.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
