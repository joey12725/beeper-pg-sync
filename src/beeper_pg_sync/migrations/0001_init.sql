-- beeper-pg-sync core schema.
--
-- Model: a conversation lives on one network (instagram, whatsapp, discord...).
-- Sources (beeper, instagram-extension, ...) observe conversations and
-- messages; every observation is recorded in *_sources tables so the same
-- message seen by two sources collapses into one row in `messages`.
--
-- `messages.id` is stable and never reassigned. Downstream tooling (search
-- indexes, embeddings, analytics) should key on it and watch
-- `messages.content_updated_at` to know when a row's text changed.

CREATE TABLE accounts (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source            text NOT NULL,
    source_account_id text NOT NULL,
    network           text NOT NULL,
    user_native_id    text,
    display_name      text,
    status            text,
    metadata          jsonb NOT NULL DEFAULT '{}',
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source, source_account_id)
);

CREATE TABLE conversations (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    network     text NOT NULL,
    native_id   text,
    account_id  bigint REFERENCES accounts (id) ON DELETE SET NULL,
    title       text,
    kind        text NOT NULL DEFAULT 'unknown'
                CHECK (kind IN ('dm', 'group', 'channel', 'thread', 'unknown')),
    metadata    jsonb NOT NULL DEFAULT '{}',
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

-- A network-native thread ID (when a source knows it) identifies one conversation.
CREATE UNIQUE INDEX conversations_network_native_id
    ON conversations (network, native_id) WHERE native_id IS NOT NULL;

CREATE TABLE conversation_sources (
    source                 text NOT NULL,
    source_conversation_id text NOT NULL,
    conversation_id        bigint NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    linked_by              text NOT NULL DEFAULT 'source'
                           CHECK (linked_by IN ('source', 'native_id', 'overlap', 'manual')),
    created_at             timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source, source_conversation_id)
);

CREATE INDEX conversation_sources_conversation ON conversation_sources (conversation_id);

CREATE TABLE participants (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    network      text NOT NULL,
    native_id    text NOT NULL,
    display_name text,
    handle       text,
    is_self      boolean NOT NULL DEFAULT false,
    metadata     jsonb NOT NULL DEFAULT '{}',
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (network, native_id)
);

CREATE TABLE messages (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversation_id     bigint NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    source              text NOT NULL,
    sender_id           bigint REFERENCES participants (id) ON DELETE SET NULL,
    sender_name         text,
    direction           text NOT NULL DEFAULT 'unknown'
                        CHECK (direction IN ('incoming', 'outgoing', 'unknown')),
    sent_at             timestamptz,
    time_precision      text NOT NULL DEFAULT 'exact'
                        CHECK (time_precision IN ('exact', 'approximate', 'unknown')),
    kind                text NOT NULL DEFAULT 'text',
    body                text NOT NULL DEFAULT '',
    edited_at           timestamptz,
    deleted             boolean NOT NULL DEFAULT false,
    reply_to_message_id bigint REFERENCES messages (id) ON DELETE SET NULL,
    attachments         jsonb NOT NULL DEFAULT '[]',
    reactions           jsonb NOT NULL DEFAULT '[]',
    metadata            jsonb NOT NULL DEFAULT '{}',
    content_updated_at  timestamptz NOT NULL DEFAULT now(),
    first_seen_at       timestamptz NOT NULL DEFAULT now(),
    last_seen_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX messages_conversation_sent_at ON messages (conversation_id, sent_at);
CREATE INDEX messages_sent_at ON messages (sent_at);
CREATE INDEX messages_content_updated_at ON messages (content_updated_at);
CREATE INDEX messages_body_search ON messages USING gin (to_tsvector('simple', body));

CREATE TABLE message_sources (
    source                 text NOT NULL,
    source_conversation_id text NOT NULL,
    source_message_id      text NOT NULL,
    message_id             bigint NOT NULL REFERENCES messages (id) ON DELETE CASCADE,
    reply_to_source_id     text,
    raw                    jsonb NOT NULL DEFAULT '{}',
    first_seen_at          timestamptz NOT NULL DEFAULT now(),
    last_seen_at           timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source, source_conversation_id, source_message_id)
);

CREATE INDEX message_sources_message ON message_sources (message_id);

-- Per-source, per-scope resumable sync position (one row per Beeper chat, etc.).
CREATE TABLE sync_state (
    source          text NOT NULL,
    scope           text NOT NULL,
    status          text NOT NULL DEFAULT 'pending',
    cursor          text,
    frontier        timestamptz,
    detail          jsonb NOT NULL DEFAULT '{}',
    last_success_at timestamptz,
    updated_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source, scope)
);

CREATE TABLE sync_runs (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source      text NOT NULL,
    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    status      text NOT NULL DEFAULT 'running'
                CHECK (status IN ('running', 'ok', 'partial', 'failed')),
    stats       jsonb NOT NULL DEFAULT '{}',
    error       text
);

-- Bump content_updated_at only when the searchable content actually changes.
CREATE FUNCTION messages_touch_content() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.body IS DISTINCT FROM OLD.body
       OR NEW.deleted IS DISTINCT FROM OLD.deleted
       OR NEW.edited_at IS DISTINCT FROM OLD.edited_at THEN
        NEW.content_updated_at := now();
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER messages_touch_content
    BEFORE UPDATE ON messages
    FOR EACH ROW EXECUTE FUNCTION messages_touch_content();

-- Flat, human-friendly view for ad-hoc SQL.
CREATE VIEW message_timeline AS
SELECT m.id,
       m.conversation_id,
       c.network,
       m.source,
       c.title AS conversation,
       c.kind AS conversation_kind,
       COALESCE(p.display_name, m.sender_name) AS sender,
       p.handle AS sender_handle,
       m.direction,
       m.sent_at,
       m.time_precision,
       m.kind,
       m.body,
       m.edited_at,
       m.deleted,
       m.reply_to_message_id,
       m.attachments,
       m.reactions,
       m.content_updated_at
FROM messages m
JOIN conversations c ON c.id = m.conversation_id
LEFT JOIN participants p ON p.id = m.sender_id;
