"""Beeper Desktop API source (primary).

Beeper Desktop exposes a local REST API (Settings -> Integrations)
that lists every connected account, chat and message across the networks Beeper
bridges. This module reads it strictly read-only: GET requests to an allowlist
of collection endpoints, no sends, no mark-read, no media downloads.

Sync model, per chat:
- First run: page backwards from the newest message for `pages_per_chat`
  pages, then save the oldest cursor as a backfill position.
- Later runs: fetch new messages until reaching the stored frontier, then
  continue the backfill for another `pages_per_chat` pages. A huge chat never
  monopolizes a run, and every run makes progress on old history.
- Chats whose `lastActivity` has not changed since the last complete sync are
  skipped without a single message request.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..model import Account, Batch, Conversation, Message, Participant
from ..store import Store
from ..text import plain

log = logging.getLogger(__name__)

SOURCE = "beeper"
DEFAULT_URL = "http://127.0.0.1:23373"

# Beeper bridge types -> network names stored in Postgres.
NETWORKS = {
    "discordgo": "discord",
    "discord": "discord",
    "facebookgo": "messenger",
    "facebook": "messenger",
    "gmessages": "sms",
    "googlechat": "googlechat",
    "imessage": "imessage",
    "imessagego": "imessage",
    "instagramgo": "instagram",
    "instagram": "instagram",
    "linkedin": "linkedin",
    "matrix": "matrix",
    "reddit": "reddit",
    "signal": "signal",
    "slackgo": "slack",
    "snapchat": "snapchat",
    "telegram": "telegram",
    "twitter": "x",
    "whatsapp": "whatsapp",
}

MESSAGE_KINDS = {
    "TEXT": "text",
    "NOTICE": "notice",
    "IMAGE": "image",
    "VIDEO": "video",
    "VOICE": "voice",
    "AUDIO": "audio",
    "FILE": "file",
    "STICKER": "sticker",
    "LOCATION": "location",
}

# Attachment fields worth keeping. Source URLs and media IDs are dropped so the
# database never holds links to private (or disappearing) media.
ATTACHMENT_FIELDS = (
    "type",
    "mimeType",
    "fileName",
    "fileSize",
    "duration",
    "isGif",
    "isSticker",
    "isVoiceNote",
    "size",
)

_ALLOWED = (
    re.compile(r"/v1/accounts"),
    re.compile(r"/v1/chats"),
    re.compile(r"/v1/chats/[^/?#]+/messages"),
    re.compile(r"/_matrix/client/v3/rooms/[^/?#]+/state"),
)
_MATRIX_USER = re.compile(r"^@([^_:]+)_(.+):[^:]+$")


class BeeperError(RuntimeError):
    pass


class BeeperAuthError(BeeperError):
    pass


class Client:
    """Minimal read-only Beeper Desktop API client (stdlib only)."""

    def __init__(self, base_url: str = DEFAULT_URL, token: str | None = None, timeout: float = 60):
        if not token:
            raise BeeperAuthError(
                "Set BEEPER_ACCESS_TOKEN (Beeper Desktop -> Settings -> Integrations -> Approved connections)"
            )
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._room_state = True

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not any(p.fullmatch(path) for p in _ALLOWED):
            raise ValueError(f"Refusing non-collection endpoint {path}")
        query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
        url = self.base_url + path + ("?" + query if query else "")
        request = urllib.request.Request(url, headers={"Authorization": "Bearer " + self.token})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code in (401, 403):
                raise BeeperAuthError("Beeper rejected the access token") from None
            raise BeeperError(f"Beeper returned HTTP {error.code} for {path}") from None
        except urllib.error.URLError as error:
            raise BeeperError(f"Beeper Desktop API unreachable at {self.base_url}: {error.reason}") from None

    def accounts(self) -> list[dict[str, Any]]:
        data = self.get("/v1/accounts")
        if not isinstance(data, list):
            raise BeeperError("Unexpected /v1/accounts response")
        return data

    def chats(self) -> Iterator[dict[str, Any]]:
        """Every chat, including archived and low-priority ones."""
        seen: set[str] = set()
        for page in self._pages("/v1/chats", {"limit": 200}):
            for chat in page["items"]:
                if chat["id"] not in seen:
                    seen.add(chat["id"])
                    yield chat

    def message_pages(self, chat_id: str, cursor: str | None = None) -> Iterator[dict[str, Any]]:
        params = {"cursor": cursor, "direction": "before"} if cursor else None
        yield from self._pages(f"/v1/chats/{urllib.parse.quote(chat_id, safe='')}/messages", params)

    def native_chat_id(self, chat_id: str) -> str | None:
        """Network-native thread ID from the bridge's m.bridge room state, when exposed."""
        if not self._room_state:
            return None
        try:
            state = self.get(f"/_matrix/client/v3/rooms/{urllib.parse.quote(chat_id, safe='')}/state")
        except BeeperAuthError:
            raise
        except BeeperError:
            self._room_state = False  # not available on this Beeper install; stop asking
            return None
        bridges = [e.get("content", {}) for e in state if isinstance(e, dict) and e.get("type") == "m.bridge"]
        if len(bridges) != 1:
            return None
        native = bridges[0].get("channel", {}).get("id")
        return str(native) if native else None

    def _pages(self, path: str, params: dict[str, Any] | None) -> Iterator[dict[str, Any]]:
        query = dict(params or {})
        seen: set[str] = set()
        while True:
            page = self.get(path, query)
            if not isinstance(page, dict) or not isinstance(page.get("items"), list):
                raise BeeperError(f"Unexpected pagination response from {path}")
            yield page
            cursor = page.get("oldestCursor")
            if not page.get("hasMore") or not page["items"] or not cursor or cursor in seen:
                return
            seen.add(cursor)
            query.update(cursor=cursor, direction="before")


