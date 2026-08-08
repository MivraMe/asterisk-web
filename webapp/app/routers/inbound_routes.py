from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.database import get_db
from app.schemas import InboundRouteCreate, InboundRouteOut, InboundRouteUpdate

router = APIRouter()


@router.get("", response_model=list[InboundRouteOut])
async def list_inbound_routes(db: AsyncSession = Depends(get_db)):
    return await crud.list_inbound_routes(db)


@router.post("", response_model=InboundRouteOut, status_code=201)
async def create_inbound_route(payload: InboundRouteCreate, db: AsyncSession = Depends(get_db)):
    return await crud.create_inbound_route(db, payload.model_dump())


@router.put("/{route_id}", response_model=InboundRouteOut)
async def update_inbound_route(route_id: int, payload: InboundRouteUpdate, db: AsyncSession = Depends(get_db)):
    try:
        return await crud.update_inbound_route(db, route_id, payload.model_dump(exclude_unset=True))
    except crud.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{route_id}", status_code=204)
async def delete_inbound_route(route_id: int, db: AsyncSession = Depends(get_db)):
    try:
        await crud.delete_inbound_route(db, route_id)
    except crud.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
