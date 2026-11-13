/* Runs in Chrome's MAIN world. Copy only message metadata, never React owners or sessions. */
(() => {
  function read(article) {
    const key = Object.keys(article).find((k) => k.startsWith("__reactFiber"));
    for (
      let f = article[key], depth = 0;
      f && depth < 50;
      f = f.return, depth++
    ) {
      const p = f.memoizedProps || {},
        m = p.slideMessageRef;
      if (
        !m ||
        typeof m.__id !== "string" ||
        !m.__id.startsWith("SlideMessage:") ||
        !/^\d{13}$/.test(String(m.timestamp_ms))
      )
        continue;
      return {
        native_id: m.__id.slice(13),
        time: new Date(Number(m.timestamp_ms)).toISOString(),
        timestamp_ms: String(m.timestamp_ms),
        sender_id: m.sender_fbid == null ? "" : String(m.sender_fbid),
        direction: p.outgoing ? "outgoing" : "incoming",
        reply_id: m.replied_to_message?.__id || "",
      };
    }
    return null;
  }
  const update = () => {
    for (const a of document.querySelectorAll('[role="article"]')) {
      const m = read(a);
      if (m) a.setAttribute("data-ig-export-native", JSON.stringify(m));
      else a.removeAttribute("data-ig-export-native");
    }
  };
  const observer = new MutationObserver(update);
  observer.observe(document.body, {
    subtree: true,
    childList: true,
    characterData: true,
  });
  document.addEventListener("ig-export-native-refresh", update);
  update();
})();
