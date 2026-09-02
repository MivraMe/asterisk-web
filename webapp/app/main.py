import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.ami_client import ami
from app.bootstrap import ensure_admin_user
from app.config import settings
from app.database import async_session
from app.middleware import AuthMiddleware

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with async_session() as db:
        await ensure_admin_user(db)

    try:
        await ami.connect()
    except Exception:
        logger.warning("AMI startup failed (will retry in the background)")
    asyncio.create_task(ami.reconnect_loop())
    logger.info("AMI connection task started")

    yield

    await ami.close()
    logger.info("AMI closed")


app = FastAPI(title="Asterisk Manager (petite-etoile)", version="2.0.0", lifespan=lifespan)
app.add_middleware(AuthMiddleware)

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

from app.routers import (  # noqa: E402
    auth,
    cdr,
    extensions,
    inbound_routes,
    ivr,
    outbound_routes,
    pages,
    ring_groups,
    status,
    trunks,
    voicemail,
)

app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(extensions.router, prefix="/api/extensions", tags=["Extensions"])
app.include_router(trunks.router, prefix="/api/trunks", tags=["Trunks"])
app.include_router(ring_groups.router, prefix="/api/ring-groups", tags=["Ring groups"])
app.include_router(ivr.router, prefix="/api/ivr", tags=["IVR"])
app.include_router(inbound_routes.router, prefix="/api/inbound-routes", tags=["Inbound routes"])
app.include_router(outbound_routes.router, prefix="/api/outbound-routes", tags=["Outbound routes"])
app.include_router(voicemail.router, prefix="/api/voicemail", tags=["Voicemail"])
app.include_router(cdr.router, prefix="/api/cdr", tags=["CDR"])
app.include_router(status.router, prefix="/api", tags=["Status"])
app.include_router(pages.router, tags=["Pages"])


@app.get("/health", tags=["Health"])
async def health() -> dict:
    return {"status": "ok", "ami_connected": ami.is_connected}
