import re
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, field_validator

from asterisk_ami import ami
from asterisk_cli import pjsip_show_endpoints
from database import AsyncSessionLocal
from models import Extension, Log
from services.asterisk_service import (
    create_extension,
    delete_extension,
    get_extension,
    list_extensions,
    update_extension,
)

router = APIRouter()


class ExtensionCreate(BaseModel):
    number: str
    name: str = ""
    password: str
    context: str = "from-internal"

    @field_validator("number")
    @classmethod
    def validate_number(cls, v: str) -> str:
        if not re.fullmatch(r"\d{3,6}", v):
            raise ValueError("Extension must be 3–6 digits")
        return v


class ExtensionUpdate(BaseModel):
    name: str | None = None
    password: str | None = None
    context: str | None = None
    transport: str | None = None


async def _audit(msg: str, module: str = "extensions") -> None:
    async with AsyncSessionLocal() as db:
        db.add(Log(level="INFO", message=msg, module=module))
        await db.commit()


@router.get("/", summary="List all PJSIP endpoints")
async def list_eps() -> list[dict]:
    file_exts = list_extensions()
    try:
        live = await pjsip_show_endpoints()
        live_map = {e["endpoint"]: e["state"] for e in live}
    except Exception:
        live_map = {}

    for ext in file_exts:
        ext["state"] = live_map.get(ext["number"], "Unknown")
    return file_exts


@router.get("/{number}", summary="Get a single PJSIP endpoint")
async def get_ep(number: str) -> dict:
    ext = get_extension(number)
    if ext is None:
        raise HTTPException(status_code=404, detail=f"Extension {number} not found")
    try:
        live = await pjsip_show_endpoints()
        live_map = {e["endpoint"]: e["state"] for e in live}
        ext["state"] = live_map.get(number, "Unknown")
    except Exception:
        ext["state"] = "Unknown"
    return ext


@router.post("/", status_code=status.HTTP_201_CREATED, summary="Create a PJSIP endpoint")
async def create_ep(body: ExtensionCreate) -> dict:
    try:
        create_extension(body.number, body.name, body.password, body.context)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    try:
        await ami.pjsip_reload()
    except Exception:
        pass
    await _audit(f"Created extension {body.number}")
    return {"number": body.number, "status": "created"}


@router.put("/{number}", summary="Update a PJSIP endpoint")
async def update_ep(number: str, body: ExtensionUpdate) -> dict:
    kwargs: dict[str, Any] = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        update_extension(number, **kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    try:
        await ami.pjsip_reload()
    except Exception:
        pass
    await _audit(f"Updated extension {number}: {list(kwargs.keys())}")
    return {"number": number, "status": "updated"}


@router.delete("/{number}", summary="Delete a PJSIP endpoint")
async def delete_ep(number: str) -> dict:
    try:
        delete_extension(number)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    try:
        await ami.pjsip_reload()
    except Exception:
        pass
    await _audit(f"Deleted extension {number}")
    return {"number": number, "status": "deleted"}


@router.post("/{number}/test", summary="Originate a test call from an extension")
async def test_ep(number: str, to: str = "echo") -> dict:
    ext = get_extension(number)
    if ext is None:
        raise HTTPException(status_code=404, detail=f"Extension {number} not found")
    try:
        resp = await ami.originate(number, to, ext["context"])
        return {"status": "originated", "ami_response": resp}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/{number}/contacts", summary="Show active contacts for an endpoint")
async def get_contacts(number: str) -> dict:
    try:
        resp = await ami.send_action({"Action": "Command", "Command": f"pjsip show contacts {number}"})
        return {"output": resp.get("Output", [])}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))
