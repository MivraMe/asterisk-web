from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from asterisk_ami import ami
from services.asterisk_service import (
    DialplanContext,
    ExtensionLine,
    parse_extensions_conf,
    write_extensions_conf,
)
from config import settings

router = APIRouter()


class ContextCreate(BaseModel):
    name: str


class ExtensionLineCreate(BaseModel):
    pattern: str
    priority: str
    app: str


@router.get("/contexts", summary="List all dialplan contexts")
async def list_contexts() -> list[dict]:
    contexts = parse_extensions_conf(settings.extensions_conf)
    return [
        {
            "name": c.name,
            "extension_count": len(c.lines),
            "includes": c.includes,
        }
        for c in contexts
    ]


@router.get("/contexts/{name}", summary="Get context details")
async def get_context(name: str) -> dict:
    contexts = parse_extensions_conf(settings.extensions_conf)
    ctx = next((c for c in contexts if c.name == name), None)
    if ctx is None:
        raise HTTPException(status_code=404, detail=f"Context {name!r} not found")
    return {
        "name": ctx.name,
        "includes": ctx.includes,
        "lines": [{"pattern": l.pattern, "priority": l.priority, "app": l.app} for l in ctx.lines],
    }


@router.post("/contexts", status_code=201, summary="Create a new dialplan context")
async def create_context(body: ContextCreate) -> dict:
    contexts = parse_extensions_conf(settings.extensions_conf)
    if any(c.name == body.name for c in contexts):
        raise HTTPException(status_code=409, detail=f"Context {body.name!r} already exists")
    contexts.append(DialplanContext(name=body.name))
    write_extensions_conf(settings.extensions_conf, contexts)
    return {"name": body.name, "status": "created"}


@router.put("/contexts/{name}", summary="Replace all extension lines in a context")
async def update_context(name: str, lines: list[ExtensionLineCreate]) -> dict:
    contexts = parse_extensions_conf(settings.extensions_conf)
    ctx = next((c for c in contexts if c.name == name), None)
    if ctx is None:
        raise HTTPException(status_code=404, detail=f"Context {name!r} not found")
    ctx.lines = [ExtensionLine(pattern=l.pattern, priority=l.priority, app=l.app) for l in lines]
    ctx._raw_lines = []  # mark dirty so it's regenerated on write
    write_extensions_conf(settings.extensions_conf, contexts)
    try:
        await ami.send_action({"Action": "Command", "Command": "module reload pbx_config.so"})
    except Exception:
        pass
    return {"name": name, "status": "updated"}


@router.delete("/contexts/{name}", summary="Delete a dialplan context")
async def delete_context(name: str) -> dict:
    contexts = parse_extensions_conf(settings.extensions_conf)
    before = len(contexts)
    contexts = [c for c in contexts if c.name != name]
    if len(contexts) == before:
        raise HTTPException(status_code=404, detail=f"Context {name!r} not found")
    write_extensions_conf(settings.extensions_conf, contexts)
    return {"name": name, "status": "deleted"}
