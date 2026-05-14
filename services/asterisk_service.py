"""
Asterisk config-file service.

Handles pjsip.conf, extensions.conf, and features.conf:
- Custom round-trip parsers (configparser cannot handle Asterisk's INI dialect)
- Backup-before-write discipline
- Three-section model per PJSIP extension: endpoint + auth + aor
"""
import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from config import settings

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# Backup helper                                                        #
# ------------------------------------------------------------------ #

def backup_file(path: str) -> str:
    """Copy file to backup_dir with timestamp suffix. Returns backup path."""
    src = Path(path)
    if not src.exists():
        return ""
    backup_dir = Path(settings.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"{src.name}_{ts}.bak"
    shutil.copy2(src, dest)
    logger.info("Backed up %s → %s", path, dest)
    return str(dest)


# ------------------------------------------------------------------ #
# pjsip.conf parser                                                    #
# ------------------------------------------------------------------ #

@dataclass
class PjsipSection:
    name: str
    template: str | None  # template/parent name if section uses (template)
    directives: list[tuple[str, str]] = field(default_factory=list)
    _raw_lines: list[str] = field(default_factory=list, repr=False)

    def get(self, key: str) -> str | None:
        for k, v in self.directives:
            if k == key:
                return v
        return None

    def set(self, key: str, value: str) -> None:
        for i, (k, _) in enumerate(self.directives):
            if k == key:
                self.directives[i] = (key, value)
                self._raw_lines = []  # mark dirty
                return
        self.directives.append((key, value))
        self._raw_lines = []

    def remove(self, key: str) -> None:
        self.directives = [(k, v) for k, v in self.directives if k != key]
        self._raw_lines = []


@dataclass
class PjsipFile:
    sections: list[PjsipSection] = field(default_factory=list)
    _gap_lines: list[str] = field(default_factory=list, repr=False)  # lines before first section

    def find(self, name: str, type_value: str | None = None) -> PjsipSection | None:
        for s in self.sections:
            if s.name == name:
                if type_value is None or s.get("type") == type_value:
                    return s
        return None

    def find_all(self, name: str) -> list[PjsipSection]:
        return [s for s in self.sections if s.name == name]


_SECTION_RE = re.compile(r"^\[([^\]]+)\](?:\(([^)]+)\))?")


def parse_pjsip_conf(path: str) -> PjsipFile:
    """Parse an Asterisk pjsip.conf-style file into PjsipFile."""
    result = PjsipFile()
    current: PjsipSection | None = None
    pre_section: list[str] = []
    pending_raw: list[str] = []  # raw lines for current section

    try:
        text = Path(path).read_text(errors="replace")
    except FileNotFoundError:
        return result

    for line in text.splitlines(keepends=True):
        stripped = line.split(";")[0].rstrip()
        m = _SECTION_RE.match(stripped)
        if m:
            if current is not None:
                current._raw_lines = pending_raw
                result.sections.append(current)
            elif not result.sections:
                result._gap_lines = pre_section

            pending_raw = [line]
            current = PjsipSection(name=m.group(1), template=m.group(2))
            pre_section = []
        elif current is None:
            pre_section.append(line)
        else:
            pending_raw.append(line)
            if stripped and "=" in stripped:
                key, _, val = stripped.partition("=")
                # handle => (legacy) and = equally
                if val.startswith(">"):
                    val = val[1:]
                current.directives.append((key.strip(), val.strip()))

    if current is not None:
        current._raw_lines = pending_raw
        result.sections.append(current)

    return result


def render_section(sec: PjsipSection) -> str:
    """Render a section from its directives (used when _raw_lines is cleared/dirty)."""
    header = f"[{sec.name}]" + (f"({sec.template})" if sec.template else "")
    lines = [header + "\n"]
    for k, v in sec.directives:
        lines.append(f"{k}={v}\n")
    lines.append("\n")
    return "".join(lines)


def write_pjsip_conf(path: str, pjsip: PjsipFile) -> None:
    """Write PjsipFile back to disk. Backs up first, preserves original formatting for unchanged sections."""
    backup_file(path)
    parts: list[str] = []
    parts.extend(pjsip._gap_lines)
    for sec in pjsip.sections:
        if sec._raw_lines:
            parts.extend(sec._raw_lines)
        else:
            parts.append(render_section(sec))
    Path(path).write_text("".join(parts))
    logger.info("Wrote %s", path)


# ------------------------------------------------------------------ #
# Extension CRUD (three-section model)                                #
# ------------------------------------------------------------------ #

def _make_endpoint_sections(number: str, name: str, password: str, context: str) -> list[PjsipSection]:
    ep = PjsipSection(name=number, template=None, directives=[
        ("type", "endpoint"),
        ("transport", "transport-udp"),
        ("context", context),
        ("disallow", "all"),
        ("allow", "ulaw"),
        ("allow", "alaw"),
        ("auth", f"auth{number}"),
        ("aors", number),
        ("callerid", f"{name} <{number}>"),
    ])
    auth = PjsipSection(name=f"auth{number}", template=None, directives=[
        ("type", "auth"),
        ("auth_type", "userpass"),
        ("password", password),
        ("username", number),
    ])
    aor = PjsipSection(name=number, template=None, directives=[
        ("type", "aor"),
        ("max_contacts", "1"),
    ])
    return [ep, auth, aor]


def get_extension(number: str) -> dict | None:
    pjsip = parse_pjsip_conf(settings.pjsip_conf)
    ep = pjsip.find(number, "endpoint")
    if ep is None:
        return None
    auth = pjsip.find(f"auth{number}", "auth")
    raw_callerid = ep.get("callerid") or ""
    # Extract display name from "Name <number>" format; fall back to raw value
    m = re.match(r'^(.*?)\s*<[^>]+>\s*$', raw_callerid)
    clean_name = m.group(1).strip().strip('"') if m else raw_callerid
    return {
        "number": number,
        "name": clean_name,
        "context": ep.get("context") or "from-internal",
        "password": auth.get("password") if auth else None,
        "codecs": [v for k, v in ep.directives if k == "allow"],
        "transport": ep.get("transport") or "transport-udp",
    }


def list_extensions() -> list[dict]:
    pjsip = parse_pjsip_conf(settings.pjsip_conf)
    numbers = {s.name for s in pjsip.sections if s.get("type") == "endpoint"}
    return [get_extension(n) for n in sorted(numbers) if get_extension(n)]


def create_extension(number: str, name: str, password: str, context: str = "from-internal") -> None:
    pjsip = parse_pjsip_conf(settings.pjsip_conf)
    if pjsip.find(number, "endpoint"):
        raise ValueError(f"Extension {number} already exists")
    new_sections = _make_endpoint_sections(number, name, password, context)
    pjsip.sections.extend(new_sections)
    write_pjsip_conf(settings.pjsip_conf, pjsip)


def update_extension(number: str, **kwargs: Any) -> None:
    pjsip = parse_pjsip_conf(settings.pjsip_conf)
    ep = pjsip.find(number, "endpoint")
    if ep is None:
        raise ValueError(f"Extension {number} not found")
    auth = pjsip.find(f"auth{number}", "auth")

    if "name" in kwargs and ep:
        ep.set("callerid", f"{kwargs['name']} <{number}>")
    if "context" in kwargs and ep:
        ep.set("context", kwargs["context"])
    if "password" in kwargs and auth:
        auth.set("password", kwargs["password"])
    if "transport" in kwargs and ep:
        ep.set("transport", kwargs["transport"])

    write_pjsip_conf(settings.pjsip_conf, pjsip)


def delete_extension(number: str) -> None:
    pjsip = parse_pjsip_conf(settings.pjsip_conf)
    before = len(pjsip.sections)
    pjsip.sections = [
        s for s in pjsip.sections
        if not (s.name == number or s.name == f"auth{number}")
    ]
    if len(pjsip.sections) == before:
        raise ValueError(f"Extension {number} not found")
    write_pjsip_conf(settings.pjsip_conf, pjsip)


# ------------------------------------------------------------------ #
# extensions.conf parser                                              #
# ------------------------------------------------------------------ #

@dataclass
class ExtensionLine:
    pattern: str
    priority: str
    app: str  # application(args) — treated as opaque

@dataclass
class DialplanContext:
    name: str
    lines: list[ExtensionLine] = field(default_factory=list)
    includes: list[str] = field(default_factory=list)
    _raw_lines: list[str] = field(default_factory=list, repr=False)


def parse_extensions_conf(path: str) -> list[DialplanContext]:
    contexts: list[DialplanContext] = []
    current: DialplanContext | None = None
    pending_raw: list[str] = []

    try:
        text = Path(path).read_text(errors="replace")
    except FileNotFoundError:
        return contexts

    for line in text.splitlines(keepends=True):
        stripped = line.split(";")[0].strip()
        m = re.match(r"^\[([^\]]+)\]", stripped)
        if m:
            if current is not None:
                current._raw_lines = pending_raw
                contexts.append(current)
            current = DialplanContext(name=m.group(1))
            pending_raw = [line]
        elif current is not None:
            pending_raw.append(line)
            if stripped.startswith("exten"):
                _, _, rest = stripped.partition("=>")
                parts = rest.strip().split(",", 2)
                if len(parts) >= 3:
                    current.lines.append(ExtensionLine(
                        pattern=parts[0].strip(),
                        priority=parts[1].strip(),
                        app=parts[2].strip(),
                    ))
            elif stripped.startswith("include"):
                _, _, inc = stripped.partition("=>")
                current.includes.append(inc.strip())

    if current is not None:
        current._raw_lines = pending_raw
        contexts.append(current)

    return contexts


def write_extensions_conf(path: str, contexts: list[DialplanContext]) -> None:
    backup_file(path)
    parts: list[str] = []
    for ctx in contexts:
        if ctx._raw_lines:
            parts.extend(ctx._raw_lines)
        else:
            parts.append(f"[{ctx.name}]\n")
            for inc in ctx.includes:
                parts.append(f"include => {inc}\n")
            for ln in ctx.lines:
                parts.append(f"exten => {ln.pattern},{ln.priority},{ln.app}\n")
            parts.append("\n")
    Path(path).write_text("".join(parts))
    logger.info("Wrote %s", path)


# ------------------------------------------------------------------ #
# features.conf parser                                                #
# ------------------------------------------------------------------ #

def parse_features_conf(path: str) -> dict[str, dict[str, str]]:
    """Parse features.conf into {section_name: {key: value}}."""
    result: dict[str, dict[str, str]] = {}
    current: str | None = None
    try:
        text = Path(path).read_text(errors="replace")
    except FileNotFoundError:
        return result
    for line in text.splitlines():
        stripped = line.split(";")[0].strip()
        m = re.match(r"^\[([^\]]+)\]", stripped)
        if m:
            current = m.group(1)
            result[current] = {}
        elif current and "=" in stripped:
            k, _, v = stripped.partition("=")
            # handle => too
            if v.startswith(">"):
                v = v[1:]
            result[current][k.strip()] = v.strip()
    return result


def write_features_conf(path: str, data: dict[str, dict[str, str]]) -> None:
    backup_file(path)
    lines: list[str] = []
    for section, kvs in data.items():
        lines.append(f"[{section}]\n")
        for k, v in kvs.items():
            lines.append(f"{k} = {v}\n")
        lines.append("\n")
    Path(path).write_text("".join(lines))
    logger.info("Wrote %s", path)
