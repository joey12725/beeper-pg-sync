(() => {
  if (document.getElementById("ig-exporter")) return;
  const host = document.createElement("div");
  host.id = "ig-exporter";
  document.documentElement.append(host);
  const root = host.attachShadow({ mode: "open" });
  root.innerHTML = `<style>:host{all:initial}*{box-sizing:border-box}aside{position:fixed;right:20px;top:90px;width:min(310px,calc(100vw - 40px));max-height:calc(100vh - 110px);overflow:auto;padding:20px;border:1px solid #ddd;border-radius:16px;background:#fff;color:#20202b;box-shadow:0 12px 48px #0003;font:14px system-ui;z-index:2147483647}h2{font-size:18px;margin:0 0 8px}p{color:#646470;font-size:12px;line-height:1.5}label{display:block;margin:12px 0}select,input,button{font:inherit;border:1px solid #ccc;border-radius:8px;padding:9px;width:100%;background:white;color:#20202b}button{cursor:pointer;margin-top:7px}button.primary{background:#6554df;color:white;border:0}button:disabled{opacity:.45;cursor:default}.row{display:flex;gap:8px}output{display:block;margin-top:12px;font-size:12px;white-space:pre-wrap;max-height:160px;overflow:auto}summary{cursor:pointer;font-weight:600}#toggle{font:14px system-ui;position:fixed;right:20px;top:20px;width:auto;z-index:2147483647;background:#6554df;color:white}</style><button id="toggle">Export DMs</button><aside hidden><h2>Keep the conversation</h2><p>Local exports · no uploads · no zoom needed</p><label>Range<select id="range"><option value="down">Selected message → newest</option><option value="up">N messages ending at selection</option><option value="all">Entire conversation</option></select></label><button id="pick">Choose a starting message</button><label>Message count / maximum per chat<input id="count" type="number" min="1" max="100000" value="1000"></label><label>On or after (optional)<input id="since" type="date"></label><p>Date filters exclude messages with unknown dates. Displayed block times are used without slow hover gestures.</p><button class="primary" id="collect">Prepare export</button><div class="row"><button id="copy" disabled>Copy text</button><button id="md" disabled>Markdown</button><button id="csv" disabled>CSV</button></div><details><summary>All conversations</summary><p>Visits Primary, General and Requests when available. Keep this tab open. Opening chats may mark them read. ZIP includes a report of limits and failures.</p><button id="bulk">Export all chats → ZIP</button></details><button id="stop" disabled>Cancel</button><output aria-live="polite" id="status">Open a conversation to begin.</output></aside>`;
  const $ = (id) => root.getElementById(id),
    status = (s) => {
      $("status").textContent = s;
    };
  let selection = null,
    rows = [],
    busy = false,
    cancelled = false;
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const articles = () => [
    ...document.querySelectorAll(
      '[role="article"][aria-roledescription="message"]',
    ),
  ];
  const textWithEmoji = (e) => {
    const c = e.cloneNode(true);
    c.querySelectorAll("img").forEach((i) => i.replaceWith(i.alt || ""));
    return c.textContent.trim();
  };
  function read(a) {
    const g = a.closest('[role="group"]');
    const speaker =
      g
        ?.querySelector('[aria-label^="React to message from "]')
        ?.getAttribute("aria-label")
        .replace("React to message from ", "") || "Unknown";
    const links = [...a.querySelectorAll("a[href]")]
      .map((e) => e.href)
      .filter((h) => /^https:\/\/www.instagram.com\/(p|reel|reels)\//.test(h));
    const imgs = [...a.querySelectorAll("img")].filter(
      (i) =>
        !i.src.includes("/emoji") &&
        !/^(?:\p{Extended_Pictographic}|\p{Emoji_Modifier}|\p{Regional_Indicator}|[\u200d\ufe0f\u20e3\d#*])+$/u.test(
          i.alt || "",
        ) &&
        !i.alt.includes("profile"),
    );
    let message = links.length
      ? [...new Set(links)].join("\n")
      : textWithEmoji(a);
    if (!links.length && imgs.length)
      message = `sent ${imgs.length === 1 ? "an image" : imgs.length + " images"}`;
    if (!message)
      message = a.querySelector("video")
        ? "sent a video"
        : "[attachment unavailable]";
    let time =
      g?.querySelector("time")?.getAttribute("datetime") ||
      g?.querySelector("[title]")?.getAttribute("title") ||
      "";
    if (!time) {
      let area = g.parentElement;
      try {
        area = scroller(a);
      } catch {}
      const labels = [...area.querySelectorAll("span")]
        .filter(
          (e) =>
            !e.closest('[role="group"]') &&
            !e.closest('[role="article"]') &&
            e.compareDocumentPosition(a) & Node.DOCUMENT_POSITION_FOLLOWING,
        )
        .map((e) => e.textContent.trim())
        .filter(
          (t) =>
            t.length < 80 &&
            /\d/.test(t) &&
            /(am|pm|yesterday|today|mon|tue|wed|thu|fri|sat|sun|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)/i.test(
              t,
            ),
        );
      time = labels.at(-1) || "";
    }
    const replies = [...g.querySelectorAll('[role="button"]')]
      .filter(
        (e) =>
          !e.hasAttribute("aria-label") &&
          !a.contains(e) &&
          !(e.compareDocumentPosition(a) & Node.DOCUMENT_POSITION_PRECEDING),
      )
      .map(textWithEmoji)
      .filter(Boolean);
    const reactions = [...g.querySelectorAll('[role="button"]')]
      .filter(
        (e) =>
          !e.hasAttribute("aria-label") &&
          !a.contains(e) &&
          e.compareDocumentPosition(a) & Node.DOCUMENT_POSITION_PRECEDING,
      )
      .map(textWithEmoji)
      .filter(Boolean);
    return {
      id: a.getAttribute("aria-labelledby"),
      speaker,
      message,
      reactions: reactions.join(" "),
      time,
      "replying to": replies.join("\n"),
    };
  }
  const scroller = (e) => {
    for (let p = e?.parentElement; p; p = p.parentElement)
      if (
        /auto|scroll/.test(getComputedStyle(p).overflowY) &&
        p.clientHeight > 0
      )
        return p;
    throw Error("Cannot locate Instagram scroll area.");
  };
  function dateValue(t) {
    if (!t) return NaN;
    const now = new Date();
    if (/today|yesterday/i.test(t)) {
      const d = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      if (/yesterday/i.test(t)) d.setDate(d.getDate() - 1);
      return +d;
    }
    if (!/\b(?:19|20)\d{2}\b/.test(t)) return NaN;
    return Date.parse(t.replace(/\u202f/g, " "));
  }
  async function collect(mode, limit, since, anchor = selection) {
    const path = location.pathname;
    let initial = articles();
    if (!initial.length)
      throw Error(
        "No supported messages found. Open a chat; use English Instagram.",
      );
    if (mode !== "all" && (!anchor || anchor.path !== path))
      throw Error("Choose a message in this conversation first.");
    const s = scroller(initial[0]),
      store = new Map();
    let order = [];
    function capture(direction) {
      const batch = articles().map(read);
      const fresh = batch.filter((r) => !store.has(r.id));
      batch.forEach((r) => store.set(r.id, r));
      order =
        direction < 0
          ? [...fresh.map((r) => r.id), ...order]
          : [...order, ...fresh.map((r) => r.id)];
    }
    capture(1);
    const scroll = async (direction) => {
      let stable = 0;
      for (let n = 0; n < 20000; n++) {
        if (cancelled) throw Error("Cancelled.");
        if (location.pathname !== path)
          throw Error("Conversation changed; export stopped.");
        const old = order.length,
          top = s.scrollTop;
        s.scrollTop += direction * Math.max(100, s.clientHeight * 0.75);
        await wait(700);
        if (cancelled) throw Error("Cancelled.");
        if (location.pathname !== path)
          throw Error("Conversation changed; export stopped.");
        capture(direction);
        status(`Collecting ${order.length} messages…`);
        const at = order.indexOf(anchor?.id);
        if (direction < 0 && mode === "up" && at >= limit - 1)
          return "count limit";
        if (direction < 0 && mode === "all" && limit && order.length >= limit)
          return "count limit";
        if (order.length === old && Math.abs(top - s.scrollTop) < 2) stable++;
        else stable = 0;
        if (stable >= 5) return "scroll boundary (history may be unavailable)";
      }
      return "safety limit";
    };
    let reason = "";
    if (mode === "all") {
      await scroll(1);
      store.clear();
      order = [];
      capture(1);
      reason = await scroll(-1);
    } else reason = await scroll(mode === "up" ? -1 : 1);
    const at = order.indexOf(anchor?.id);
    if (mode !== "all" && at < 0)
      throw Error("Selected message was lost. Select it again.");
    let result = order.map((id) => store.get(id));
    if (mode === "down") result = result.slice(at);
    if (mode === "up")
      result = result.slice(Math.max(0, at - limit + 1), at + 1);
    if (mode === "all" && limit) result = result.slice(-limit);
    let excluded = 0;
    if (since) {
      const cutoff = +new Date(since + "T00:00:00");
      result = result.filter((r) => {
        const d = dateValue(r.time);
        if (!Number.isFinite(d)) excluded++;
        return d >= cutoff;
      });
    }
    if (location.pathname !== path)
      throw Error("Conversation changed; export stopped.");
    return {
      rows: result,
      report: `${result.length} messages; ${reason}. ${excluded} excluded with unknown dates. Completeness is not guaranteed by Instagram's UI.`,
    };
  }
  function download(data, name, type) {
    const u = URL.createObjectURL(
      data instanceof Blob ? data : new Blob([data], { type }),
    );
    const a = document.createElement("a");
    a.href = u;
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(u), 60000);
  }
  function options() {
    const n = Number($("count").value);
    if (!Number.isInteger(n) || n < 1 || n > 100000)
      throw Error("Count must be 1–100000.");
    return { n, since: $("since").value };
  }
  async function run(fn) {
    if (busy) return;
    busy = true;
    cancelled = false;
    ["collect", "bulk", "pick", "range", "count", "since"].forEach(
      (id) => ($(id).disabled = true),
    );
    $("stop").disabled = false;
    try {
      await fn();
    } catch (e) {
      status(e.message);
    } finally {
      busy = false;
      ["collect", "bulk", "pick", "range", "count", "since"].forEach(
        (id) => ($(id).disabled = false),
      );
      $("stop").disabled = true;
    }
  }
  $("toggle").onclick = () => {
    root.querySelector("aside").hidden = !root.querySelector("aside").hidden;
  };
  $("stop").onclick = () => {
    cancelled = true;
    status("Cancelling…");
  };
  $("pick").onclick = () => {
    status("Click a message bubble. Escape cancels selection.");
    const pick = (e) => {
      const a = e.target.closest('[role="article"]');
      if (!a) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      selection = {
        id: a.getAttribute("aria-labelledby"),
        path: location.pathname,
      };
      status("Selected: " + read(a).message.slice(0, 100));
      cleanup();
    };
    const key = (e) => {
      if (e.key === "Escape") {
        cleanup();
        status("Selection cancelled.");
      }
    };
    function cleanup() {
      document.removeEventListener("click", pick, true);
      document.removeEventListener("keydown", key, true);
    }
    document.addEventListener("click", pick, true);
    document.addEventListener("keydown", key, true);
  };
  $("collect").onclick = () =>
    run(async () => {
      rows = [];
      ["copy", "md", "csv"].forEach((id) => ($(id).disabled = true));
      const o = options(),
        r = await collect(
          $("range").value,
          $("range").value === "all" ? 0 : o.n,
          o.since,
        );
      rows = r.rows;
      status(r.report + " Ready to save.");
      ["copy", "md", "csv"].forEach((id) => ($(id).disabled = !rows.length));
    });
  $("copy").onclick = async () => {
    try {
      await navigator.clipboard.writeText(IGExport.text(rows));
      status(`Copied ${rows.length} messages.`);
    } catch {
      status("Clipboard blocked. Download Markdown instead.");
    }
  };
  $("md").onclick = () =>
    download(IGExport.markdown(rows), "instagram-chat.md", "text/markdown");
  $("csv").onclick = () =>
    download(IGExport.csv(rows), "instagram-chat.csv", "text/csv");
  $("bulk").onclick = () =>
    run(async () => {
      const { n, since } = options(),
        files = {},
        reports = [],
        seen = new Set();
      let number = 0;
      const nav = document.querySelector('[aria-label="Thread list"]');
      if (!nav) throw Error("Open the Instagram DM inbox first.");
      const tabs = [...nav.querySelectorAll('[role="tab"]')].map((e) =>
        e.textContent.trim(),
      );
      for (const tab of tabs.length ? tabs : ["Inbox"]) {
        if (cancelled) throw Error("Cancelled.");
        [...nav.querySelectorAll('[role="tab"]')]
          .find((e) => e.textContent.trim() === tab)
          ?.click();
        await wait(1000);
        try {
          const visited = new Set();
          let idle = 0;
          for (let page = 0; page < 10000 && idle < 5; page++) {
            if (cancelled) throw Error("Cancelled.");
            const candidates = [
              ...nav.querySelectorAll('[role="button"]'),
            ].filter(
              (e) =>
                e.getBoundingClientRect().height >= 60 &&
                e.textContent.includes("·"),
            );
            if (!candidates.length) {
              reports.push(
                `${tab}: no supported chat rows found; folder may be empty or unsupported.`,
              );
              break;
            }
            let fresh = 0;
            for (const button of candidates) {
              const key = button.textContent;
              if (visited.has(key)) continue;
              visited.add(key);
              fresh++;
              button.click();
              await wait(1200);
              const path = location.pathname;
              if (!/\/direct\/t\//.test(path)) {
                reports.push(`${tab}: could not open a chat`);
                continue;
              }
              if (seen.has(path)) continue;
              seen.add(path);
              try {
                const r = await collect("all", n, since, null);
                const filename = `chat-${String(++number).padStart(4, "0")}.csv`;
                files[filename] = IGExport.csv(r.rows);
                reports.push(`${filename} | ${path}: ${r.report}`);
              } catch (e) {
                if (cancelled) throw e;
                reports.push(`${path}: FAILED ${e.message}`);
              }
            }
            const s = scroller(
              candidates[0] || nav.querySelector('[role="button"]'),
            );
            const before = s.scrollTop;
            s.scrollTop += s.clientHeight * 0.8;
            await wait(900);
            idle = !fresh && Math.abs(s.scrollTop - before) < 2 ? idle + 1 : 0;
          }
          reports.push(
            `${tab}: inbox scan stopped; hidden or unsupported folders may be omitted.`,
          );
        } catch (e) {
          if (cancelled) throw e;
          reports.push(`${tab}: FAILED ${e.message}. Other folders preserved.`);
        }
      }
      files["export-report.txt"] = reports.join("\n");
      download(IGExport.zip(files), "instagram-chats.zip");
      status(
        `Saved ${number} chats. Read export-report.txt for coverage and failures.`,
      );
    });
  // Exposed only in the isolated content-script world for diagnostics/tests.
  globalThis.IGExportDOM = { read, articles, collect, dateValue };
})();
