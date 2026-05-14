import asyncio
import logging

logger = logging.getLogger(__name__)

# Explicit allowlist — prevents arbitrary command execution
ALLOWED_COMMANDS: set[str] = {
    "pjsip show endpoints",
    "pjsip show contacts",
    "pjsip reload",
    "dialplan show",
    "core show channels concise",
    "core show uptime",
    "core reload",
    "module reload chan_pjsip.so",
    "module reload res_pjsip.so",
    "module reload pbx_config.so",
}


async def run_asterisk_command(cmd: str) -> tuple[int, str, str]:
    """
    Execute: sudo asterisk -rx "<cmd>"
    Uses exec (not shell) to prevent injection.
    Returns (returncode, stdout, stderr).
    """
    if cmd not in ALLOWED_COMMANDS:
        raise ValueError(f"Command not in allowlist: {cmd!r}")

    proc = await asyncio.create_subprocess_exec(
        "sudo", "asterisk", "-rx", cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    rc = proc.returncode or 0
    logger.debug("CLI[%d] %s", rc, cmd)
    return rc, stdout.decode(errors="replace"), stderr.decode(errors="replace")


async def pjsip_show_endpoints() -> list[dict]:
    """Parse `pjsip show endpoints` into a list of dicts."""
    rc, out, _ = await run_asterisk_command("pjsip show endpoints")
    if rc != 0:
        return []
    endpoints = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("Endpoint") or line.startswith("=") or line.startswith("-"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            endpoints.append({"endpoint": parts[0].split("/")[-1], "state": parts[1]})
    return endpoints


async def core_show_uptime() -> dict:
    """Parse `core show uptime` into a dict."""
    rc, out, _ = await run_asterisk_command("core show uptime")
    if rc != 0:
        return {}
    result: dict[str, str] = {}
    for line in out.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            result[key.strip()] = val.strip()
    return result


async def core_show_channels() -> list[dict]:
    """Parse `core show channels concise` into a list of channel dicts."""
    rc, out, _ = await run_asterisk_command("core show channels concise")
    if rc != 0:
        return []
    channels = []
    for line in out.splitlines():
        parts = line.split("!")
        if len(parts) >= 7:
            channels.append({
                "channel": parts[0],
                "context": parts[1],
                "extension": parts[2],
                "priority": parts[3],
                "state": parts[4],
                "app": parts[5],
                "data": parts[6] if len(parts) > 6 else "",
            })
    return channels
