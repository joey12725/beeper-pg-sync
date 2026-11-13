# Architecture

```
src/beeper_pg_sync/
  model.py           the ingestion contract: Account, Conversation, Participant, Message, Batch
  store.py           Store.ingest(batch): the only code that writes messages
  db.py              connections + migration runner
  migrations/        numbered SQL files (0001_init.sql)
  sources/beeper.py  Beeper Desktop API client, normalization, incremental sync
  sources/instagram.py  Chrome extension payloads and CSV/ZIP/JSON exports
  server.py          HTTP ingest endpoint for the extension
  cli.py             migrate | sync | import | serve | run | status
extension/           Chrome MV3 extension (content script UI, page-world metadata bridge, service worker)
```

## Data model

A **conversation** belongs to one network (`instagram`, `whatsapp`, `discord`, ...). A **source** is how we learned about it (`beeper`, `instagram-extension`). Sources have their own IDs for the same thing, so each table that sources write to has a `*_sources` companion:

- `conversation_sources (source, source_conversation_id) -> conversation_id`, with `linked_by` recording whether the link came from the source itself, a shared native thread ID, a message overlap or a manual fix.
- `message_sources (source, source_conversation_id, source_message_id) -> message_id`, with the raw source metadata.

`messages` is the canonical table. Its `id` is assigned once and never changes, even when a second source later observes the same message. `messages.source` records which source created the row; that source alone may rewrite the content.

`time_precision` is `exact` for real timestamps (Beeper, Instagram native metadata), `approximate` for times derived from a displayed label, and `unknown` when there is nothing to go on.

`content_updated_at` changes only when `body`, `edited_at` or `deleted` change (a trigger enforces it). Reactions and bookkeeping updates leave it alone.

## Beeper sync

`BeeperSync.run()` walks `/v1/accounts` and every page of `/v1/chats`. Merged chat containers are skipped because their members appear separately. For each chat:

1. If the stored state is `complete` and `lastActivity` is unchanged, skip without fetching messages.
2. **New messages.** Page backwards from the newest message until a page reaches the stored `frontier` (newest timestamp from the last successful run). On the very first sync, stop after `pages_per_chat` pages and remember the oldest cursor.
3. **Backfill.** If a backfill cursor is stored, continue older history for up to `pages_per_chat` pages and save the new cursor. When Beeper reports no more history, the chat becomes `complete`.
4. Save `sync_state`: status (`complete`, `backfilling`, `partial`, `failed`), cursor, frontier, `lastActivity` and diagnostics.

Each page is ingested in its own transaction. A failure in one chat is recorded in `sync_state` and the run moves on; an authentication error stops the run.

Beeper sometimes returns an empty page with `hasMore=true` when a bridge has a history gap. On a first sync the cursor is parked for backfill. On later syncs the frontier is not advanced, so the next run retries rather than skipping messages.

Message normalization:

- `REACTION` events and hidden messages are not stored as messages (reactions are already aggregated on their target).
- Rich text is reduced to plain text with a parser that never loads URLs or runs scripts.
- Attachments keep type, MIME type, file name, size, duration and dimensions. Source URLs and media IDs are dropped.
- Matrix user IDs like `@whatsapp_15550100001:beeper.local` become network-native participant IDs (`15550100001`).

Beeper chat IDs are Matrix room IDs, not network-native thread IDs. With `BEEPER_RESOLVE_NATIVE_IDS=true`, the sync also asks the room's `m.bridge` state for the native thread ID (available on some self-hosted setups). If the endpoint is not there, it stops asking for the rest of the run.

## Instagram extension

The extension has three parts:

- `native.js` runs in the page's main world and copies a whitelist of message metadata (native ID, millisecond timestamp, sender ID, direction, reply target) from Instagram's rendered React props onto each message element as a data attribute. Nothing else from the page crosses over.
- `content.js` + `core.js` run in the isolated world, draw the panel in a Shadow DOM, scroll the thread and collect rows.
- `background.js` holds the server URL and token and makes the HTTP call, so Instagram's page never sees either.

The payload (`format: "beeper-pg-sync/instagram@1"`) carries the thread ID from `/direct/t/<thread>/`, the title and the rows. Rows without native timestamps get an `approx_time` computed in the browser's own time zone from the displayed label.

On the server, rows with a native ID use it as `source_message_id`. Rows without one get a fingerprint of their visible content plus an occurrence counter, so re-importing the same export is idempotent and two identical "ok" messages stay two rows.

## Cross-source matching

When a batch arrives for a conversation the source has not seen before:

1. If the batch carries a native thread ID that another conversation already has, link to it.
2. Otherwise, for fallback sources (`link_by_overlap=True`), look for a conversation on the same network, not yet linked to this source, that shares at least three matching messages, at least twice as many as any runner-up.
3. Otherwise create a new conversation.

A message the source has not seen before merges into an existing row when there is exactly one candidate in the same conversation, not yet observed by this source, with the same direction (or unknown), a matching formatting-insensitive body and a timestamp within 90 seconds (15 minutes for approximate times). Media-only messages need exact timestamps within 2 seconds. When several identical candidates exist, only a clear nearest match within 2 seconds is accepted. Everything else becomes a new row: a rare duplicate is easier to fix than a wrong merge.
