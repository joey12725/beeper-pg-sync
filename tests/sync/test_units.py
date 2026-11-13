"""Pure-Python tests: no database required."""

from collections import Counter

import pytest

from beeper_pg_sync.db import migration_files
from beeper_pg_sync.sources import beeper, instagram
from beeper_pg_sync.text import comparable, plain


def test_plain_strips_rich_text_without_loading_anything():
    html = '<p>Dinner at <strong>7</strong>?</p><p>bring <img alt="🍕"> &amp; snacks</p><script>alert(1)</script>'
    assert plain(html) == "Dinner at 7?\n\nbring 🍕 & snacks"
    assert plain(None) == ""
    assert plain("5 &lt; 6") == "5 < 6"


def test_comparable_ignores_formatting_and_case():
    assert comparable("**See** [the doc](https://example.com)  NOW") == comparable("see the doc now")
    assert comparable("<:wave:123456>") == ":wave:"


def test_network_mapping_and_matrix_user_ids():
    assert beeper.network_for({"bridge": {"type": "instagramgo"}}) == "instagram"
    assert beeper.network_for({"bridge": {"type": "local-whatsapp"}}) == "whatsapp"
    assert beeper.network_for({"bridge": {"type": "brandnewgo"}, "network": "Brand New"}) == "brand-new"
    assert beeper.native_user_id("@discord_221590782384013314:beeper.com") == "221590782384013314"
    assert beeper.native_user_id("@instagramgo_5550002:beeper.local") == "5550002"
    assert beeper.native_user_id("not-a-matrix-id") == "not-a-matrix-id"


def test_normalize_message_drops_reactions_and_media_urls():
    assert beeper.normalize_message({"id": "1", "type": "REACTION"}, {}) is None
    assert beeper.normalize_message({"id": "1", "type": "TEXT", "isHidden": True}, {}) is None
    item = {
        "id": "42",
        "type": "IMAGE",
        "text": "",
        "timestamp": "2026-03-14T18:00:00.250Z",
        "senderID": "@whatsapp_15550100001:beeper.local",
        "senderName": "Theo Park",
        "attachments": [{"type": "img", "mimeType": "image/jpeg", "srcURL": "mxc://private/abc", "id": "mxc://x"}],
        "reactions": [{"participantID": "@whatsapp_15550100000:beeper.local", "reactionKey": "🔥", "emoji": True}],
        "linkedMessageID": "41",
    }
    msg = beeper.normalize_message(item, {})
    assert msg.kind == "image"
    assert msg.attachments == [{"type": "img", "mimeType": "image/jpeg"}]
    assert msg.reactions == [{"participant": "15550100000", "reaction": "🔥", "emoji": True}]
    assert msg.sender.native_id == "15550100001"
    assert msg.reply_to_source_id == "41"
    assert msg.sent_at.microsecond == 250000


def test_client_only_calls_collection_endpoints():
    client = beeper.Client("http://127.0.0.1:1", token="demo-token")
    with pytest.raises(ValueError):
        client.get("/v1/messages/send")
    with pytest.raises(ValueError):
        client.get("/v1/chats/abc/messages/123/react")
    with pytest.raises(beeper.BeeperAuthError):
        beeper.Client(token=None)


def test_instagram_rows_use_native_ids_and_classify_media():
    row = {
        "native_id": "mid.demo-001",
        "timestamp_ms": "1773511200123",
        "sender_id": "17840000000000001",
        "direction": "incoming",
        "speaker": "Maya Chen",
        "username": "@maya.makes.demo",
        "message": "sent 2 images",
        "reactions": "❤️ 😂",
        "reply_id": "SlideMessage:mid.demo-000",
        "replying to": "the quoted text",
    }
    msg = instagram.row_to_message(row, "1000000000000001", Counter())
    assert msg.source_message_id == "mid.demo-001"
    assert msg.time_precision == "exact" and msg.sent_at.isoformat().endswith(".123000+00:00")
    assert (msg.kind, msg.body, msg.metadata["summary"]) == ("image", "", "sent 2 images")
    assert msg.reply_to_source_id == "mid.demo-000"
    assert msg.reactions == [{"reaction": "❤️"}, {"reaction": "😂"}]
    assert msg.sender.handle == "maya.makes.demo"


def test_instagram_fingerprints_keep_repeated_messages_distinct():
    seen = Counter()
    rows = [{"speaker": "Theo", "message": "ok", "time": "Mar 14, 2026 6:00 PM"}] * 2
    keys = [instagram.row_to_message(r, "1000000000000001", seen).source_message_id for r in rows]
    assert keys[0] != keys[1] and keys[0].startswith("fp:")
    again = Counter()
    assert [instagram.row_to_message(r, "1000000000000001", again).source_message_id for r in rows] == keys


def test_instagram_csv_restores_defused_formulas():
    csv_text = '﻿speaker,username,message,reactions,time,replying to\r\n"Maya","@maya","\'=SUM(1)","","",""'
    batch = instagram.batch_from_csv(csv_text, "instagram-Maya Chen-1000000000000001.csv")
    assert batch.conversation.source_conversation_id == "1000000000000001"
    assert batch.conversation.title == "Maya Chen"
    assert batch.messages[0].body == "=SUM(1)"


def test_payload_format_is_checked():
    with pytest.raises(ValueError):
        instagram.batch_from_payload({"format": "something-else", "thread_id": "1", "messages": []})
    with pytest.raises(ValueError):
        instagram.batch_from_payload({"format": instagram.PAYLOAD_FORMAT, "thread_id": "../x", "messages": []})


def test_extra_migration_directories(tmp_path):
    (tmp_path / "1001_vectors.sql").write_text("SELECT 1;")
    versions = [v for v, _ in migration_files([tmp_path])]
    assert versions[0] == "0001_init" and versions[-1] == "1001_vectors"
    (tmp_path / "0001_init.sql").write_text("SELECT 1;")
    with pytest.raises(ValueError):
        migration_files([tmp_path])


def test_client_paginates_with_bearer_token_over_http():
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    seen = []

    class FakeDesktopAPI(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):  # noqa: N802
            seen.append((self.path, self.headers.get("Authorization")))
            if self.headers.get("Authorization") != "Bearer demo-token":
                self.send_response(401)
                self.end_headers()
                return
            if "cursor=c1" in self.path:
                body = {"items": [{"id": "chat-b"}], "hasMore": False, "oldestCursor": "c2"}
            else:
                body = {"items": [{"id": "chat-a"}], "hasMore": True, "oldestCursor": "c1"}
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data)

    httpd = HTTPServer(("127.0.0.1", 0), FakeDesktopAPI)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        assert [c["id"] for c in beeper.Client(url, "demo-token").chats()] == ["chat-a", "chat-b"]
        assert seen[1][0] == "/v1/chats?limit=200&cursor=c1&direction=before"
        with pytest.raises(beeper.BeeperAuthError):
            list(beeper.Client(url, "wrong-token").chats())
    finally:
        httpd.shutdown()
