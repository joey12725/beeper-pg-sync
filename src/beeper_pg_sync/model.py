"""The ingestion contract every source produces.

A source turns whatever it reads (an HTTP API, a browser export, a file) into
`Batch` objects. `Store.ingest` is the only code that writes them to Postgres,
so adding a source never touches SQL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

Direction = Literal["incoming", "outgoing", "unknown"]
Precision = Literal["exact", "approximate", "unknown"]
ConversationKind = Literal["dm", "group", "channel", "thread", "unknown"]


@dataclass
class Account:
    source_account_id: str
    network: str
    user_native_id: str | None = None
    display_name: str | None = None
    status: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Participant:
    native_id: str
    display_name: str | None = None
    handle: str | None = None
    is_self: bool = False


@dataclass
class Conversation:
    source_conversation_id: str
    network: str
    title: str | None = None
    kind: ConversationKind = "unknown"
    native_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Message:
    source_message_id: str
    body: str = ""
    sent_at: datetime | None = None
    time_precision: Precision = "exact"
    direction: Direction = "unknown"
    sender: Participant | None = None
    sender_name: str | None = None
    kind: str = "text"
    edited_at: datetime | None = None
    deleted: bool = False
    reply_to_source_id: str | None = None
    attachments: list[dict[str, Any]] = field(default_factory=list)
    reactions: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Batch:
    """Messages from one conversation, as observed by one source."""

    source: str
    conversation: Conversation
    messages: list[Message] = field(default_factory=list)
    account: Account | None = None
    participants: list[Participant] = field(default_factory=list)
    # Fallback sources may be linked to an existing conversation from another
    # source when enough messages overlap. Primary sources never are.
    link_by_overlap: bool = False


@dataclass
class IngestResult:
    conversation_id: int
    added: list[int] = field(default_factory=list)
    changed: list[int] = field(default_factory=list)
    matched: int = 0
    unchanged: int = 0

    @property
    def summary(self) -> dict[str, int]:
        return {
            "added": len(self.added),
            "changed": len(self.changed),
            "matched": self.matched,
            "unchanged": self.unchanged,
        }
