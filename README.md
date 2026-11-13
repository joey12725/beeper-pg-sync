<img src="assets/logo.png" width="88" height="88" alt="Chat bubble with a download arrow">

# beeper-pg-sync

**Every chat you have, in one Postgres database you own.**

beeper-pg-sync pulls your conversations out of [Beeper](https://www.beeper.com/) (WhatsApp, Signal, Telegram, Discord, iMessage, Google Messages, Instagram and the rest of the networks Beeper bridges) and keeps them synced into a clean, query-ready Postgres schema. A bundled Chrome extension covers the other path: it reads Instagram DMs straight from the browser and sends them to the same database, where they merge with whatever Beeper already saw.

Then it's just SQL. Search five years of group chats, chart who you talk to, feed a local LLM, build a dashboard. It's your data, and it lives in a database you run.

<p align="center"><img src="assets/architecture.svg" alt="Beeper, the Chrome extension and file exports flow through beeper-pg-sync into Postgres" width="860"></p>

## Features

- **Beeper as the primary source.** Reads the local Beeper Desktop API: every account, every chat (archived and low-priority included), full message history.
- **Strictly read-only.** The client only calls an allowlist of GET endpoints. It never sends, reacts, marks anything read or downloads media, and it drops attachment URLs before they reach the database.
- **Incremental and resumable.** Each chat keeps its own frontier and backfill cursor. Unchanged chats cost zero message requests, new messages arrive in seconds, and old history fills in a few pages per chat per run so one giant group never hogs a sync.
- **Instagram fallback via Chrome extension.** Prepare a chat (or every chat) in Instagram's web UI, hit **Sync**, and it lands in Postgres. Native Instagram message IDs and millisecond timestamps come along when the page exposes them.
- **Cross-source dedupe.** A message seen by Beeper and by the extension becomes one row with two provenance records. Conversations link on native thread IDs, or on a unique overlap of matching messages.
- **Edits and deletes tracked.** Edited messages update in place and bump `content_updated_at`, so downstream indexes know exactly what to refresh.
- **Built to be built on.** Stable `bigint` message IDs, a single `Store.ingest()` write path, pluggable migration directories, `pg_notify` on every change and a `message_timeline` view for ad-hoc SQL.
- **Small footprint.** One runtime dependency (psycopg). The ingest server and Beeper client are standard library.

## Quickstart

You need Python 3.11+, [uv](https://docs.astral.sh/uv/), Docker (for Postgres) and Beeper Desktop with its API turned on.

```bash
git clone https://github.com/joey12725/beeper-pg-sync.git
cd beeper-pg-sync

docker compose up -d db          # Postgres 17 on localhost:5432
cp .env.example .env             # add BEEPER_ACCESS_TOKEN and an INGEST_TOKEN
uv sync
set -a; source .env; set +a

uv run beeper-pg-sync migrate    # create the schema
uv run beeper-pg-sync sync       # first sync
uv run beeper-pg-sync status     # counts per network, recent runs
```

To get a Beeper token: in Beeper Desktop open Settings → Integrations, make sure the Desktop API is enabled, click **+** next to **Approved connections** and copy the token it creates.

Keep it running with `uv run beeper-pg-sync run`. That applies migrations, starts the extension ingest server on `127.0.0.1:8765` and syncs Beeper every `SYNC_INTERVAL` seconds (15 minutes by default). Prefer containers? `docker compose --profile daemon up -d` runs the same thing next to the database.

Now query it:

```sql
SELECT sent_at, network, conversation, sender, body
FROM message_timeline
WHERE to_tsvector('simple', body) @@ plainto_tsquery('simple', 'gallery opening')
ORDER BY sent_at DESC
LIMIT 20;
```

## The Chrome extension

<p align="center"><img src="assets/extension.png" alt="The export panel open beside an Instagram-style DM thread (demo data)" width="860"></p>

The extension lives in [`extension/`](extension) and works on its own as an Instagram DM exporter, with sync on top.

1. Open `chrome://extensions`, turn on **Developer mode**, click **Load unpacked** and pick the `extension/` folder (or the folder from a release ZIP).
2. Open the extension's **Details → Extension options**. Enter your server URL (`http://127.0.0.1:8765` by default) and the `INGEST_TOKEN` from `.env`. **Test connection** confirms it.
3. Open [Instagram DMs](https://www.instagram.com/direct/inbox/) in English and click **Export**.

Pick a range (from a selected message, the N messages before one, or the whole conversation), then **Prepare export** and choose:

| Button | What you get |
| --- | --- |
| **Copy** | `speaker: message` lines on the clipboard |
| **Markdown** | a `.md` transcript with timestamps |
| **CSV** | `speaker, username, message, reactions, time, replying to, native_id, sender_id, direction, reply_id, timestamp_ms, time_precision` with formula-injection protection |
| **Sync** | the chat sent to your beeper-pg-sync server |

**Export all chats** walks Primary, General and Requests, saves a ZIP of per-chat CSVs with a coverage report, and can send each chat to the server as it goes. Files the extension saved earlier import with `uv run beeper-pg-sync import instagram-chats.zip`.

The extension runs locally. Its only network traffic is the server URL you configure. Instagram can mark chats as read when they're opened, so bulk export opens them one at a time and keeps the report honest about what it reached.

## How it works

**Beeper sync.** For each chat, `sync` compares Beeper's `lastActivity` with the last complete run and skips untouched chats outright. Otherwise it pages backwards from the newest message until it reaches the stored frontier, then spends up to `BEEPER_PAGES_PER_CHAT` pages continuing older history from a saved cursor. Every page is written in its own transaction, so an interrupted run loses nothing and the next one picks up where it stopped.

**One write path.** Sources never touch SQL. They produce `Batch` objects (a conversation plus messages) and `Store.ingest()` does the rest: upserting accounts and participants, resolving the conversation, matching messages already seen by another source, linking replies and emitting a `NOTIFY`.

**Dedupe rules.** Re-ingesting an observation updates it in place. A message from a second source merges into an existing row only when direction, a time window and a formatting-insensitive body comparison all point to exactly one candidate. Only the source that created a row rewrites its content; other sources fill gaps, such as a missing sender or a more precise timestamp.

More detail lives in [docs/architecture.md](docs/architecture.md), [docs/configuration.md](docs/configuration.md) and [docs/extending.md](docs/extending.md).

## Schema at a glance

| Table | Holds |
| --- | --- |
| `accounts` | connected accounts per source (Beeper account IDs, bridge type) |
| `conversations` | one row per chat, unique on `(network, native_id)` when known |
| `conversation_sources` | which source IDs map to each conversation, and how they were linked |
| `participants` | people per network, with display names and handles |
| `messages` | the canonical message rows: body, sender, direction, timestamps, reactions, attachment metadata |
| `message_sources` | every source observation of every message, with its raw metadata |
| `sync_state`, `sync_runs` | resumable per-chat positions and a run log |

## Development

```bash
uv sync
uv run ruff check src tests && uv run ruff format --check src tests
TEST_DATABASE_URL=postgresql://sync:sync@localhost:5432/messages_test uv run pytest

npm ci
npm run lint && npm test      # extension: jsdom tests + prettier
npm run package               # dist/instagram-chat-exporter.zip
```

Database tests create and drop the `public` schema of `TEST_DATABASE_URL`, so point it at a throwaway database. All fixtures and screenshots use made-up people and messages.

## Tech stack

Python 3.11+ · psycopg 3 · PostgreSQL 16/17 · Beeper Desktop API · Chrome Manifest V3 (vanilla JS, Shadow DOM UI) · pytest · node:test + jsdom · ruff · prettier · Docker Compose · GitHub Actions

## Credits

Built by [Joey Hersh](https://github.com/joey12725). MIT licensed. Not affiliated with Beeper, Automattic or Meta; use it with your own accounts and follow each network's terms.
