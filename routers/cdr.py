from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from services.cdr_service import export_csv, get_call, get_calls

router = APIRouter()


@router.get("/", summary="List CDR records with optional filters")
async def list_cdr(
    from_ext: str | None = Query(default=None),
    to_ext: str | None = Query(default=None),
    status: str | None = Query(default=None),
    from_dt: datetime | None = Query(default=None, alias="from"),
    to_dt: datetime | None = Query(default=None, alias="to"),
    limit: int = Query(default=200, le=1000),
) -> list[dict]:
    return await get_calls(from_ext=from_ext, to_ext=to_ext, status=status,
                           from_dt=from_dt, to_dt=to_dt, limit=limit)


@router.get("/export", summary="Export CDR as CSV")
async def export_cdr(
    from_ext: str | None = Query(default=None),
    to_ext: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> StreamingResponse:
    csv_data = await export_csv(from_ext=from_ext, to_ext=to_ext, status=status)

    def gen():
        yield csv_data

    return StreamingResponse(
        gen(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=cdr_export.csv"},
    )


@router.get("/{call_id}", summary="Get a single CDR record")
async def get_cdr(call_id: int) -> dict:
    record = await get_call(call_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Call {call_id} not found")
    return record
