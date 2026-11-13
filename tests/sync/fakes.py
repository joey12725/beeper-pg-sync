"""An in-memory stand-in for the Beeper Desktop API. All data is fabricated."""

from datetime import UTC, datetime, timedelta

BASE = datetime(2026, 3, 14, 18, 0, tzinfo=UTC)

ACCOUNTS = [
    {
        "accountID": "instagramgo",
        "network": "Instagram",
        "bridge": {"id": "instagramgo", "type": "instagramgo", "provider": "cloud"},
        "status": "connected",
        "user": {"id": "5550001", "fullName": "Sam Rivera", "username": "sam.rivera.demo"},
    },
    {
        "accountID": "local-whatsapp_ba_demo",
        "network": "WhatsApp",
        "bridge": {"id": "local-whatsapp", "type": "whatsapp", "provider": "local"},
        "status": "connected",
        "user": {"id": "15550100000", "fullName": "Sam Rivera"},
    },
]


def stamp(minutes):
    return (BASE + timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")


def message(n, text, *, chat, account="instagramgo", sender="maya", outgoing=False, minutes=None, **extra):
    who = "5550001" if outgoing else {"maya": "5550002", "theo": "5550003"}[sender]
    return {
        "id": f"{chat}-{n}",
        "chatID": chat,
        "accountID": account,
        "senderID": f"@instagramgo_{who}:beeper.local",
        "senderName": "Sam Rivera" if outgoing else sender.title(),
        "timestamp": stamp(n if minutes is None else minutes),
        "sortKey": str(n),
        "type": "TEXT",
        "text": text,
        "isSender": outgoing,
        **extra,
    }


def chat(chat_id, title, *, account="instagramgo", kind="single", last=0):
    return {
        "id": chat_id,
        "accountID": account,
        "title": title,
        "type": kind,
        "lastActivity": stamp(last),
        "participants": {
            "items": [
                {"id": "@instagramgo_5550001:beeper.local", "fullName": "Sam Rivera", "isSelf": True},
                {"id": "@instagramgo_5550002:beeper.local", "fullName": "Maya Chen", "username": "maya.makes.demo"},
            ]
        },
    }


class FakeBeeper:
    def __init__(self, page_size=3):
        self.page_size = page_size
        self.chat_list = []
        self.messages = {}
        self.native = {}
        self.requests = 0

    def add_chat(self, chat_obj, messages, native_id=None):
        self.chat_list.append(chat_obj)
        self.messages[chat_obj["id"]] = sorted(messages, key=lambda m: m["timestamp"])
        if native_id:
            self.native[chat_obj["id"]] = native_id

    def accounts(self):
        return ACCOUNTS

    def chats(self):
        yield from self.chat_list

    def message_pages(self, chat_id, cursor=None):
        items = self.messages[chat_id]
        end = len(items) if cursor is None else int(cursor)
        while True:
            self.requests += 1
            start = max(0, end - self.page_size)
            page = items[start:end]
            yield {"items": page, "hasMore": start > 0, "oldestCursor": str(start), "newestCursor": str(end)}
            if start == 0:
                return
            end = start

    def native_chat_id(self, chat_id):
        return self.native.get(chat_id)
