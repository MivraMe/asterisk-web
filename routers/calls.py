import asyncio

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from asterisk_ami import ami
from asterisk_cli import core_show_channels, parse_channels_concise_output

router = APIRouter()


async def _get_active_channels() -> list[dict]:
    """Use AMI Command (preferred, works remotely) then fall back to local CLI."""
    try:
        lines = await ami.send_command("core show channels concise")
        return parse_channels_concise_output(lines)
    except Exception:
        pass
    return await core_show_channels()


@router.get("/", summary="List active channels")
async def list_calls() -> list[dict]:
    try:
        return await _get_active_channels()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/{channel:path}/hangup", summary="Hang up a channel")
async def hangup_call(channel: str) -> dict:
    try:
        resp = await ami.hangup(channel)
        return {"channel": channel, "status": "hangup_sent", "ami": resp}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.websocket("/ws/calls")
async def ws_calls(websocket: WebSocket) -> None:
    await websocket.accept()
    queue = await ami.subscribe()
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                # Only forward call-related events
                if event.get("Event") in {
                    "Newchannel", "Hangup", "DialBegin", "DialEnd",
                    "BridgeEnter", "BridgeLeave", "Hold", "Unhold",
                }:
                    await websocket.send_json(event)
            except asyncio.TimeoutError:
                await websocket.send_json({"Event": "Ping"})
    except WebSocketDisconnect:
        pass
    finally:
        await ami.unsubscribe(queue)
