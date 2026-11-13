"""End-to-end sync tests against a real Postgres (TEST_DATABASE_URL). Data is fabricated."""

import json
import threading
import urllib.error
import urllib.request
from datetime import datetime

import pytest
from fakes import FakeBeeper, chat, message, stamp

from beeper_pg_sync.db import migrate
from beeper_pg_sync.server import serve
from beeper_pg_sync.sources import instagram
from beeper_pg_sync.sources.beeper import BeeperSync
from beeper_pg_sync.store import Store

CHAT = "!ig_demo_1:beeper.local"
THREAD = "1000000000000001"


def count(conn, sql, *args):
    return conn.execute(sql, args).fetchone()["n"]


def conversation_messages(n_messages):
    return [message(i, f"demo message number {i}", chat=CHAT, outgoing=i % 3 == 0) for i in range(1, n_messages + 1)]


def payload(rows, thread=THREAD, title="Maya Chen"):
    return {"format": instagram.PAYLOAD_FORMAT, "thread_id": thread, "title": title, "messages": rows}


def ig_row(n, text, outgoing=False, **extra):
    return {
        "native_id": f"mid.demo-{n}",
        "timestamp_ms": str(int(datetime.fromisoformat(stamp(n)).timestamp() * 1000)),
        "direction": "outgoing" if outgoing else "incoming",
        "speaker": "Sam Rivera" if outgoing else "Maya Chen",
        "username": "@sam.rivera.demo" if outgoing else "@maya.makes.demo",
        "message": text,
        **extra,
    }


def test_migrations_are_idempotent(conn):
    assert migrate(conn) == []
    assert count(conn, "SELECT count(*) AS n FROM schema_migrations") == 1


def test_first_sync_backfills_in_budgeted_slices(conn):
    api = FakeBeeper(page_size=3)
    api.add_chat(chat(CHAT, "Maya Chen", last=10), conversation_messages(10))
    job = BeeperSync(Store(conn), api, pages_per_chat=2)

    first = job.run()
    assert first["added"] == 6
    state = Store(conn).get_state("beeper", CHAT)
    assert state["status"] == "backfilling" and state["cursor"] == "4"

    job.run()  # new-message check reaches the frontier, then two more backfill pages
    assert count(conn, "SELECT count(*) AS n FROM messages") == 10
    assert Store(conn).get_state("beeper", CHAT)["status"] == "complete"

    requests = api.requests
    skipped = job.run()
    assert skipped["skipped"] == 1 and api.requests == requests  # unchanged chat: zero message calls

    api.messages[CHAT].append(message(11, "a brand new message", chat=CHAT))
    api.chat_list[0]["lastActivity"] = stamp(11)
    assert job.run()["added"] == 1
    row = conn.execute("SELECT * FROM message_timeline ORDER BY sent_at DESC LIMIT 1").fetchone()
    assert row["body"] == "a brand new message"
    assert row["sender"] == "Maya Chen" and row["network"] == "instagram" and row["direction"] == "incoming"


def test_edits_update_content_and_bump_content_timestamp(conn):
    api = FakeBeeper(page_size=50)
    api.add_chat(chat(CHAT, "Maya Chen", last=3), conversation_messages(3))
    job = BeeperSync(Store(conn), api)
    job.run()
    before = conn.execute("SELECT id, content_updated_at FROM messages WHERE body LIKE '%number 2'").fetchone()

    api.messages[CHAT][1] = {**api.messages[CHAT][1], "text": "edited text", "editedTimestamp": stamp(5)}
    api.chat_list[0]["lastActivity"] = stamp(5)
    result = job.run()
    assert result["changed"] == 1
    after = conn.execute("SELECT body, content_updated_at FROM messages WHERE id = %s", (before["id"],)).fetchone()
    assert after["body"] == "edited text" and after["content_updated_at"] > before["content_updated_at"]


def test_reactions_are_not_messages_and_replies_link(conn):
    api = FakeBeeper(page_size=50)
    msgs = [
        message(1, "want to grab tacos friday?", chat=CHAT),
        message(2, "yes!! the place on 5th?", chat=CHAT, outgoing=True, linkedMessageID=f"{CHAT}-1"),
        {**message(3, "", chat=CHAT), "type": "REACTION"},
    ]
    api.add_chat(chat(CHAT, "Maya Chen", last=3), msgs)
    BeeperSync(Store(conn), api).run()
    rows = conn.execute("SELECT id, body, reply_to_message_id FROM messages ORDER BY sent_at").fetchall()
    assert [r["body"] for r in rows] == ["want to grab tacos friday?", "yes!! the place on 5th?"]
    assert rows[1]["reply_to_message_id"] == rows[0]["id"]


