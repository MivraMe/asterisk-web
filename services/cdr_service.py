"""CDR service — queries the local calls table and optionally Asterisk's native CDR SQLite."""
import csv
import io
import logging
from datetime import datetime

from sqlalchemy import and_, select

from config import settings
from database import AsyncSessionLocal
from models import Call

logger = logging.getLogger(__name__)


async def get_calls(
    from_ext: str | None = None,
    to_ext: str | None = None,
    status: str | None = None,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
    limit: int = 200,
) -> list[dict]:
    async with AsyncSessionLocal() as db:
        stmt = select(Call).order_by(Call.start_time.desc()).limit(limit)
        filters = []
        if from_ext:
            filters.append(Call.from_ext == from_ext)
        if to_ext:
            filters.append(Call.to_ext == to_ext)
        if status:
            filters.append(Call.status == status)
        if from_dt:
            filters.append(Call.start_time >= from_dt)
        if to_dt:
            filters.append(Call.start_time <= to_dt)
        if filters:
            stmt = stmt.where(and_(*filters))
        rows = (await db.execute(stmt)).scalars().all()
    return [_call_to_dict(r) for r in rows]


async def get_call(call_id: int) -> dict | None:
    async with AsyncSessionLocal() as db:
        row = (await db.execute(select(Call).where(Call.id == call_id))).scalar_one_or_none()
    return _call_to_dict(row) if row else None


async def record_call_start(callid: str, from_ext: str, to_ext: str) -> None:
    async with AsyncSessionLocal() as db:
        db.add(Call(callid=callid, from_ext=from_ext, to_ext=to_ext,
                    start_time=datetime.utcnow(), status="active"))
        await db.commit()


async def record_call_end(callid: str, status: str = "completed") -> None:
    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(Call).where(Call.callid == callid, Call.status == "active")
        )).scalar_one_or_none()
        if row:
            row.end_time = datetime.utcnow()
            row.status = status
            if row.start_time:
                row.duration = int((row.end_time - row.start_time).total_seconds())
            await db.commit()


async def export_csv(
    from_ext: str | None = None,
    to_ext: str | None = None,
    status: str | None = None,
) -> str:
    calls = await get_calls(from_ext=from_ext, to_ext=to_ext, status=status, limit=10000)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["id", "callid", "from_ext", "to_ext",
                                              "start_time", "end_time", "duration", "status", "codec"])
    writer.writeheader()
    writer.writerows(calls)
    return buf.getvalue()


def _call_to_dict(c: Call) -> dict:
    return {
        "id": c.id,
        "callid": c.callid,
        "from_ext": c.from_ext,
        "to_ext": c.to_ext,
        "start_time": c.start_time.isoformat() if c.start_time else None,
        "end_time": c.end_time.isoformat() if c.end_time else None,
        "duration": c.duration,
        "status": c.status,
        "codec": c.codec,
    }
