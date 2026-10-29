import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { execFileSync } from "node:child_process";
import { JSDOM } from "jsdom";
import "../extension/core.js";
const E = globalThis.IGExport;
test("CSV preserves multiline, quotes, Unicode and defuses spreadsheet formulas", () => {
  const csv = E.csv([
    {
      speaker: "=1+1",
      message: 'a,"b"\n🦋',
      reactions: "❤️",
      time: "",
      "replying to": "quote",
    },
  ]);
  assert.ok(csv.includes('"\'=1+1"'));
  assert.ok(csv.includes('"a,""b""\n🦋"'));
  assert.ok(csv.startsWith("\ufeffspeaker,message,reactions,time,replying to"));
});
test("ZIP opens with a standard independent reader including Unicode filenames", async () => {
  const path = mkdtempSync(tmpdir() + "/igzip-") + "/test.zip";
  writeFileSync(
    path,
    Buffer.from(
      await E.zip({ "猫.csv": E.csv([]), "report.txt": "ok" }).arrayBuffer(),
    ),
  );
  const result = execFileSync("python3", [
    "-c",
    'import zipfile,sys; z=zipfile.ZipFile(sys.argv[1]); assert z.testzip() is None; assert z.read("report.txt")==b"ok"; assert "猫.csv" in z.namelist()',
    path,
  ]);
  assert.equal(result.length, 0);
});
function fixture() {
  const d = new JSDOM(
    '<html><body><div role="group"><button aria-label="React to message from Alice"></button><div role="button">original quote</div><div role="article" aria-roledescription="message" aria-labelledby="m1">Hello <img src="https://static.cdninstagram.com/emoji.php" alt="😊"></div><div role="button">❤️</div></div></body></html>',
    {
      url: "https://www.instagram.com/direct/t/1/",
      runScripts: "outside-only",
    },
  );
  d.window.eval(readFileSync("extension/content.js", "utf8"));
  return d.window;
}
test("DOM extraction separates speaker, quote and reaction and retains emoji", () => {
  const w = fixture(),
    r = w.IGExportDOM.read(w.IGExportDOM.articles()[0]);
  assert.equal(r.speaker, "Alice");
  assert.equal(r.message, "Hello 😊");
  assert.equal(r.reactions, "❤️");
  assert.equal(r["replying to"], "original quote");
});
test("post shares export their URL and image messages become a count", () => {
  const w = fixture(),
    a = w.IGExportDOM.articles()[0];
  a.innerHTML = '<a href="/p/abc/">caption<img src="photo.jpg"></a>';
  assert.equal(
    w.IGExportDOM.read(a).message,
    "https://www.instagram.com/p/abc/",
  );
  a.innerHTML = '<img src="1.jpg"><img src="2.jpg">';
  assert.equal(w.IGExportDOM.read(a).message, "sent 2 images");
});
test("date filters never interpret yearless labels as 2001", () => {
  const w = fixture();
  assert.ok(Number.isNaN(w.IGExportDOM.dateValue("Oct 27, 10:30 AM")));
  assert.ok(Number.isNaN(w.IGExportDOM.dateValue("4:33 PM")));
  assert.equal(
    new Date(w.IGExportDOM.dateValue("Oct 27, 2026 10:30 AM")).getFullYear(),
    2026,
  );
});
test("alternate emoji image URLs preserve surrounding message", () => {
  const w = fixture(),
    a = w.IGExportDOM.articles()[0];
  a.innerHTML =
    'Hello <img alt="😊" src="https://cdn.example/emoji.png"> there';
  assert.equal(w.IGExportDOM.read(a).message, "Hello 😊 there");
});
test("skin tone emoji preserve surrounding text", () => {
  const w = fixture(),
    a = w.IGExportDOM.articles()[0];
  a.innerHTML =
    'Hello <img alt="👍🏽" src="https://cdn.example/assets/123.png"> there';
  assert.equal(w.IGExportDOM.read(a).message, "Hello 👍🏽 there");
});
function scrollingFixture() {
  const w = fixture();
  const area = w.document.createElement("div");
  area.style.overflowY = "auto";
  Object.defineProperty(area, "clientHeight", { value: 500 });
  Object.defineProperty(area, "scrollTop", { get: () => 0, set: () => {} });
  w.document.body.prepend(area);
  area.append(w.document.querySelector("[role=group]"));
  return w;
}
test("navigation during a load rejects collection before exporting another chat", async () => {
  const w = scrollingFixture();
  w.setTimeout = (fn) => {
    w.history.pushState({}, "", "/direct/t/other/");
    queueMicrotask(fn);
  };
  await assert.rejects(
    w.IGExportDOM.collect("all", 10, "", null),
    /Conversation changed/,
  );
});
test("bounded collection returns chronological messages with a boundary report", async () => {
  const w = scrollingFixture();
  w.setTimeout = (fn) => queueMicrotask(fn);
  const r = await w.IGExportDOM.collect("all", 10, "", null);
  assert.equal(r.rows.length, 1);
  assert.equal(r.rows[0].message, "Hello 😊");
  assert.match(r.report, /scroll boundary/);
});
test("bulk ZIP preserves collected chats when a later folder is empty", async () => {
  const w = scrollingFixture();
  w.setTimeout = (fn) => queueMicrotask(fn);
  let files;
  w.IGExport = {
    csv: E.csv,
    zip: (f) => {
      files = f;
      return new w.Blob(["zip"]);
    },
  };
  w.URL.createObjectURL = () => "blob:test";
  w.URL.revokeObjectURL = () => {};
  w.HTMLAnchorElement.prototype.click = () => {};
  const nav = w.document.createElement("div");
  nav.ariaLabel = "Thread list";
  nav.setAttribute("aria-label", "Thread list");
  nav.style.overflowY = "auto";
  Object.defineProperty(nav, "clientHeight", { value: 500 });
  Object.defineProperty(nav, "scrollTop", { get: () => 0, set: () => {} });
  nav.innerHTML =
    '<div role="tab">Primary</div><div role="tab">General</div><div role="button">Alice · 1h</div>';
  w.document.body.prepend(nav);
  const button = nav.querySelector("[role=button]");
  button.getBoundingClientRect = () => ({ height: 72 });
  nav.querySelectorAll("[role=tab]")[1].onclick = () => button.remove();
  const root = w.document.querySelector("#ig-exporter").shadowRoot;
  root.getElementById("count").value = "";
  root.getElementById("bulk").click();
  for (let n = 0; n < 100 && !files; n++)
    await new Promise((r) => setImmediate(r));
  assert.ok(files["chat-0001.csv"]);
  assert.match(files["export-report.txt"], /General: no supported chat rows/);
});

