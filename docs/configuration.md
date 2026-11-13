# Configuration

Everything is read from the environment. `.env.example` lists every variable; copy it to `.env` and load it with `set -a; source .env; set +a` or Docker Compose's `env_file`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | none | Postgres connection string, e.g. `postgresql://sync:sync@localhost:5432/messages` |
| `BEEPER_URL` | `http://127.0.0.1:23373` | Beeper Desktop API base URL |
| `BEEPER_ACCESS_TOKEN` | none | Token from Beeper Desktop → Settings → Integrations |
| `BEEPER_NETWORKS` | all | Comma-separated allowlist, e.g. `instagram,whatsapp,signal` |
| `BEEPER_PAGES_PER_CHAT` | `4` | Older-history pages fetched per chat per run |
| `BEEPER_RESOLVE_NATIVE_IDS` | `false` | Ask bridges for native thread IDs via Matrix room state |
| `INGEST_TOKEN` | none | Shared secret for the extension; the server refuses to start without it |
| `INGEST_HOST` | `127.0.0.1` | Ingest server bind address (`0.0.0.0` inside Docker) |
| `INGEST_PORT` | `8765` | Ingest server port |
| `SYNC_INTERVAL` | `900` | Seconds between syncs in `beeper-pg-sync run` |
| `BEEPER_PG_SYNC_MIGRATIONS` | none | Extra migration directories, separated by `:` |

## Network names

Beeper bridge types map to these `network` values: `discord`, `googlechat`, `imessage`, `instagram`, `linkedin`, `matrix`, `messenger`, `reddit`, `signal`, `slack`, `sms` (Google Messages), `snapchat`, `telegram`, `whatsapp`, `x`. Unknown bridges fall back to a slug of Beeper's network name.

## Commands

| Command | Does |
| --- | --- |
| `beeper-pg-sync migrate` | create or upgrade the schema |
| `beeper-pg-sync sync [--full] [--network NAME] [--pages-per-chat N]` | one Beeper sync; `--full` ignores saved positions |
| `beeper-pg-sync import FILE...` | import extension exports (`.csv`, `.zip`, `.json`) |
| `beeper-pg-sync serve [--host H] [--port P]` | run only the extension ingest server |
| `beeper-pg-sync run [--interval S]` | migrate, serve, and sync on a loop (the daemon) |
| `beeper-pg-sync status` | per-network counts and recent runs as JSON |

## Running in Docker

`docker compose --profile daemon up -d` builds the image and runs `beeper-pg-sync run` beside the database, publishing the ingest server on `127.0.0.1:8765`. The container reaches Beeper Desktop on the host through `host.docker.internal`. If your Beeper API only listens on loopback, run the daemon on the host instead (`uv run beeper-pg-sync run`) and keep just the database in Docker.

## Security notes

- The Beeper client only issues GET requests to the accounts, chats, messages and room-state endpoints. Anything else raises before a request is made.
- The ingest server requires `Authorization: Bearer $INGEST_TOKEN` on every endpoint except `/healthz`, compares tokens in constant time and answers CORS only for `chrome-extension://` origins.
- Keep the ingest server on loopback or behind your own TLS proxy. Message bodies are private data.
