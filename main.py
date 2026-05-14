import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
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

    # Import any .cfg files that exist on disk but are not yet in the DB
    try:
        from services.polycom_service import import_orphan_devices
        await import_orphan_devices()
    except Exception as exc:
        logger.warning("Polycom orphan import failed: %s", exc)

    # Ensure Polycom bootstrap (000000000000.cfg) and site.cfg exist
    try:
        from polycom_provisioning import render_site_config, write_master_config, write_site_config
        write_master_config()
        site_cfg = Path(settings.polycom_cfg_dir) / "site.cfg"
        if not site_cfg.exists():
            xml_str = render_site_config(provisioning_ip=settings.asterisk_ip)
            write_site_config(xml_str)
            logger.info("Generated default site.cfg")
    except Exception as exc:
        logger.warning("Polycom bootstrap init failed: %s", exc)

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

# Accept Polycom phone log uploads (PUT/POST) — phones try to push boot/app
# logs to the provisioning server; silently accept so they don't show "provision fail".
@app.api_route("/polycom/{path:path}", methods=["PUT", "POST", "DELETE"], include_in_schema=False)
async def polycom_phone_upload(path: str, request: Request) -> Response:
    body = await request.body()
    if body and path.endswith((".log", ".cfg")):
        log_path = Path(settings.polycom_cfg_dir) / path
        try:
            log_path.write_bytes(body)
        except Exception:
            pass
    return Response(status_code=200)

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

# Register WebSocket routes at the paths the JS client expects.
# The same handlers are also reachable at /api/monitoring/ws/events and
# /api/calls/ws/calls via the included routers (both work).
from routers.calls import ws_calls
from routers.monitoring import ws_events

app.add_api_websocket_route("/ws/events", ws_events)
app.add_api_websocket_route("/ws/calls", ws_calls)


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