# -- normalization ------------------------------------------------------------


def network_for(account: dict[str, Any]) -> str:
    bridge = (account.get("bridge") or {}).get("type") or ""
    bridge = bridge.removeprefix("local-").lower()
    if bridge in NETWORKS:
        return NETWORKS[bridge]
    name = (account.get("network") or bridge or "unknown").lower()
    return re.sub(r"[^a-z0-9]+", "-", name).strip("-") or "unknown"


def native_user_id(matrix_id: str) -> str:
    """'@instagramgo_1789:beeper.local' -> '1789'. Unknown shapes pass through."""
    match = _MATRIX_USER.match(matrix_id or "")
    return match[2] if match else matrix_id


def parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def normalize_account(account: dict[str, Any]) -> Account:
    user = account.get("user") or {}
    return Account(
        source_account_id=account["accountID"],
        network=network_for(account),
        user_native_id=str(user["id"]) if user.get("id") else None,
        display_name=user.get("fullName") or user.get("username"),
        status=account.get("status"),
        metadata={
            "bridge": {k: v for k, v in (account.get("bridge") or {}).items() if k in ("id", "type", "provider")}
        },
    )


def normalize_participants(chat: dict[str, Any]) -> list[Participant]:
    people = []
    for item in (chat.get("participants") or {}).get("items", []):
        if not item.get("id"):
            continue
        people.append(
            Participant(
                native_id=native_user_id(item["id"]),
                display_name=item.get("fullName"),
                handle=item.get("username"),
                is_self=bool(item.get("isSelf")),
            )
        )
    return people


def normalize_chat(chat: dict[str, Any], account: dict[str, Any], native_id: str | None = None) -> Conversation:
    kind = {"single": "dm", "group": "group"}.get(chat.get("type"), "unknown")
    return Conversation(
        source_conversation_id=chat["id"],
        network=network_for(account),
        title=chat.get("title") or None,
        kind=kind,
        native_id=native_id,
        metadata={"beeper": {"archived": chat.get("isArchived"), "expiry_seconds": chat.get("messageExpirySeconds")}},
    )


def normalize_message(item: dict[str, Any], people: dict[str, Participant]) -> Message | None:
    """One Beeper message -> Message, or None for reaction/hidden events."""
    if item.get("type") == "REACTION" or item.get("isHidden"):
        return None
    sender_key = item.get("senderID") or ""
    known = people.get(native_user_id(sender_key))
    sender = None
    if sender_key:
        sender = Participant(
            native_id=native_user_id(sender_key),
            display_name=item.get("senderName") or (known.display_name if known else None),
            handle=known.handle if known else None,
            is_self=bool(item.get("isSender")),
        )
    links = [{"url": x.get("url"), "title": x.get("title")} for x in item.get("links") or [] if x.get("url")]
    return Message(
        source_message_id=str(item["id"]),
        body=plain(item.get("text")),
        sent_at=parse_time(item.get("timestamp")),
        time_precision="exact",
        direction="outgoing" if item.get("isSender") else "incoming",
        sender=sender,
        sender_name=item.get("senderName"),
        kind=MESSAGE_KINDS.get(item.get("type") or "TEXT", (item.get("type") or "text").lower()),
        edited_at=parse_time(item.get("editedTimestamp")),
        deleted=bool(item.get("isDeleted")),
        reply_to_source_id=str(item["linkedMessageID"]) if item.get("linkedMessageID") else None,
        attachments=[{k: a[k] for k in ATTACHMENT_FIELDS if k in a} for a in item.get("attachments") or []],
        reactions=[
            {
                "participant": native_user_id(r.get("participantID") or ""),
                "reaction": r.get("reactionKey"),
                "emoji": r.get("emoji", True),
            }
            for r in item.get("reactions") or []
        ],
        metadata={"links": links} if links else {},
        raw={k: item[k] for k in ("id", "sortKey", "type", "accountID") if k in item},
    )


# -- sync -----------------------------------------------------------------------