def test_instagram_extension_links_to_beeper_chat_by_overlap(conn):
    api = FakeBeeper(page_size=50)
    texts = [
        "are you coming to the gallery opening",
        "yes leaving in ten minutes",
        "grab me a coffee please",
        "oat milk latte coming up",
    ]
    beeper_msgs = [message(i, t, chat=CHAT, outgoing=i % 2 == 0) for i, t in enumerate(texts, 1)]
    api.add_chat(chat(CHAT, "Maya Chen", last=4), beeper_msgs)
    BeeperSync(Store(conn), api).run()

    rows = [ig_row(i, t, outgoing=i % 2 == 0) for i, t in enumerate(texts, 1)]
    rows.append(ig_row(5, "this one only the extension saw"))
    result = Store(conn).ingest(instagram.batch_from_payload(payload(rows)))

    assert result.matched == 4 and len(result.added) == 1
    assert count(conn, "SELECT count(*) AS n FROM conversations") == 1
    assert count(conn, "SELECT count(*) AS n FROM messages") == 5
    assert count(conn, "SELECT count(*) AS n FROM message_sources") == 9
    link = conn.execute("SELECT * FROM conversation_sources WHERE source = 'instagram-extension'").fetchone()
    assert link["linked_by"] == "overlap"
    assert conn.execute("SELECT native_id FROM conversations").fetchone()["native_id"] == THREAD

    # Re-sending the same export changes nothing.
    again = Store(conn).ingest(instagram.batch_from_payload(payload(rows)))
    assert again.summary == {"added": 0, "changed": 0, "matched": 0, "unchanged": 5}


def test_unrelated_instagram_thread_gets_its_own_conversation(conn):
    api = FakeBeeper(page_size=50)
    api.add_chat(chat(CHAT, "Maya Chen", last=4), conversation_messages(4))
    BeeperSync(Store(conn), api).run()
    rows = [ig_row(100 + i, f"completely different chat {i}") for i in range(4)]
    Store(conn).ingest(instagram.batch_from_payload(payload(rows, thread="2000000000000002", title="Theo Park")))
    assert count(conn, "SELECT count(*) AS n FROM conversations") == 2


def test_native_thread_ids_link_without_overlap(conn):
    api = FakeBeeper(page_size=50)
    api.add_chat(chat(CHAT, "Maya Chen", last=1), conversation_messages(1), native_id=THREAD)
    BeeperSync(Store(conn), api, resolve_native_ids=True).run()
    Store(conn).ingest(instagram.batch_from_payload(payload([ig_row(50, "hello from the browser")])))
    link = conn.execute("SELECT linked_by FROM conversation_sources WHERE source = 'instagram-extension'").fetchone()
    assert link["linked_by"] == "native_id"
    assert count(conn, "SELECT count(*) AS n FROM conversations") == 1


def test_csv_reimport_is_idempotent_and_keeps_repeats(conn, tmp_path):
    csv_text = (
        "﻿speaker,username,message,reactions,time,replying to\r\n"
        '"Theo Park","@theo.demo","ok","","Mar 14, 2026 6:00 PM",""\r\n'
        '"Theo Park","@theo.demo","ok","","Mar 14, 2026 6:00 PM",""\r\n'
        '"Sam Rivera","@sam.rivera.demo","see you there","👍","Mar 14, 2026 6:00 PM",""'
    )
    path = tmp_path / "instagram-Theo Park-3000000000000003.csv"
    path.write_text(csv_text, encoding="utf-8")
    store = Store(conn)
    for _ in range(2):
        for batch in instagram.batches_from_path(path):
            store.ingest(batch)
    assert count(conn, "SELECT count(*) AS n FROM messages") == 3
    assert count(conn, "SELECT count(*) AS n FROM messages WHERE time_precision = 'unknown'") == 3


def test_ingest_server_requires_token_and_stores_payload(dsn, conn):
    httpd = serve(dsn, "demo-ingest-token", "127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{httpd.server_address[1]}"
    body = json.dumps(payload([ig_row(1, "sent from the extension")])).encode()
    try:
        with pytest.raises(urllib.error.HTTPError) as denied:
            urllib.request.urlopen(urllib.request.Request(url + "/v1/ingest/instagram", data=body))
        assert denied.value.code == 401

        request = urllib.request.Request(
            url + "/v1/ingest/instagram",
            data=body,
            headers={
                "Authorization": "Bearer demo-ingest-token",
                "Content-Type": "application/json",
                "Origin": "chrome-extension://demoextensionid",
            },
        )
        with urllib.request.urlopen(request) as response:
            assert response.headers["Access-Control-Allow-Origin"] == "chrome-extension://demoextensionid"
            assert json.load(response)["added"] == 1
        status = urllib.request.Request(url + "/v1/status", headers={"Authorization": "Bearer demo-ingest-token"})
        with urllib.request.urlopen(status) as response:
            assert json.load(response)["networks"][0]["messages"] == 1
    finally:
        httpd.shutdown()
