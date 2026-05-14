import asyncio
import logging
import os
import re

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

    # Don't use sudo when already root (e.g. inside Docker)
    cmd_parts = ["asterisk", "-rx", cmd] if os.geteuid() == 0 else ["sudo", "asterisk", "-rx", cmd]
    proc = await asyncio.create_subprocess_exec(
        *cmd_parts,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    rc = proc.returncode or 0
    logger.debug("CLI[%d] %s", rc, cmd)
    return rc, stdout.decode(errors="replace"), stderr.decode(errors="replace")


# Asterisk PJSIP state strings → normalized display values
_PJSIP_STATE_MAP = {
    "Not in use": "Available",
    "In use":     "In Use",
    "Unavailable": "Unavailable",
    "Ringing":    "Ringing",
    "Ring+Inuse": "In Use",
    "OnHold":     "On Hold",
    "OnHold+Inuse": "On Hold",
    "Invalid":    "Unavailable",
}


def parse_pjsip_endpoints_output(lines: list[str]) -> list[dict]:
    """
    Parse lines from 'pjsip show endpoints'.
    Data lines look like:
      Endpoint:  6693/6693                       Not in use    0 of inf
    The state is multi-word so we cannot split on whitespace naively.
    """
    # Flatten: some AMI responses embed newlines inside a single Output value
    flat: list[str] = []
    for l in lines:
        flat.extend(l.splitlines())

    endpoints = []
    for line in flat:
        stripped = line.strip()
        if not stripped.startswith("Endpoint:"):
            continue
        rest = stripped[len("Endpoint:"):].strip()
        # Skip the column-header line (contains angle brackets) or empty rest
        if not rest or "<" in rest:
            continue
        # Strip trailing channel count: "N of inf" or "N of N"
        rest = re.sub(r"\s+\d+\s+of\s+\S+\s*$", "", rest).strip()
        # Split on 2+ consecutive spaces: "6693/6693     Not in use"
        parts = re.split(r"\s{2,}", rest, maxsplit=1)
        ep_name = parts[0].strip().split("/")[0]  # "6693/6693" → "6693"
        raw_state = parts[1].strip() if len(parts) > 1 else "Unknown"
        # Case-insensitive lookup with original case fallback
        state = _PJSIP_STATE_MAP.get(raw_state) or _PJSIP_STATE_MAP.get(raw_state.lower()) or raw_state
        if ep_name:
            endpoints.append({"endpoint": ep_name, "state": state})

    if flat and not endpoints:
        logger.warning("parse_pjsip_endpoints_output: %d lines, 0 parsed. First line: %r",
                       len(flat), flat[0] if flat else "")
    return endpoints


async def pjsip_show_endpoints() -> list[dict]:
    """Parse `pjsip show endpoints` into a list of dicts."""
    rc, out, _ = await run_asterisk_command("pjsip show endpoints")
    if rc != 0:
        return []
    return parse_pjsip_endpoints_output(out.splitlines())


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


def parse_channels_concise_output(lines: list[str]) -> list[dict]:
    """
    Parse lines from 'core show channels concise'.
    Format: Channel!Context!Extension!Priority!State!Application!Data!CallerID!...
    """
    channels = []
    for line in lines:
        parts = line.split("!")
        if len(parts) < 6:
            continue
        channel = parts[0].strip()
        if not channel or "/" not in channel:
            continue  # skip summary lines like "1 active call(s)"
        channels.append({
            "channel": channel,
            "context": parts[1],
            "extension": parts[2],
            "priority": parts[3],
            "state": parts[4],
            "app": parts[5],
            "data": parts[6] if len(parts) > 6 else "",
            "callerid": parts[7] if len(parts) > 7 else "",
            "duration": parts[8] if len(parts) > 8 else "",
        })
    return channels


async def core_show_channels() -> list[dict]:
    """Parse `core show channels concise` into a list of channel dicts."""
    rc, out, _ = await run_asterisk_command("core show channels concise")
    if rc != 0:
        return []
    return parse_channels_concise_output(out.splitlines())