@dataclass
class BeeperSync:
    store: Store
    client: Client
    pages_per_chat: int = 4
    networks: Iterable[str] = ()
    resolve_native_ids: bool = False
    max_new_pages: int = 500

    def run(self, full: bool = False) -> dict[str, Any]:
        run_id = self.store.start_run(SOURCE)
        stats: dict[str, Any] = {"chats": 0, "skipped": 0, "failed": 0, "added": 0, "changed": 0, "matched": 0}
        try:
            accounts = {a["accountID"]: a for a in self.client.accounts()}
            wanted = set(self.networks)
            for chat in self.client.chats():
                account = accounts.get(chat.get("accountID"))
                if account is None or chat.get("merge"):
                    continue  # merged containers have no messages of their own
                if wanted and network_for(account) not in wanted:
                    continue
                try:
                    outcome = self.sync_chat(chat, account, full=full)
                except BeeperAuthError:
                    raise
                except (BeeperError, ValueError, KeyError) as error:
                    log.warning("chat %s failed: %s", chat.get("id"), error)
                    self._fail(chat, str(error))
                    stats["failed"] += 1
                    continue
                if outcome is None:
                    stats["skipped"] += 1
                    continue
                stats["chats"] += 1
                for key in ("added", "changed", "matched"):
                    stats[key] += outcome[key]
        except Exception as error:
            self.store.finish_run(run_id, "failed", stats, str(error))
            raise
        self.store.finish_run(run_id, "partial" if stats["failed"] else "ok", stats)
        return stats

    def sync_chat(self, chat: dict[str, Any], account: dict[str, Any], full: bool = False) -> dict[str, int] | None:
        state = self.store.get_state(SOURCE, chat["id"])
        detail = dict(state["detail"]) if state else {}
        last_activity = chat.get("lastActivity")
        if (
            not full
            and state
            and state["status"] == "complete"
            and last_activity
            and detail.get("last_activity") == last_activity
        ):
            return None

        native_id = detail.get("native_id")
        if native_id is None and self.resolve_native_ids:
            native_id = self.client.native_chat_id(chat["id"])
        conversation = normalize_chat(chat, account, native_id)
        people = normalize_participants(chat)
        by_id = {p.native_id: p for p in people}
        totals = {"added": 0, "changed": 0, "matched": 0, "pages": 0}
        first_page = [True]

        def ingest(page: dict[str, Any]) -> list[datetime]:
            messages = [m for m in (normalize_message(i, by_id) for i in page["items"]) if m]
            stamps = [m.sent_at for m in messages if m.sent_at]
            if messages or first_page[0]:
                batch = Batch(
                    source=SOURCE,
                    conversation=conversation,
                    messages=messages,
                    account=normalize_account(account),
                    participants=people if first_page[0] else [],
                )
                result = self.store.ingest(batch)
                totals["added"] += len(result.added)
                totals["changed"] += len(result.changed)
                totals["matched"] += result.matched
                first_page[0] = False
            totals["pages"] += 1
            return stamps

        frontier = None if full or not state else state["frontier"]
        backfill = None if full or not state else detail.get("backfill_cursor")
        first_sync = frontier is None
        newest = frontier
        reached = False
        gap = False

        # Phase 1: newest messages, down to the stored frontier.
        for number, page in enumerate(self.client.message_pages(chat["id"]), 1):
            stamps = ingest(page)
            if stamps:
                newest = max([newest, *stamps]) if newest else max(stamps)
            more = bool(page.get("hasMore"))
            if not more:
                reached, backfill = True, None
                break
            if not page["items"]:
                # A bridge history gap: hasMore with an empty page. On a first sync,
                # park the cursor for backfill. On later syncs keep the old frontier
                # so the next run retries instead of skipping messages.
                gap = True
                if first_sync:
                    reached, backfill = True, page.get("oldestCursor")
                break
            if frontier is not None and stamps and min(stamps) <= frontier:
                reached = True
                break
            if first_sync and number >= self.pages_per_chat:
                reached, backfill = True, page.get("oldestCursor")
                break
            if number >= self.max_new_pages:
                break

        # Phase 2: continue older history from the saved cursor.
        if backfill and not first_sync:
            cursor = backfill
            for number, page in enumerate(self.client.message_pages(chat["id"], cursor), 1):
                ingest(page)
                if not page.get("hasMore"):
                    backfill = None
                    break
                if not page["items"]:
                    gap = True  # retry this cursor next run
                    break
                backfill = page.get("oldestCursor") or backfill
                if number >= self.pages_per_chat:
                    break

        status = "complete" if reached and not backfill else "backfilling" if reached else "partial"
        detail.update(
            last_activity=last_activity,
            backfill_cursor=backfill,
            native_id=native_id,
            history_gap=gap,
            network=conversation.network,
        )
        self.store.put_state(
            SOURCE,
            chat["id"],
            status=status,
            cursor=backfill,
            frontier=newest if reached else frontier,
            detail=detail,
            success=reached,
        )
        return totals

    def _fail(self, chat: dict[str, Any], error: str) -> None:
        state = self.store.get_state(SOURCE, chat["id"])
        detail = {**(state["detail"] if state else {}), "error": error}
        self.store.put_state(
            SOURCE,
            chat["id"],
            status="failed",
            cursor=state["cursor"] if state else None,
            frontier=state["frontier"] if state else None,
            detail=detail,
            success=False,
        )