test("message and date filters can be cleared after setting them", () => {
  const w = fixture(),
    root = w.document.querySelector("#ig-exporter").shadowRoot;
  root.getElementById("count").value = "42";
  root.getElementById("since").value = "2026-01-01";
  root.getElementById("count-clear").click();
  root.getElementById("since-clear").click();
  assert.equal(root.getElementById("count").value, "");
  assert.equal(root.getElementById("count").placeholder, "Unlimited");
  assert.equal(root.getElementById("since").value, "");
});
test("unlimited prior range keeps messages through the selected message", async () => {
  const w = scrollingFixture();
  w.setTimeout = (fn) => queueMicrotask(fn);
  const r = await w.IGExportDOM.collect("up", 0, "", {
    id: "m1",
    path: w.location.pathname,
  });
  assert.equal(r.rows.length, 1);
  assert.match(r.report, /scroll boundary/);
});

test("export controls follow direct routes across SPA navigation", async () => {
  const w = fixture(),
    host = w.document.getElementById("ig-exporter"),
    root = host.shadowRoot;
  assert.equal(host.style.display, "contents");
  root.getElementById("toggle").click();
  assert.equal(root.getElementById("panel").hidden, false);
  for (const path of ["/reels/example/", "/", "/directly"]) {
    w.history.pushState({}, "", path);
    w.document.body.append(w.document.createElement("span"));
    await Promise.resolve();
    assert.equal(host.style.display, "none");
    assert.equal(root.getElementById("panel").hidden, true);
  }
  w.history.pushState({}, "", "/direct/inbox/");
  w.dispatchEvent(new w.PopStateEvent("popstate"));
  assert.equal(host.style.display, "contents");
  assert.equal(
    root.getElementById("toggle").getAttribute("aria-expanded"),
    "false",
  );
});
