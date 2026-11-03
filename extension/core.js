/* Shared export functions; no network or storage. */
globalThis.IGExport = (() => {
  const columns = [
    "speaker",
    "username",
    "message",
    "reactions",
    "time",
    "replying to",
    "native_id",
    "sender_id",
    "direction",
    "reply_id",
    "timestamp_ms",
    "time_precision",
  ];
  const cell = (v) =>
    '"' +
    String(v ?? "")
      .replace(/^[=+@\-\t\r]/, "'$&")
      .replaceAll('"', '""') +
    '"';
  function csv(rows) {
    return (
      "\ufeff" +
      [
        columns.join(","),
        ...rows.map((r) => columns.map((k) => cell(r[k])).join(",")),
      ].join("\r\n")
    );
  }
  function filename(title, thread, extension) {
    const clean = (value, max) =>
      Array.from(
        String(value || "")
          .normalize("NFC")
          .replace(/[<>:"/\\|?*\x00-\x1f\x7f]/g, "-")
          .replace(/\s+/g, " ")
          .trim()
          .replace(/[. ]+$/g, ""),
      )
        .slice(0, max)
        .join("");
    return `instagram-${clean(title, 80) || "chat"}-${clean(thread, 40) || "export"}.${extension}`;
  }
  function text(rows) {
    return rows.map((r) => `${r.speaker}: ${r.message}`).join("\n");
  }
  function markdown(rows) {
    return rows
      .map((r) =>
        `${r.time ? "[" + r.time + "] " : ""}${r.speaker}: ${r.message}`.replace(
          /([\\`*_{}\[\]<>#])/g,
          "\\$1",
        ),
      )
      .join("\n\n");
  }
  const enc = new TextEncoder();
  function crc32(b) {
    let c = 0xffffffff;
    for (const v of b) {
      c ^= v;
      for (let n = 0; n < 8; n++) c = (c >>> 1) ^ (c & 1 ? 0xedb88320 : 0);
    }
    return (c ^ 0xffffffff) >>> 0;
  }
  function zip(files) {
    const chunks = [],
      directory = [];
    let offset = 0;
    const header = (size) => {
      const b = new Uint8Array(size);
      return [b, new DataView(b.buffer)];
    };
    for (const [name, content] of Object.entries(files)) {
      const n = enc.encode(name),
        b = enc.encode(content),
        crc = crc32(b);
      const [h, v] = header(30);
      v.setUint32(0, 0x04034b50, true);
      v.setUint16(4, 20, true);
      v.setUint16(6, 0x800, true);
      v.setUint32(14, crc, true);
      v.setUint32(18, b.length, true);
      v.setUint32(22, b.length, true);
      v.setUint16(26, n.length, true);
      chunks.push(h, n, b);
      const [d, w] = header(46);
      w.setUint32(0, 0x02014b50, true);
      w.setUint16(4, 20, true);
      w.setUint16(6, 20, true);
      w.setUint16(8, 0x800, true);
      w.setUint32(16, crc, true);
      w.setUint32(20, b.length, true);
      w.setUint32(24, b.length, true);
      w.setUint16(28, n.length, true);
      w.setUint32(42, offset, true);
      directory.push(d, n);
      offset += h.length + n.length + b.length;
    }
    const length = directory.reduce((s, b) => s + b.length, 0),
      [end, v] = header(22);
    v.setUint32(0, 0x06054b50, true);
    v.setUint16(8, Object.keys(files).length, true);
    v.setUint16(10, Object.keys(files).length, true);
    v.setUint32(12, length, true);
    v.setUint32(16, offset, true);
    return new Blob([...chunks, ...directory, end], {
      type: "application/zip",
    });
  }
  return { csv, text, markdown, zip, filename };
})();
