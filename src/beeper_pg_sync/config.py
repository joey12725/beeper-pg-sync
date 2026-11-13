"""Settings, read from the environment (12-factor style)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _list(name: str) -> list[str]:
    return [x.strip().lower() for x in os.environ.get(name, "").split(",") if x.strip()]


@dataclass
class Settings:
    database_url: str | None = field(default_factory=lambda: os.environ.get("DATABASE_URL"))
    beeper_url: str = field(default_factory=lambda: os.environ.get("BEEPER_URL", "http://127.0.0.1:23373"))
    beeper_token: str | None = field(default_factory=lambda: os.environ.get("BEEPER_ACCESS_TOKEN"))
    beeper_networks: list[str] = field(default_factory=lambda: _list("BEEPER_NETWORKS"))
    pages_per_chat: int = field(default_factory=lambda: int(os.environ.get("BEEPER_PAGES_PER_CHAT", "4")))
    resolve_native_ids: bool = field(default_factory=lambda: _flag("BEEPER_RESOLVE_NATIVE_IDS"))
    ingest_token: str | None = field(default_factory=lambda: os.environ.get("INGEST_TOKEN"))
    ingest_host: str = field(default_factory=lambda: os.environ.get("INGEST_HOST", "127.0.0.1"))
    ingest_port: int = field(default_factory=lambda: int(os.environ.get("INGEST_PORT", "8765")))
    sync_interval: int = field(default_factory=lambda: int(os.environ.get("SYNC_INTERVAL", "900")))
