"""Instagram fallback source: rows collected by the bundled Chrome extension.

The extension reads open Instagram DM threads in the browser and either sends
them to the ingest server (JSON payload) or saves CSV/ZIP exports. Both paths
end here and become ordinary `Batch` objects.

Instagram conversations are keyed by the thread ID in the DM URL
(`/direct/t/<thread>/`). When Beeper already holds the same chat under a
different ID, the store links the two by message overlap.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..model import Batch, Conversation, Message, Participant

SOURCE = "instagram-extension"
NETWORK = "instagram"
PAYLOAD_FORMAT = "beeper-pg-sync/instagram@1"

_MEDIA = re.compile(r"^sent (an image|\d+ images|a video)$")
_FILENAME = re.compile(r"instagram-(?P<title>.*)-(?P<thread>[^-]+)\.csv$")
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")


def _iso(value: str | None) -> datetime | None:
    if not value or not _ISO.match(value.strip()):
        return None
    return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))


def _timing(row: dict[str, Any]) -> tuple[datetime | None, str]:
    stamp = str(row.get("timestamp_ms") or "").strip()
    if re.fullmatch(r"\d{13}", stamp):
        return datetime.fromtimestamp(int(stamp) / 1000, tz=UTC), "exact"
    exact = _iso(row.get("time"))
    if exact:
        return exact, "exact"
    approx = _iso(row.get("approx_time"))
    if approx:
        return approx, "approximate"
    return None, "unknown"


def _strip(value: str | None) -> str | None:
    value = (value or "").strip()
    return value.removeprefix("SlideMessage:") or None


def row_to_message(row: dict[str, Any], thread_id: str, occurrence: Counter[str]) -> Message:
    text = str(row.get("message") or "")
    speaker = (row.get("speaker") or "").strip() or None
    handle = (row.get("username") or "").strip().lstrip("@") or None
    sent_at, precision = _timing(row)
    native = _strip(row.get("native_id"))
    if native:
        key = native
    else:
        # No stable ID exposed: fingerprint the visible content. Identical
        # repeated messages stay distinct through an occurrence counter.
        basis = json.dumps(
            [thread_id, speaker, text, row.get("time") or "", row.get("replying to") or ""], ensure_ascii=False
        )
        digest = hashlib.sha256(basis.encode()).hexdigest()[:24]
        key = f"fp:{digest}:{occurrence[digest]}"
        occurrence[digest] += 1

    kind, body, metadata = "text", text, {}
    media = _MEDIA.match(text)
    if media:
        kind = "video" if "video" in text else "image"
        body, metadata["summary"] = "", text
    elif text == "[attachment unavailable]":
        kind, body, metadata["summary"] = "file", "", text
    if row.get("replying to"):
        metadata["quoted"] = row["replying to"]
    if precision != "exact" and row.get("time"):
        metadata["time_label"] = row["time"]

    sender = None
    sender_id = str(row.get("sender_id") or "").strip()
    if sender_id or handle:
        sender = Participant(
            native_id=sender_id or f"username:{handle}",
            display_name=speaker,
            handle=handle,
            is_self=row.get("direction") == "outgoing",
        )
    direction = row.get("direction") if row.get("direction") in ("incoming", "outgoing") else "unknown"
    return Message(
        source_message_id=key,
        body=body,
        sent_at=sent_at,
        time_precision=precision,
        direction=direction,
        sender=sender,
        sender_name=speaker,
        kind=kind,
        reply_to_source_id=_strip(row.get("reply_id")),
        reactions=[{"reaction": r} for r in str(row.get("reactions") or "").split()],
        metadata=metadata,
        raw={k: v for k, v in row.items() if k not in ("message", "replying to") and v not in ("", None)},
    )


def build_batch(thread_id: str, title: str | None, rows: Iterable[dict[str, Any]]) -> Batch:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", thread_id or ""):
        raise ValueError(f"Invalid Instagram thread ID {thread_id!r}")
    occurrence: Counter[str] = Counter()
    messages = [row_to_message(row, thread_id, occurrence) for row in rows]
    return Batch(
        source=SOURCE,
        conversation=Conversation(
            source_conversation_id=thread_id,
            network=NETWORK,
            title=title or None,
            native_id=thread_id,
        ),
        messages=messages,
        link_by_overlap=True,
    )


def batch_from_payload(payload: dict[str, Any]) -> Batch:
    """The JSON document the extension POSTs to the ingest server."""
    if payload.get("format") != PAYLOAD_FORMAT:
        raise ValueError(f"Expected format {PAYLOAD_FORMAT!r}")
    rows = payload.get("messages")
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise ValueError("messages must be a list of objects")
    return build_batch(str(payload.get("thread_id") or ""), payload.get("title"), rows)


def batch_from_csv(text: str, filename: str) -> Batch:
    """A CSV saved by the extension, named instagram-<title>-<thread>.csv."""
    match = _FILENAME.search(Path(filename).name)
    if not match:
        raise ValueError(f"{filename}: expected an instagram-<title>-<thread>.csv export")
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    for row in rows:
        for key, value in row.items():
            # The exporter defuses spreadsheet formulas with a leading quote.
            if isinstance(value, str) and len(value) > 1 and value[0] == "'" and value[1] in "=+-@\t\r":
                row[key] = value[1:]
    return build_batch(match["thread"], match["title"], rows)


def batches_from_path(path: str | Path) -> list[Batch]:
    path = Path(path)
    if path.suffix == ".zip":
        batches = []
        with zipfile.ZipFile(path) as archive:
            for name in sorted(archive.namelist()):
                if name.endswith(".csv"):
                    batches.append(batch_from_csv(archive.read(name).decode("utf-8"), name))
        return batches
    if path.suffix == ".csv":
        return [batch_from_csv(path.read_text(encoding="utf-8"), path.name)]
    if path.suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        return [batch_from_payload(p) for p in (data if isinstance(data, list) else [data])]
    raise ValueError(f"{path}: unsupported file type (expected .csv, .zip or .json)")
