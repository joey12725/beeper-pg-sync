"""Tiny HTTP ingest server for the Chrome extension (stdlib only).

POST /v1/ingest/instagram   one extension payload, or {"batches": [...]}
GET  /v1/status             message counts per network and recent sync runs
GET  /healthz               liveness

Every request except /healthz needs `Authorization: Bearer $INGEST_TOKEN`.
"""

from __future__ import annotations

import hmac
import json
import logging
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import psycopg

from .db import connect
from .sources import instagram
from .store import Store

log = logging.getLogger(__name__)
MAX_BODY = 64 * 1024 * 1024


def status_report(conn: psycopg.Connection) -> dict[str, Any]:
    networks = conn.execute(
        """SELECT c.network, count(m.id) AS messages, count(DISTINCT c.id) AS conversations,
                  max(m.sent_at) AS newest
           FROM conversations c LEFT JOIN messages m ON m.conversation_id = c.id
           GROUP BY c.network ORDER BY c.network"""
    ).fetchall()
    runs = conn.execute(
        """SELECT source, started_at, finished_at, status, stats, error
           FROM sync_runs ORDER BY id DESC LIMIT 5"""
    ).fetchall()
    return {"networks": networks, "runs": runs}


def make_handler(dsn: str | None, token: str) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "beeper-pg-sync"

        def log_message(self, fmt: str, *args: Any) -> None:
            log.info("%s %s", self.address_string(), fmt % args)

        def _send(self, code: int, body: Any) -> None:
            data = json.dumps(body, default=str).encode()
            self.send_response(code)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _cors(self) -> None:
            origin = self.headers.get("Origin", "")
            if origin.startswith("chrome-extension://"):
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Private-Network", "true")
                self.send_header("Vary", "Origin")

        def _authorized(self) -> bool:
            supplied = self.headers.get("Authorization", "")
            if hmac.compare_digest(supplied.encode(), f"Bearer {token}".encode()):
                return True
            self._send(HTTPStatus.UNAUTHORIZED, {"error": "missing or invalid bearer token"})
            return False

        def _with_db(self, work: Callable[[psycopg.Connection], Any]) -> None:
            try:
                with connect(dsn) as conn:
                    self._send(HTTPStatus.OK, work(conn))
            except ValueError as error:
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            except Exception:
                log.exception("request failed")
                self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "internal error"})

        def do_OPTIONS(self) -> None:  # noqa: N802 (http.server naming)
            self.send_response(HTTPStatus.NO_CONTENT)
            self._cors()
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/healthz":
                self._send(HTTPStatus.OK, {"ok": True})
            elif self.path == "/v1/status":
                if self._authorized():
                    self._with_db(status_report)
            else:
                self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/v1/ingest/instagram":
                self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            if not self._authorized():
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY:
                self._send(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "body missing or too large"})
                return
            try:
                payload = json.loads(self.rfile.read(length))
            except json.JSONDecodeError:
                self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid JSON"})
                return
            items = payload.get("batches") if isinstance(payload, dict) and "batches" in payload else [payload]

            def ingest(conn: psycopg.Connection) -> dict[str, Any]:
                batches = [instagram.batch_from_payload(p) for p in items]
                store = Store(conn)
                results = [store.ingest(b) for b in batches]
                return {
                    "conversations": [{"conversation_id": r.conversation_id, **r.summary} for r in results],
                    "added": sum(len(r.added) for r in results),
                }

            self._with_db(ingest)

    return Handler


def serve(dsn: str | None, token: str | None, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    if not token:
        raise RuntimeError("Set INGEST_TOKEN; the ingest server never runs unauthenticated")
    httpd = ThreadingHTTPServer((host, port), make_handler(dsn, token))
    log.info("ingest server listening on http://%s:%s", host, port)
    return httpd
