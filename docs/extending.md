# Extending

beeper-pg-sync is meant to be a foundation: a stable message table plus a clear ingestion boundary. Search indexes, embeddings, analytics and agents can live in separate projects on top of it.

## Stable hooks

| Hook | Use it for |
| --- | --- |
| `messages.id` (bigint, never reassigned) | foreign key for anything derived from a message: embeddings, labels, summaries |
| `messages.content_updated_at` (indexed) | incremental re-processing: "everything changed since my last run" |
| `pg_notify('beeper_pg_sync', json)` after each ingest that added or changed rows | wake a worker immediately instead of polling; payload has `conversation_id`, `source`, `added`, `changed` |
| `IngestResult.added` / `.changed` | message IDs touched by a `Store.ingest()` call, for in-process pipelines |
| `message_timeline` view | flat, joined rows for SQL, BI tools and LLM tool calls |
| `BEEPER_PG_SYNC_MIGRATIONS` / `migrate(conn, extra_dirs=[...])` | ship your own tables in the same database and migration history |

## Adding tables (for example, embeddings)

Put SQL files in your own directory with a prefix range that won't collide with core migrations (core uses `0001`-`0999`):

```sql
-- my_project/migrations/1001_embeddings.sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE message_embeddings (
    message_id  bigint PRIMARY KEY REFERENCES messages (id) ON DELETE CASCADE,
    model       text NOT NULL,
    embedding   vector(1024) NOT NULL,
    embedded_at timestamptz NOT NULL DEFAULT now()
);
```

```python
from beeper_pg_sync.db import connect, migrate

with connect() as conn:
    migrate(conn, extra_dirs=["my_project/migrations"])
```

The bundled `docker-compose.yml` uses the `pgvector/pgvector:pg17` image, so `CREATE EXTENSION vector` works out of the box.

A worker then embeds what's new or edited:

```sql
SELECT m.id, m.body
FROM messages m
LEFT JOIN message_embeddings e ON e.message_id = m.id
WHERE m.body <> '' AND NOT m.deleted
  AND (e.message_id IS NULL OR e.embedded_at < m.content_updated_at)
ORDER BY m.id
LIMIT 500;
```

## Adding a source

A source is anything that can produce `beeper_pg_sync.model.Batch` objects:

```python
from beeper_pg_sync.model import Batch, Conversation, Message, Participant
from beeper_pg_sync.store import Store

batch = Batch(
    source="my-exporter",
    conversation=Conversation(source_conversation_id="thread-42", network="signal", title="Weekend plans"),
    messages=[
        Message(
            source_message_id="m-1",
            body="who's driving?",
            sent_at=some_aware_datetime,
            direction="incoming",
            sender=Participant(native_id="user-7", display_name="Ana Silva"),
        )
    ],
    link_by_overlap=True,  # merge into a chat another source already has, if messages overlap
)
Store(conn).ingest(batch)
```

Guidelines:

- Pick a stable `source` name and stable `source_message_id`s; that is what makes re-ingestion idempotent.
- Use timezone-aware datetimes and set `time_precision` honestly.
- Set `native_id` on the conversation when you know the network's own thread ID. Two sources that agree on it link instantly.
- Use `Store.get_state` / `Store.put_state` for resumable cursors, keyed by your source name and a scope of your choosing.
