import csv
import io
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import CDR
from app.schemas import CDROut, CDRPage

router = APIRouter()

CSV_COLUMNS = [
    "calldate", "clid", "src", "dst", "dcontext", "channel", "dstchannel",
    "lastapp", "duration", "billsec", "disposition", "accountcode", "uniqueid",
]


def _apply_filters(stmt, date_from: datetime | None, date_to: datetime | None,
                    extension: str | None, direction: str | None):
    if date_from is not None:
        stmt = stmt.where(CDR.calldate >= date_from)
    if date_to is not None:
        stmt = stmt.where(CDR.calldate <= date_to)
    if extension:
        stmt = stmt.where((CDR.src == extension) | (CDR.dst == extension))
    if direction == "inbound":
        stmt = stmt.where(CDR.dcontext.like("from-trunk-%"))
    elif direction == "outbound":
        stmt = stmt.where(CDR.dcontext == "internal", func.length(CDR.dst) > 6)
    elif direction == "internal":
        stmt = stmt.where(CDR.dcontext == "internal", func.length(CDR.dst) <= 6)
    return stmt


@router.get("", response_model=CDRPage)
async def list_cdr(
    date_from: datetime | None = Query(None, alias="from"),
    date_to: datetime | None = Query(None, alias="to"),
    extension: str | None = None,
    direction: str | None = Query(None, pattern="^(inbound|outbound|internal)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    base = _apply_filters(select(CDR), date_from, date_to, extension, direction)

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        await db.execute(
            base.order_by(CDR.calldate.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    ).scalars().all()

    return CDRPage(total=total, page=page, page_size=page_size, items=rows)


@router.get("/export.csv")
async def export_cdr_csv(
    date_from: datetime | None = Query(None, alias="from"),
    date_to: datetime | None = Query(None, alias="to"),
    extension: str | None = None,
    direction: str | None = Query(None, pattern="^(inbound|outbound|internal)$"),
    db: AsyncSession = Depends(get_db),
):
    stmt = _apply_filters(select(CDR), date_from, date_to, extension, direction).order_by(CDR.calldate.desc())
    rows = (await db.execute(stmt)).scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_COLUMNS)
    for row in rows:
        writer.writerow([getattr(row, col) for col in CSV_COLUMNS])
    buf.seek(0)

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=cdr_export.csv"},
    )


@router.get("/{cdr_id}/recording")
async def get_recording(cdr_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(CDR, cdr_id)
    if row is None or not row.recordingfile:
        raise HTTPException(status_code=404, detail="No recording for this call")

    path = Path(settings.asterisk_spool_dir) / "monitor" / row.recordingfile
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Recording file missing on disk")

    return FileResponse(str(path), media_type="audio/wav", filename=path.name)
