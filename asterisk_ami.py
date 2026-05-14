"""
Asterisk AMI client — persistent async TCP singleton.

Protocol summary:
  - Blocks are lines of "Key: Value\r\n" terminated by a blank line.
  - First line after connect is a banner: "Asterisk Call Manager/x.y\r\n"
  - Actions must include a unique ActionID to correlate responses.
  - Responses have Response: key; events have Event: key.
  - Command action returns multiple Output: lines, ending with "--END COMMAND--".
"""
import asyncio
import logging
import uuid
from typing import Any

from config import settings

logger = logging.getLogger(__name__)


class AsteriskAMI:
    def __init__(self) -> None:
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._pending: dict[str, asyncio.Future[dict]] = {}
        self._event_subscribers: list[asyncio.Queue] = []
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
            self._reader, self._writer = await asyncio.open_connection(
                settings.ami_host, settings.ami_port
            )
            # consume banner line
            banner = await self._reader.readline()
            logger.info("AMI banner: %s", banner.decode().strip())

            # login
            await self._send_raw(
                f"Action: Login\r\nUsername: {settings.ami_username}\r\n"
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

    async def _reconnect_loop(self) -> None:
        delay = 1
        while self._running:
            await self._connected.wait()
            # wait until disconnected
            while self._connected.is_set():
                await asyncio.sleep(1)
            if not self._running:
                break
            logger.info("AMI reconnecting in %ds…", delay)
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
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()

    # ------------------------------------------------------------------ #
    # I/O                                                                  #
    # ------------------------------------------------------------------ #

    async def _send_raw(self, text: str) -> None:
        if self._writer is None:
            raise ConnectionError("AMI not connected")
        self._writer.write(text.encode())
        await self._writer.drain()

    async def _read_block(self) -> dict[str, Any]:
        """Read one AMI block (lines until blank line). Returns parsed dict."""
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

    def _parse_block(self, lines: list[str]) -> dict[str, Any]:
        block: dict[str, Any] = {}
        for line in lines:
            if ": " in line:
                key, _, val = line.partition(": ")
                if key == "Output":
                    block.setdefault("Output", []).append(val)
                else:
                    block[key] = val
            elif line.startswith("Output:"):
                block.setdefault("Output", []).append(line[7:].lstrip())
        return block

    async def _read_loop(self) -> None:
        """Continuously read blocks and dispatch responses/events."""
        # Buffers for Command actions that arrive as multiple AMI blocks.
        # Asterisk 18+ sends: Block1={Response+Message} then Block2={Output lines}
        command_bufs: dict[str, list[str]] = {}   # accumulated Output lines per ActionID
        command_resps: dict[str, dict] = {}        # saved Response block per ActionID
        try:
            while self._connected.is_set():
                block = await self._read_block()
                action_id = block.get("ActionID", "")

                if "Event" in block:
                    await self._dispatch_event(block)

                # Temporary: log every non-event block so we can see AMI format
                if "Response" in block or "Output" in block:
                    logger.info("AMI block keys=%s action_id=%r pending=%s cmd_resps=%s",
                                list(block.keys()), action_id,
                                list(self._pending.keys())[:3],
                                list(command_resps.keys())[:3])

                if "Response" in block and action_id in self._pending:
                    # Merge any Output lines buffered before this Response arrived
                    out = command_bufs.pop(action_id, []) + block.get("Output", [])

                    if (block.get("Message") == "Command output follows"
                            and "--END COMMAND--" not in out):
                        # Command response received but output not yet complete — wait
                        command_resps[action_id] = block
                        command_bufs[action_id] = out
                    else:
                        # Non-command response OR all output already present
                        block["Output"] = out
                        command_resps.pop(action_id, None)
                        fut = self._pending.pop(action_id)
                        if not fut.done():
                            fut.set_result(block)

                elif "Output" in block:
                    # Additional output block for a Command action (split response).
                    # Asterisk 21 AMI omits ActionID from output-only blocks, so if
                    # action_id is absent but there is exactly one waiting command,
                    # attribute the output to it (commands are always serial).
                    target_id = action_id
                    if not target_id and len(command_resps) == 1:
                        target_id = next(iter(command_resps))
                        logger.debug("AMI Output block has no ActionID; attributing to %s", target_id)
                    if target_id:
                        command_bufs.setdefault(target_id, []).extend(block["Output"])
                        if ("--END COMMAND--" in command_bufs[target_id]
                                and target_id in command_resps
                                and target_id in self._pending):
                            resp = command_resps.pop(target_id)
                            resp["Output"] = command_bufs.pop(target_id)
                            fut = self._pending.pop(target_id)
                            if not fut.done():
                                fut.set_result(resp)

        except (ConnectionResetError, asyncio.IncompleteReadError, OSError) as exc:
            logger.warning("AMI read loop ended: %s", exc)
        finally:
            self._connected.clear()
            # fail all pending
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(ConnectionError("AMI disconnected"))
            self._pending.clear()

    async def _dispatch_event(self, event: dict) -> None:
        dead: list[asyncio.Queue] = []
        for q in self._event_subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            try:
                self._event_subscribers.remove(q)
            except ValueError:
                pass

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    async def send_action(self, action: dict[str, str], timeout: float = 10.0) -> dict:
        """Send an AMI action dict; returns the response dict."""
        if not self._connected.is_set():
            raise ConnectionError("AMI not connected")
        action_id = str(uuid.uuid4())
        action["ActionID"] = action_id

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
            raise TimeoutError(f"AMI action timed out: {action.get('Action')}")

    async def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._event_subscribers.append(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self._event_subscribers.remove(q)
        except ValueError:
            pass

    # ------------------------------------------------------------------ #
    # High-level helpers                                                   #
    # ------------------------------------------------------------------ #

    async def get_channels(self) -> list[dict]:
        resp = await self.send_action({"Action": "CoreShowChannels"})
        return resp.get("channels", [])

    async def hangup(self, channel: str) -> dict:
        return await self.send_action({"Action": "Hangup", "Channel": channel})

    async def originate(self, from_ext: str, to_ext: str, context: str = "from-internal") -> dict:
        return await self.send_action({
            "Action": "Originate",
            "Channel": f"PJSIP/{from_ext}",
            "Exten": to_ext,
            "Context": context,
            "Priority": "1",
            "Async": "true",
        })

    async def send_command(self, cmd: str) -> list[str]:
        """Send a CLI command via AMI Command action. Returns output lines."""
        resp = await self.send_action({"Action": "Command", "Command": cmd})
        return resp.get("Output", [])

    async def pjsip_reload(self) -> dict:
        return await self.send_action({"Action": "Command", "Command": "pjsip reload"})

    async def core_reload(self) -> dict:
        return await self.send_action({"Action": "Command", "Command": "core reload"})

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set()


# Global singleton
ami = AsteriskAMI()
