"""Asterisk Manager Interface (AMI) — minimal async client.

Handles two shapes of AMI interaction:
  - Simple request/response actions (Login, Command, Originate, Hangup...)
    where a single "Response:" block answers the action.
  - "List" actions (PJSIPShowEndpoints, CoreShowChannels...) where the
    Response block just acknowledges the request and the actual data
    arrives as a series of "Event:" blocks sharing the same ActionID,
    terminated by an event whose name ends in "Complete".

Protocol summary: blocks are lines of "Key: Value\\r\\n" terminated by a
blank line; the first line after connect is a banner.
"""
import asyncio
import logging
import uuid
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


class AMIError(Exception):
    pass


class AsteriskAMI:
    def __init__(self) -> None:
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._pending: dict[str, asyncio.Future[dict]] = {}
        self._list_collectors: dict[str, tuple[list[dict], asyncio.Future[list[dict]]]] = {}
        self._connected = asyncio.Event()
        self._lock = asyncio.Lock()
        self._running = False

    # ------------------------------------------------------------------ #
    # Connection management                                                #
    # ------------------------------------------------------------------ #

    async def connect(self) -> None:
        self._running = True
        await self._try_connect()

    async def _try_connect(self) -> bool:
        try:
            self._reader, self._writer = await asyncio.open_connection(settings.ami_host, settings.ami_port)
            banner = await self._reader.readline()
            logger.info("AMI banner: %s", banner.decode(errors="replace").strip())

            await self._send_raw(
                f"Action: Login\r\nUsername: {settings.ami_user}\r\n"
                f"Secret: {settings.ami_secret}\r\nActionID: login\r\n\r\n"
            )
            resp = await self._read_block()
            if resp.get("Response") != "Success":
                logger.error("AMI login failed: %s", resp)
                return False

            self._connected.set()
            logger.info("AMI connected to %s:%d", settings.ami_host, settings.ami_port)
            asyncio.create_task(self._read_loop())
            return True
        except Exception as exc:
            logger.warning("AMI connect error: %s", exc)
            return False

    async def reconnect_loop(self) -> None:
        delay = 1
        while self._running:
            await self._connected.wait()
            while self._connected.is_set():
                await asyncio.sleep(1)
            if not self._running:
                break
            logger.info("AMI reconnecting in %ds...", delay)
            await asyncio.sleep(delay)
            if await self._try_connect():
                delay = 1
            else:
                delay = min(delay * 2, 30)

    async def close(self) -> None:
        self._running = False
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        self._connected.clear()

    # ------------------------------------------------------------------ #
    # I/O                                                                  #
    # ------------------------------------------------------------------ #

    async def _send_raw(self, text: str) -> None:
        if self._writer is None:
            raise AMIError("AMI not connected")
        self._writer.write(text.encode())
        await self._writer.drain()

    async def _read_block(self) -> dict[str, Any]:
        lines: list[str] = []
        assert self._reader is not None
        while True:
            raw = await self._reader.readline()
            if not raw:
                raise ConnectionResetError("AMI EOF")
            line = raw.decode(errors="replace").rstrip("\r\n")
            if line == "":
                if lines:
                    return self._parse_block(lines)
            else:
                lines.append(line)

    @staticmethod
    def _parse_block(lines: list[str]) -> dict[str, Any]:
        block: dict[str, Any] = {}
        output: list[str] = []
        for line in lines:
            if line == "--END COMMAND--":
                output.append(line)
            elif ": " in line:
                key, _, val = line.partition(": ")
                if key == "Output":
                    output.append(val)
                else:
                    block[key] = val
        if output:
            block["Output"] = output
        return block

    async def _read_loop(self) -> None:
        try:
            while self._connected.is_set():
                block = await self._read_block()
                action_id = block.get("ActionID", "")

                if "Event" in block:
                    self._dispatch_event(action_id, block)

                if "Response" in block and action_id in self._pending:
                    fut = self._pending.pop(action_id)
                    if not fut.done():
                        fut.set_result(block)

                if "Response" in block and action_id in self._list_collectors:
                    # Some list actions (e.g. PJSIPShowEndpoints with nothing
                    # configured) answer with a bare "Response: Error" and no
                    # events at all — there's no terminating "...Complete"
                    # event to wait for, so treat that as an empty result
                    # instead of hanging until the call times out. A
                    # "Response: Success" here just acknowledges the request;
                    # the actual data still arrives as Event blocks.
                    if block.get("Response") == "Error":
                        events, fut = self._list_collectors.pop(action_id)
                        if not fut.done():
                            fut.set_result([])
        except (ConnectionResetError, asyncio.IncompleteReadError, OSError) as exc:
            logger.warning("AMI read loop ended: %s", exc)
        finally:
            self._connected.clear()
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(AMIError("AMI disconnected"))
            self._pending.clear()
            for events, fut in self._list_collectors.values():
                if not fut.done():
                    fut.set_exception(AMIError("AMI disconnected"))
            self._list_collectors.clear()

    def _dispatch_event(self, action_id: str, event: dict) -> None:
        collector = self._list_collectors.get(action_id)
        if collector is None:
            return
        events, fut = collector
        event_name = event.get("Event", "")
        if event_name.endswith("Complete"):
            self._list_collectors.pop(action_id, None)
            if not fut.done():
                fut.set_result(events)
        else:
            events.append(event)

    # ------------------------------------------------------------------ #
    # Core send primitives                                                 #
    # ------------------------------------------------------------------ #

    async def send_action(self, action: dict[str, str], timeout: float = 10.0) -> dict:
        if not self._connected.is_set():
            raise AMIError("AMI not connected")
        action_id = str(uuid.uuid4())
        action = {**action, "ActionID": action_id}

        loop = asyncio.get_event_loop()
        fut: asyncio.Future[dict] = loop.create_future()
        self._pending[action_id] = fut

        lines = "".join(f"{k}: {v}\r\n" for k, v in action.items()) + "\r\n"
        async with self._lock:
            await self._send_raw(lines)

        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(action_id, None)
            raise TimeoutError(f"AMI action timed out: {action.get('Action')}") from None

    async def send_list_action(self, action: dict[str, str], timeout: float = 10.0) -> list[dict]:
        """For actions whose data arrives as a series of Event blocks
        (PJSIPShowEndpoints, CoreShowChannels, ...)."""
        if not self._connected.is_set():
            raise AMIError("AMI not connected")
        action_id = str(uuid.uuid4())
        action = {**action, "ActionID": action_id}

        loop = asyncio.get_event_loop()
        fut: asyncio.Future[list[dict]] = loop.create_future()
        self._list_collectors[action_id] = ([], fut)

        lines = "".join(f"{k}: {v}\r\n" for k, v in action.items()) + "\r\n"
        async with self._lock:
            await self._send_raw(lines)

        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._list_collectors.pop(action_id, None)
            raise TimeoutError(f"AMI list action timed out: {action.get('Action')}") from None

    # ------------------------------------------------------------------ #
    # High-level helpers                                                   #
    # ------------------------------------------------------------------ #

    async def get_endpoints(self) -> list[dict]:
        """PJSIPShowEndpoints -> one EndpointList event per configured endpoint."""
        return await self.send_list_action({"Action": "PJSIPShowEndpoints"})

    async def get_channels(self) -> list[dict]:
        """CoreShowChannels -> one CoreShowChannel event per active channel."""
        return await self.send_list_action({"Action": "CoreShowChannels"})

    async def hangup(self, channel: str) -> dict:
        return await self.send_action({"Action": "Hangup", "Channel": channel})

    async def originate(self, from_ext: str, to_ext: str, context: str = "internal") -> dict:
        return await self.send_action({
            "Action": "Originate",
            "Channel": f"PJSIP/{from_ext}",
            "Exten": to_ext,
            "Context": context,
            "Priority": "1",
            "Async": "true",
        })

    async def _reload(self, command: str) -> dict:
        return await self.send_action({"Action": "Command", "Command": command})

    async def pjsip_reload(self) -> dict:
        # There is no bare "pjsip reload" CLI command — res_pjsip's config
        # is reloaded through the generic module-reload mechanism.
        return await self._reload("module reload res_pjsip.so")

    async def dialplan_reload(self) -> dict:
        return await self._reload("dialplan reload")

    async def voicemail_reload(self) -> dict:
        return await self._reload("voicemail reload")

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set()


ami = AsteriskAMI()
