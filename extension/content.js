(() => {
  if (document.getElementById("ig-exporter")) return;
  const host = document.createElement("div");
  host.id = "ig-exporter";
  document.documentElement.append(host);
  const root = host.attachShadow({ mode: "open" });
  const icon = (paths) =>
    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths}</svg>`;
  const arrow = icon('<path d="M12 3v12m-4-4 4 4 4-4M5 15v5h14v-5"/>');
  const copyIcon = icon(
    '<rect x="8" y="8" width="12" height="12" rx="3"/><path d="M15 8V4H4v11h4"/>',
  );
  const fileIcon = icon(
    '<path d="M14 3H6v18h12V7l-4-4Zm0 0v5h4M9 12h6m-6 4h6"/>',
  );
  const tableIcon = icon(
    '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M3 10h18M10 10v10"/>',
  );
  root.innerHTML = `
    <style>
      :host{all:initial;color-scheme:light dark}
      *,*::before,*::after{box-sizing:border-box}
      [hidden]{display:none!important}
      button,input,select{font:inherit}
      button{cursor:pointer}
      svg{width:20px;height:20px;flex-shrink:0}
      aside,#toggle{--bg:#fff;--ink:#202124;--muted:#777980;--line:#e9e9ec;--field:#f6f6f8;--hover:#ededf0;font:13px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:var(--ink)}
      aside{position:fixed;right:24px;top:88px;width:min(344px,calc(100vw - 32px));max-height:calc(100dvh - 108px);overflow:auto;z-index:2147483647;background:var(--bg);border:1px solid var(--line);border-radius:20px;box-shadow:0 16px 64px #0002,0 2px 8px #00000008}
      header{display:flex;align-items:center;gap:11px;padding:22px 22px 18px}
      .brand{display:grid;place-items:center;width:34px;height:34px;background:var(--field);border-radius:10px}
      h2{font-size:16px;font-weight:650;letter-spacing:-.4px;margin:0;flex:1}
      .icon-button{display:grid;place-items:center;width:30px;height:30px;padding:5px;background:none;border:0;border-radius:8px;color:var(--muted)}
      .icon-button:hover{background:var(--field);color:var(--ink)}
      .body{padding:0 22px 22px}
      label{display:block;font-size:12px;font-weight:550;color:var(--muted)}
      select,input{display:block;width:100%;min-width:0;height:44px;margin-top:8px;padding:0 12px;border:1px solid transparent;border-radius:10px;background:var(--field);color:var(--ink);font-size:13px;outline:none}
      select{padding-right:6px}
      input:focus,select:focus{border-color:var(--muted);background:var(--bg)}
      button:focus-visible,summary:focus-visible{outline:2px solid #818cf8;outline-offset:3px}
      .field-title{display:flex;align-items:center;justify-content:space-between;gap:4px;min-height:20px}
      .clear-filter{border:0;background:none;color:var(--muted);font-size:10px;padding:2px 0;text-decoration:underline;text-underline-offset:3px}
      .clear-filter:hover{color:var(--ink)}
      .fields{display:grid;grid-template-columns:1fr 1.25fr;gap:12px;margin:22px 0}
      button{transition:background .15s,color .15s,opacity .15s}
      .selection{display:flex;align-items:center;justify-content:center;gap:8px;width:100%;height:40px;margin-top:10px;border:1px solid var(--line);border-radius:10px;background:var(--bg);color:var(--ink);font-size:12px;font-weight:550}
      .selection svg{width:16px;height:16px;color:var(--muted)}
      .selection:hover{background:var(--field)}
      .primary{display:flex;align-items:center;justify-content:center;gap:9px;width:100%;height:46px;border:0;border-radius:11px;background:var(--ink);color:var(--bg);font-weight:600}
      .primary:hover{opacity:.85}
      .primary svg{width:17px;height:17px}
      .formats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:12px}
      .formats button{display:flex;flex-direction:column;align-items:center;gap:8px;padding:14px 3px 12px;border:1px solid var(--line);border-radius:11px;background:var(--bg);color:var(--ink);font-size:11px;font-weight:550}
      .formats button:hover:enabled{background:var(--field);border-color:var(--muted)}
      button:disabled{cursor:default;opacity:.35}
      details{margin-top:22px;border-top:1px solid var(--line)}
      summary{display:flex;align-items:center;gap:9px;padding:18px 0 0;cursor:pointer;list-style:none;font-size:12px;font-weight:550}
      summary::-webkit-details-marker{display:none}
      summary svg{width:17px;height:17px;color:var(--muted)}
      summary::after{content:'+';margin-left:auto;color:var(--muted);font-size:18px;font-weight:400;line-height:1}
      details[open] summary::after{content:'−'}
      #bulk{margin-top:14px}
      #stop{width:100%;margin-top:12px;border:0;border-radius:8px;background:var(--field);color:var(--ink);padding:9px}
      #stop:disabled{display:none}
      output{display:block;margin-top:16px;max-height:100px;overflow:auto;color:var(--muted);font-size:11px;line-height:1.6;overflow-wrap:anywhere}
      output:empty{display:none}
      #toggle{position:fixed;right:168px;top:24px;z-index:2147483647;display:flex;align-items:center;gap:8px;padding:10px 15px;border:1px solid var(--line);border-radius:12px;background:var(--bg);box-shadow:0 3px 16px #0001;font-size:12px;font-weight:600}
      #toggle svg{width:16px;height:16px}
      #toggle:hover{background:var(--field)}
      @media(prefers-color-scheme:dark){aside,#toggle{--bg:#1c1c20;--ink:#f2f2f4;--muted:#9999a3;--line:#333338;--field:#27272c;--hover:#34343b}aside{box-shadow:0 16px 64px #0006}}
      @media(prefers-reduced-motion:reduce){button{transition:none}}
    </style>
    <button id="toggle" aria-expanded="false" aria-controls="panel">${arrow} Export</button>
    <aside id="panel" aria-label="Chat export" hidden>
      <header><span class="brand">${arrow}</span><h2>Chat export</h2><button id="close" class="icon-button" aria-label="Close export panel">${icon('<path d="m6 6 12 12M6 18 18 6"/>')}</button></header>
      <div class="body">
        <label>Range<select id="range"><option value="down">From selected message</option><option value="up">Before selected message</option><option value="all">Entire conversation</option></select></label>
        <button id="pick" class="selection">${icon('<circle cx="12" cy="12" r="6"/><path d="M12 2v4m0 12v4M2 12h4m12 0h4"/>')} Select message</button>
        <div class="fields">
          <label><span class="field-title">Message limit<button id="count-clear" class="clear-filter" type="button" aria-label="Disable message limit">Unlimited</button></span><input id="count" type="number" min="1" max="100000" value="1000" placeholder="Unlimited" aria-label="Message count or maximum per chat"></label>
          <label><span class="field-title">Since<button id="since-clear" class="clear-filter" type="button" aria-label="Clear since date">Clear</button></span><input id="since" type="date" aria-label="On or after date" title="Messages with unknown dates are excluded"></label>
        </div>
        <button class="primary" id="collect">Prepare export ${icon('<path d="M5 12h14m-5-5 5 5-5 5"/>')}</button>
        <div class="formats"><button id="copy" disabled>${copyIcon} Copy text</button><button id="md" disabled>${fileIcon} Markdown</button><button id="csv" disabled>${tableIcon} CSV</button></div>
        <details><summary>${icon('<rect x="3" y="3" width="14" height="14" rx="3"/><path d="M8 21h10a3 3 0 0 0 3-3V8"/>')} Export all chats</summary><button id="bulk" class="selection" title="Opening chats may mark them read">${arrow} Download ZIP</button></details>
        <button id="stop" disabled>Cancel export</button><output aria-live="polite" id="status"></output>
      </div>
    </aside>`;
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
        if (direction < 0 && mode === "up" && limit && at >= limit - 1)
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
      result = result.slice(limit ? Math.max(0, at - limit + 1) : 0, at + 1);
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
    const value = $("count").value.trim();
    const n = value === "" ? 0 : Number(value);
    if (value !== "" && (!Number.isInteger(n) || n < 1 || n > 100000))
      throw Error("Count must be 1–100000, or leave it blank for unlimited.");
    return { n, since: $("since").value };
  }
  async function run(fn) {
    if (busy) return;
    busy = true;
    cancelled = false;
    [
      "collect",
      "bulk",
      "pick",
      "range",
      "count",
      "since",
      "count-clear",
      "since-clear",
    ].forEach((id) => ($(id).disabled = true));
    $("stop").disabled = false;
    try {
      await fn();
    } catch (e) {
      status(e.message);
    } finally {
      busy = false;
      [
        "collect",
        "bulk",
        "pick",
        "range",
        "count",
        "since",
        "count-clear",
        "since-clear",
      ].forEach((id) => ($(id).disabled = false));
      $("stop").disabled = true;
    }
  }
  $("count-clear").onclick = () => {
    $("count").value = "";
  };
  $("since-clear").onclick = () => {
    $("since").value = "";
  };
  function setOpen(open) {
    $("panel").hidden = !open;
    $("toggle").setAttribute("aria-expanded", String(open));
  }
  // Content scripts stay loaded as Instagram navigates between routes.
  let route = null;
  function syncRoute() {
    if (route === location.pathname) return;
    route = location.pathname;
    const inDirect = /^\/direct(?:\/|$)/.test(route);
    host.style.setProperty(
      "display",
      inDirect ? "contents" : "none",
      "important",
    );
    if (!inDirect) setOpen(false);
  }
  new MutationObserver(syncRoute).observe(document.documentElement, {
    childList: true,
    subtree: true,
  });
  window.addEventListener("popstate", syncRoute);
  window.navigation?.addEventListener("currententrychange", syncRoute);
  syncRoute();
  $("toggle").onclick = () => setOpen($("panel").hidden);
  $("close").onclick = () => {
    setOpen(false);
    $("toggle").focus();
  };
  root.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      setOpen(false);
      $("toggle").focus();
    }
  });
  $("range").onchange = () => {
    $("pick").hidden = $("range").value === "all";
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
