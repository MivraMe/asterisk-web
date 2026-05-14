import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from asterisk_ami import ami
from config import settings
from database import init_db

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    Path(settings.backup_dir).mkdir(parents=True, exist_ok=True)
    await init_db()
    logger.info("Database initialised")

    try:
        await ami.connect()
        asyncio.create_task(ami._reconnect_loop())
        logger.info("AMI connection started")
    except Exception as exc:
        logger.warning("AMI startup failed (will retry): %s", exc)

    yield

    # Shutdown
    await ami.close()
    logger.info("AMI closed")


app = FastAPI(
    title="Asterisk Manager",
    description="Web interface for Asterisk PBX + Polycom provisioning",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Polycom config directory so phones can fetch their configs
polycom_dir = Path(settings.polycom_cfg_dir)
polycom_dir.mkdir(parents=True, exist_ok=True)
app.mount("/polycom", StaticFiles(directory=str(polycom_dir)), name="polycom")

# Mount frontend static files
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Include routers
from routers.extensions import router as ext_router
from routers.polycom import router as polycom_router
from routers.calls import router as calls_router
from routers.routing import router as routing_router
from routers.features import router as features_router
from routers.cdr import router as cdr_router
from routers.monitoring import router as monitoring_router
from routers.config_router import router as config_router

app.include_router(ext_router, prefix="/api/extensions", tags=["Extensions"])
app.include_router(polycom_router, prefix="/api/polycom", tags=["Polycom"])
app.include_router(calls_router, prefix="/api/calls", tags=["Calls"])
app.include_router(routing_router, prefix="/api/routing", tags=["Routing"])
app.include_router(features_router, prefix="/api/features", tags=["Features"])
app.include_router(cdr_router, prefix="/api/cdr", tags=["CDR"])
app.include_router(monitoring_router, prefix="/api/monitoring", tags=["Monitoring"])
app.include_router(config_router, prefix="/api/config", tags=["Config"])

# WebSocket routes (already defined in routers but need to be accessible at root-ish paths)
from routers.calls import ws_calls
from routers.monitoring import ws_events


@app.get("/health", tags=["Health"])
async def health() -> dict:
    return {
        "status": "ok",
        "ami_connected": ami.is_connected,
    }


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str):
    """Serve index.html for all non-API routes (SPA)."""
    if full_path.startswith("api/") or full_path.startswith("static/") or full_path.startswith("polycom/"):
        from fastapi import HTTPException
        raise HTTPException(status_code=404)
    index = Path(__file__).parent / "static" / "index.html"
    return FileResponse(str(index))
