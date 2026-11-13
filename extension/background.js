/* Service worker: forwards prepared chats to a beeper-pg-sync ingest server.
   The server URL and token live in chrome.storage.local (extension options). */
const DEFAULTS = { endpoint: "http://127.0.0.1:8765", token: "" };

async function settings() {
  return {
    ...DEFAULTS,
    ...(await chrome.storage.local.get(["endpoint", "token"])),
  };
}

async function call(path, init = {}) {
  const { endpoint, token } = await settings();
  if (!token)
    throw Error("Add your sync server token in the extension options.");
  const response = await fetch(endpoint.replace(/\/+$/, "") + path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok)
    throw Error(data.error || `Sync server returned HTTP ${response.status}`);
  return data;
}

function ingest(payloads) {
  const body = payloads.length === 1 ? payloads[0] : { batches: payloads };
  return call("/v1/ingest/instagram", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

chrome.runtime.onMessage.addListener((message, _sender, reply) => {
  const work =
    message?.type === "sync:ingest"
      ? ingest(message.payloads)
      : message?.type === "sync:status"
        ? call("/v1/status")
        : null;
  if (!work) return false;
  work.then(
    (result) => reply({ ok: true, result }),
    (error) => reply({ ok: false, error: error.message }),
  );
  return true; // keep the channel open for the async reply
});
