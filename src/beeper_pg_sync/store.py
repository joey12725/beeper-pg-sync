"""Writes `Batch` objects to Postgres: idempotent, cross-source aware.

Rules:
- Re-ingesting an observation updates it in place; it never duplicates.
- A message first seen by one source and later by another (Beeper and the
  Instagram extension, say) becomes one `messages` row with two
  `message_sources` rows. Matching uses direction, a time window and a
  formatting-insensitive body comparison, and only ever picks a unique match.
- Only the source that created a message rewrites its content (edits, deletes,
  reactions). Other sources can fill gaps, such as a missing sender or a more
  precise timestamp.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from .model import Account, Batch, IngestResult, Message, Participant
from .text import comparable

NOTIFY_CHANNEL = "beeper_pg_sync"
OVERLAP_MIN_MATCHES = 3
OVERLAP_MIN_KEY_LENGTH = 8


def _window(message: Message) -> timedelta:
    if message.time_precision == "exact":
        return timedelta(seconds=90)
    return timedelta(minutes=15)


class Store:
    def __init__(self, conn: psycopg.Connection, notify: bool = True):
        self.conn = conn
        self.notify = notify

    # -- public ---------------------------------------------------------------

    def ingest(self, batch: Batch) -> IngestResult:
        with self.conn.transaction():
            account_id = self._account(batch.source, batch.account) if batch.account else None
            conversation_id = self._conversation(batch, account_id)
            result = IngestResult(conversation_id=conversation_id)
            people: dict[str, int] = {}
            for participant in batch.participants:
                people[participant.native_id] = self._participant(batch.conversation.network, participant)
            for message in batch.messages:
                self._message(batch, conversation_id, message, people, result)
            self._link_replies(batch)
            if self.notify and (result.added or result.changed):
                payload = {"conversation_id": conversation_id, "source": batch.source, **result.summary}
                self.conn.execute("SELECT pg_notify(%s, %s)", (NOTIFY_CHANNEL, json.dumps(payload)))
        return result

    def get_state(self, source: str, scope: str) -> dict[str, Any] | None:
        return self.conn.execute(
            "SELECT * FROM sync_state WHERE source = %s AND scope = %s", (source, scope)
        ).fetchone()

    def put_state(
        self,
        source: str,
        scope: str,
        *,
        status: str,
        cursor: str | None,
        frontier: datetime | None,
        detail: dict[str, Any],
        success: bool,
    ) -> None:
        self.conn.execute(
            """INSERT INTO sync_state (source, scope, status, cursor, frontier, detail, last_success_at)
               VALUES (%s, %s, %s, %s, %s, %s, CASE WHEN %s THEN now() END)
               ON CONFLICT (source, scope) DO UPDATE SET
                   status = EXCLUDED.status,
                   cursor = EXCLUDED.cursor,
                   frontier = EXCLUDED.frontier,
                   detail = EXCLUDED.detail,
                   last_success_at = COALESCE(EXCLUDED.last_success_at, sync_state.last_success_at),
                   updated_at = now()""",
            (source, scope, status, cursor, frontier, Jsonb(detail), success),
        )

    def start_run(self, source: str) -> int:
        row = self.conn.execute("INSERT INTO sync_runs (source) VALUES (%s) RETURNING id", (source,)).fetchone()
        self.conn.commit()
        return row["id"]

    def finish_run(self, run_id: int, status: str, stats: dict[str, Any], error: str | None = None) -> None:
        self.conn.execute(
            "UPDATE sync_runs SET finished_at = now(), status = %s, stats = %s, error = %s WHERE id = %s",
            (status, Jsonb(stats), error, run_id),
        )
        self.conn.commit()

    # -- accounts, conversations, participants --------------------------------

    def _account(self, source: str, account: Account) -> int:
        row = self.conn.execute(
            """INSERT INTO accounts (source, source_account_id, network, user_native_id, display_name, status, metadata)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (source, source_account_id) DO UPDATE SET
                   network = EXCLUDED.network,
                   user_native_id = COALESCE(EXCLUDED.user_native_id, accounts.user_native_id),
                   display_name = COALESCE(EXCLUDED.display_name, accounts.display_name),
                   status = EXCLUDED.status,
                   metadata = accounts.metadata || EXCLUDED.metadata,
                   updated_at = now()
               RETURNING id""",
            (
                source,
                account.source_account_id,
                account.network,
                account.user_native_id,
                account.display_name,
                account.status,
                Jsonb(account.metadata),
            ),
        ).fetchone()
        return row["id"]

    def _participant(self, network: str, participant: Participant) -> int:
        row = self.conn.execute(
            """INSERT INTO participants (network, native_id, display_name, handle, is_self)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (network, native_id) DO UPDATE SET
                   display_name = COALESCE(EXCLUDED.display_name, participants.display_name),
                   handle = COALESCE(EXCLUDED.handle, participants.handle),
                   is_self = participants.is_self OR EXCLUDED.is_self,
                   updated_at = now()
               RETURNING id""",
            (network, participant.native_id, participant.display_name, participant.handle, participant.is_self),
        ).fetchone()
        return row["id"]

    def _conversation(self, batch: Batch, account_id: int | None) -> int:
        conv = batch.conversation
        linked = self.conn.execute(
            """SELECT conversation_id FROM conversation_sources
               WHERE source = %s AND source_conversation_id = %s""",
            (batch.source, conv.source_conversation_id),
        ).fetchone()
        if linked:
            cid = linked["conversation_id"]
            self.conn.execute(
                """UPDATE conversations SET
                       title = COALESCE(%s, title),
                       kind = CASE WHEN %s <> 'unknown' THEN %s ELSE kind END,
                       account_id = COALESCE(account_id, %s),
                       metadata = metadata || %s,
                       updated_at = now()
                   WHERE id = %s""",
                (conv.title, conv.kind, conv.kind, account_id, Jsonb(conv.metadata), cid),
            )
            self._adopt_native_id(cid, conv.network, conv.native_id)
            return cid

        cid, how = None, "source"
        if conv.native_id:
            row = self.conn.execute(
                "SELECT id FROM conversations WHERE network = %s AND native_id = %s",
                (conv.network, conv.native_id),
            ).fetchone()
            if row:
                cid, how = row["id"], "native_id"
        if cid is None and batch.link_by_overlap:
            cid = self._overlap_candidate(batch)
            if cid is not None:
                how = "overlap"
                self._adopt_native_id(cid, conv.network, conv.native_id)
        if cid is None:
            cid = self.conn.execute(
                """INSERT INTO conversations (network, native_id, account_id, title, kind, metadata)
                   VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                (conv.network, conv.native_id, account_id, conv.title, conv.kind, Jsonb(conv.metadata)),
            ).fetchone()["id"]
        self.conn.execute(
            """INSERT INTO conversation_sources (source, source_conversation_id, conversation_id, linked_by)
               VALUES (%s, %s, %s, %s)""",
            (batch.source, conv.source_conversation_id, cid, how),
        )
        return cid

    def _adopt_native_id(self, cid: int, network: str, native_id: str | None) -> None:
        if not native_id:
            return
        self.conn.execute(
            """UPDATE conversations SET native_id = %s
               WHERE id = %s AND native_id IS NULL
                 AND NOT EXISTS (SELECT 1 FROM conversations WHERE network = %s AND native_id = %s)""",
            (native_id, cid, network, native_id),
        )

    def _overlap_candidate(self, batch: Batch) -> int | None:
        """Find the one conversation from another source that shares enough messages."""
        votes: Counter[int] = Counter()
        for message in batch.messages[:500]:
            key = comparable(message.body)
            if len(key) < OVERLAP_MIN_KEY_LENGTH or message.sent_at is None or message.direction == "unknown":
                continue
            window = _window(message)
            rows = self.conn.execute(
                """SELECT m.conversation_id, m.body FROM messages m
                   JOIN conversations c ON c.id = m.conversation_id
                   WHERE c.network = %s AND m.direction = %s
                     AND m.sent_at BETWEEN %s AND %s
                     AND NOT EXISTS (SELECT 1 FROM conversation_sources cs
                                     WHERE cs.conversation_id = c.id AND cs.source = %s)""",
                (
                    batch.conversation.network,
                    message.direction,
                    message.sent_at - window,
                    message.sent_at + window,
                    batch.source,
                ),
            ).fetchall()
            for cid in {r["conversation_id"] for r in rows if comparable(r["body"]) == key}:
                votes[cid] += 1
        ranked = votes.most_common(2)
        if not ranked or ranked[0][1] < OVERLAP_MIN_MATCHES:
            return None
        if len(ranked) > 1 and ranked[0][1] < 2 * ranked[1][1]:
            return None
        return ranked[0][0]

    # -- messages -------------------------------------------------------------

    def _message(
        self,
        batch: Batch,
        cid: int,
        message: Message,
        people: dict[str, int],
        result: IngestResult,
    ) -> None:
        sender_id = None
        if message.sender is not None:
            if message.sender.native_id not in people:
                people[message.sender.native_id] = self._participant(batch.conversation.network, message.sender)
            sender_id = people[message.sender.native_id]
        key = (batch.source, batch.conversation.source_conversation_id, message.source_message_id)

        seen = self.conn.execute(
            """SELECT m.* FROM message_sources s JOIN messages m ON m.id = s.message_id
               WHERE s.source = %s AND s.source_conversation_id = %s AND s.source_message_id = %s""",
            key,
        ).fetchone()
        if seen:
            self._touch_source(key, message)
            if seen["source"] == batch.source and self._content_changed(seen, message):
                self.conn.execute(
                    """UPDATE messages SET body = %s, edited_at = %s, deleted = %s, reactions = %s,
                           attachments = %s, sender_id = COALESCE(sender_id, %s), last_seen_at = now()
                       WHERE id = %s""",
                    (
                        message.body,
                        message.edited_at,
                        message.deleted,
                        Jsonb(message.reactions),
                        Jsonb(message.attachments),
                        sender_id,
                        seen["id"],
                    ),
                )
                result.changed.append(seen["id"])
            else:
                self._fill_gaps(seen, message, sender_id)
                result.unchanged += 1
            return

        twin = self._find_twin(batch, cid, message)
        if twin is not None:
            self._fill_gaps(twin, message, sender_id)
            self._insert_source(key, twin["id"], message)
            result.matched += 1
            return

        row = self.conn.execute(
            """INSERT INTO messages (conversation_id, source, sender_id, sender_name, direction, sent_at,
                   time_precision, kind, body, edited_at, deleted, attachments, reactions, metadata)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (
                cid,
                batch.source,
                sender_id,
                message.sender_name or (message.sender.display_name if message.sender else None),
                message.direction,
                message.sent_at,
                message.time_precision if message.sent_at else "unknown",
                message.kind,
                message.body,
                message.edited_at,
                message.deleted,
                Jsonb(message.attachments),
                Jsonb(message.reactions),
                Jsonb(message.metadata),
            ),
        ).fetchone()
        self._insert_source(key, row["id"], message)
        result.added.append(row["id"])

    @staticmethod
    def _content_changed(row: dict[str, Any], message: Message) -> bool:
        return (
            row["body"] != message.body
            or row["deleted"] != message.deleted
            or row["edited_at"] != message.edited_at
            or row["reactions"] != message.reactions
        )

    def _find_twin(self, batch: Batch, cid: int, message: Message) -> dict[str, Any] | None:
        if message.sent_at is None:
            return None
        key = comparable(message.body)
        window = _window(message) if key else timedelta(seconds=2)
        rows = self.conn.execute(
            """SELECT m.* FROM messages m
               WHERE m.conversation_id = %s AND m.sent_at BETWEEN %s AND %s
                 AND (m.direction = %s OR m.direction = 'unknown' OR %s = 'unknown')
                 AND NOT EXISTS (SELECT 1 FROM message_sources s
                                 WHERE s.message_id = m.id AND s.source = %s)""",
            (
                cid,
                message.sent_at - window,
                message.sent_at + window,
                message.direction,
                message.direction,
                batch.source,
            ),
        ).fetchall()
        if key:
            candidates = [r for r in rows if comparable(r["body"]) == key]
        else:
            both_exact = message.time_precision == "exact"
            candidates = [r for r in rows if not r["body"] and both_exact and r["time_precision"] == "exact"]
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            # Repeated identical messages ("ok", "lol"): only the closest unique one is safe.
            ranked = sorted(candidates, key=lambda r: abs((r["sent_at"] - message.sent_at).total_seconds()))
            first, second = ranked[0], ranked[1]
            if (
                abs((first["sent_at"] - message.sent_at).total_seconds())
                < 2
                <= abs((second["sent_at"] - message.sent_at).total_seconds())
            ):
                return first
        return None

    def _fill_gaps(self, row: dict[str, Any], message: Message, sender_id: int | None) -> None:
        upgrade_time = (
            message.sent_at is not None and message.time_precision == "exact" and row["time_precision"] != "exact"
        )
        self.conn.execute(
            """UPDATE messages SET
                   sender_id = COALESCE(sender_id, %s),
                   sender_name = COALESCE(sender_name, %s),
                   direction = CASE WHEN direction = 'unknown' THEN %s ELSE direction END,
                   sent_at = CASE WHEN %s THEN %s ELSE sent_at END,
                   time_precision = CASE WHEN %s THEN 'exact' ELSE time_precision END,
                   last_seen_at = now()
               WHERE id = %s""",
            (
                sender_id,
                message.sender_name,
                message.direction,
                upgrade_time,
                message.sent_at,
                upgrade_time,
                row["id"],
            ),
        )

    def _insert_source(self, key: tuple[str, str, str], message_id: int, message: Message) -> None:
        self.conn.execute(
            """INSERT INTO message_sources (source, source_conversation_id, source_message_id,
                   message_id, reply_to_source_id, raw)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (*key, message_id, message.reply_to_source_id, Jsonb(message.raw)),
        )

    def _touch_source(self, key: tuple[str, str, str], message: Message) -> None:
        self.conn.execute(
            """UPDATE message_sources SET raw = %s, reply_to_source_id = COALESCE(%s, reply_to_source_id),
                   last_seen_at = now()
               WHERE source = %s AND source_conversation_id = %s AND source_message_id = %s""",
            (Jsonb(message.raw), message.reply_to_source_id, *key),
        )

    def _link_replies(self, batch: Batch) -> None:
        self.conn.execute(
            """UPDATE messages m SET reply_to_message_id = target.message_id
               FROM message_sources s
               JOIN message_sources target
                 ON target.source = s.source
                AND target.source_conversation_id = s.source_conversation_id
                AND target.source_message_id = s.reply_to_source_id
               WHERE s.message_id = m.id
                 AND s.source = %s AND s.source_conversation_id = %s
                 AND s.reply_to_source_id IS NOT NULL
                 AND m.reply_to_message_id IS NULL
                 AND target.message_id <> m.id""",
            (batch.source, batch.conversation.source_conversation_id),
        )
