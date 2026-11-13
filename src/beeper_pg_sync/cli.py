"""Command line: migrate, sync, import, serve, run, status."""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import threading
import time
from collections.abc import Sequence

from .config import Settings
from .db import connect, migrate
from .server import serve, status_report
from .sources import beeper, instagram
from .store import Store

log = logging.getLogger("beeper_pg_sync")


def _sync_once(settings: Settings, full: bool = False) -> dict:
    client = beeper.Client(settings.beeper_url, settings.beeper_token)
    with connect(settings.database_url) as conn:
        job = beeper.BeeperSync(
            Store(conn),
            client,
            pages_per_chat=settings.pages_per_chat,
            networks=settings.beeper_networks,
            resolve_native_ids=settings.resolve_native_ids,
        )
        return job.run(full=full)


def cmd_migrate(settings: Settings, args: argparse.Namespace) -> int:
    with connect(settings.database_url) as conn:
        applied = migrate(conn)
    print("applied: " + ", ".join(applied) if applied else "schema is up to date")
    return 0


def cmd_sync(settings: Settings, args: argparse.Namespace) -> int:
    if args.network:
        settings.beeper_networks = [n.lower() for n in args.network]
    if args.pages_per_chat:
        settings.pages_per_chat = args.pages_per_chat
    stats = _sync_once(settings, full=args.full)
    print(json.dumps(stats))
    return 1 if stats["failed"] else 0


def cmd_import(settings: Settings, args: argparse.Namespace) -> int:
    with connect(settings.database_url) as conn:
        store = Store(conn)
        for path in args.files:
            for batch in instagram.batches_from_path(path):
                result = store.ingest(batch)
                title = batch.conversation.title or batch.conversation.source_conversation_id
                print(f"{path}: {title}: {json.dumps(result.summary)}")
    return 0


def cmd_serve(settings: Settings, args: argparse.Namespace) -> int:
    httpd = serve(
        settings.database_url,
        settings.ingest_token,
        args.host or settings.ingest_host,
        args.port or settings.ingest_port,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def cmd_run(settings: Settings, args: argparse.Namespace) -> int:
    """Long-running mode: migrate, serve the extension, sync Beeper on an interval."""
    with connect(settings.database_url) as conn:
        migrate(conn)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    httpd = None
    if settings.ingest_token:
        httpd = serve(settings.database_url, settings.ingest_token, settings.ingest_host, settings.ingest_port)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
    else:
        log.warning("INGEST_TOKEN not set; extension ingest disabled")
    interval = args.interval or settings.sync_interval
    try:
        while not stop.is_set():
            started = time.monotonic()
            try:
                log.info("beeper sync finished: %s", json.dumps(_sync_once(settings)))
            except beeper.BeeperError as error:
                log.error("beeper sync skipped: %s", error)
            stop.wait(max(0.0, interval - (time.monotonic() - started)))
    except KeyboardInterrupt:
        pass
    finally:
        if httpd:
            httpd.shutdown()
    return 0


def cmd_status(settings: Settings, args: argparse.Namespace) -> int:
    with connect(settings.database_url) as conn:
        print(json.dumps(status_report(conn), default=str, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="beeper-pg-sync",
        description="Sync Beeper chats (and Instagram DMs via the Chrome extension) into Postgres.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("migrate", help="create or upgrade the database schema").set_defaults(func=cmd_migrate)

    sync = sub.add_parser("sync", help="run one Beeper sync")
    sync.add_argument("--full", action="store_true", help="ignore saved positions and rescan every chat")
    sync.add_argument("--network", action="append", help="only these networks (repeatable), e.g. instagram")
    sync.add_argument("--pages-per-chat", type=int, help="backfill budget per chat per run")
    sync.set_defaults(func=cmd_sync)

    imp = sub.add_parser("import", help="import Instagram extension exports (.csv, .zip, .json)")
    imp.add_argument("files", nargs="+")
    imp.set_defaults(func=cmd_import)

    srv = sub.add_parser("serve", help="run the extension ingest server")
    srv.add_argument("--host")
    srv.add_argument("--port", type=int)
    srv.set_defaults(func=cmd_serve)

    run = sub.add_parser("run", help="migrate, serve the extension and sync Beeper every --interval seconds")
    run.add_argument("--interval", type=int)
    run.set_defaults(func=cmd_run)

    sub.add_parser("status", help="message counts and recent runs").set_defaults(func=cmd_status)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        return args.func(Settings(), args)
    except (RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
