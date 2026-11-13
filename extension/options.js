const $ = (id) => document.getElementById(id);

chrome.storage.local.get(["endpoint", "token"]).then((saved) => {
  $("endpoint").value = saved.endpoint || "http://127.0.0.1:8765";
  $("token").value = saved.token || "";
});

$("save").onclick = async () => {
  await chrome.storage.local.set({
    endpoint: $("endpoint").value.trim(),
    token: $("token").value.trim(),
  });
  $("status").textContent = "Saved.";
};

$("test").onclick = async () => {
  await $("save").onclick();
  const reply = await chrome.runtime.sendMessage({ type: "sync:status" });
  if (!reply?.ok) {
    $("status").textContent = reply?.error || "No answer from the server.";
    return;
  }
  const total = reply.result.networks.reduce(
    (sum, n) => sum + Number(n.messages),
    0,
  );
  $("status").textContent =
    `Connected. ${total.toLocaleString()} messages stored.`;
};
