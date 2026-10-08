"""Minimal ``.env`` loader.

Deliberately dependency-free: the format we document is ``KEY=VALUE`` with
comments, and that is all this parses. Values already present in the real
environment always win, so a deployed container's variables are never
overridden by a file that happened to ship alongside the code.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

_loaded = False


def parse(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, separator, value = line.partition("=")
        if not separator:
            continue
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def load(path: Path | str | None = None, *, force: bool = False) -> dict[str, str]:
    """Read the env file into ``os.environ``. Safe to call repeatedly."""
    global _loaded
    if _loaded and not force and path is None:
        return {}

    target = Path(path) if path is not None else ENV_PATH
    _loaded = True
    if not target.exists():
        return {}

    try:
        values = parse(target.read_text(encoding="utf-8"))
    except OSError:
        return {}

    for key, value in values.items():
        # Never clobber a variable the platform already set.
        os.environ.setdefault(key, value)
    return values


def get(name: str, default: str | None = None) -> str | None:
    load()
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value
