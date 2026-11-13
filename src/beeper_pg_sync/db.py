"""Connections and a small, dependency-free migration runner."""

from __future__ import annotations

import os
from collections.abc import Iterable
from importlib import resources
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

MIGRATION_LOCK = 0x6D73_796E_63  # arbitrary advisory-lock key ("msync")


def connect(dsn: str | None = None) -> psycopg.Connection:
    dsn = dsn or os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("Set DATABASE_URL (for example postgresql://sync:sync@localhost:5432/messages)")
    return psycopg.connect(dsn, row_factory=dict_row, autocommit=True)


def migration_files(extra_dirs: Iterable[str | Path] = ()) -> list[tuple[str, str]]:
    """Return (version, sql) pairs sorted by filename.

    Core migrations ship in this package. Projects built on top of the schema
    can add their own directories (argument or BEEPER_PG_SYNC_MIGRATIONS,
    separated by os.pathsep); use a distinct numeric prefix range such as 1000+.
    """
    found: dict[str, str] = {}
    core = resources.files("beeper_pg_sync") / "migrations"
    for entry in core.iterdir():
        if entry.name.endswith(".sql"):
            found[entry.name[:-4]] = entry.read_text(encoding="utf-8")
    env = os.environ.get("BEEPER_PG_SYNC_MIGRATIONS", "")
    dirs = [*extra_dirs, *(p for p in env.split(os.pathsep) if p)]
    for directory in dirs:
        for path in sorted(Path(directory).glob("*.sql")):
            if path.stem in found:
                raise ValueError(f"Duplicate migration version {path.stem}")
            found[path.stem] = path.read_text(encoding="utf-8")
    return sorted(found.items())


def migrate(conn: psycopg.Connection, extra_dirs: Iterable[str | Path] = ()) -> list[str]:
    """Apply pending migrations, each in its own transaction. Returns applied versions."""
    applied: list[str] = []
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (MIGRATION_LOCK,))
        conn.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations (
                   version text PRIMARY KEY,
                   applied_at timestamptz NOT NULL DEFAULT now())"""
        )
        done = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}
        for version, sql in migration_files(extra_dirs):
            if version in done:
                continue
            with conn.transaction():
                conn.execute(sql)
                conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
            applied.append(version)
    return applied
