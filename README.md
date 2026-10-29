# Instagram Chat Exporter

A small, local Chrome extension for keeping Instagram conversations in a useful format. Works in desktop Chrome on macOS, Windows, and Linux. No server, account registration, telemetry, or build step required to install.

## Install

1. Download the ZIP from this repository's **Releases** and extract it to a permanent folder (or clone this repository and use `extension/`).
2. Open `chrome://extensions`, enable **Developer mode**, then select **Load unpacked**.
3. Choose the extracted folder containing `manifest.json`.
4. Open or refresh [Instagram DMs](https://www.instagram.com/direct/inbox/). Sign in normally. Use Instagram in English.
5. Click the **Export** button. No zoom adjustment required.

Chrome requires unpacked extensions to stay in their installed folder. To update, replace those files and click Reload in `chrome://extensions`, then refresh Instagram.

## Export one conversation

Open a chat, then choose a range:

- **From selected message:** click **Select message**, then click a message bubble. Prepare collects that message and everything after it, scrolling automatically.
- **Before selected message:** select a message and enter a count. The selected message counts toward N. Click **Unlimited** (or empty the count field) to collect all earlier messages through the selection.
- **Entire conversation:** automatically walks to newest, then back through history. The count field does not limit this mode.

Click **Prepare export**, then **Copy text**, **Markdown**, or **CSV**. Copy uses `speaker: message`, in chronological order. Markdown includes available displayed times. CSV has exactly `speaker,message,reactions,time,replying to`; quotes, newlines, emoji and spreadsheet formula protection are supported. Speaker names are Instagram usernames when available. Escape cancels message selection.

Shared posts/reels become their Instagram URL when a link is exposed in the message. Images become `sent an image` or `sent 4 images`. Unavailable attachments are labeled; the extension does not download image/video files or retrieve expired media.

## Export all chats

Expand **Export all chats**, set the maximum messages per chat and optionally an **Since** date, then click **Download ZIP**. It sequentially visits discoverable chat rows in Primary, General, and Requests when those tabs exist. Each CSV has a numbered filename; `export-report.txt` maps filenames (in report order) to thread paths and records coverage, failures and stopping reasons.

Click **Unlimited** beside Message limit to remove the per-chat cap. Click **Clear** beside Since to remove the date filter. You can also empty either field directly.

Keep the tab open and avoid clicking around during collection. **Opening chats can mark them as read.** This uses Instagram's interface, so large exports take time. Cancel stops the operation; cancellation discards the current run. A failed chat/folder is reported while other collected chats are retained. Large exports are held in browser memory until download.

## Dates and completeness

This is a **best-effort interface export, not a guaranteed account archive**. Instagram virtualizes its UI and may withhold history. Five stable scroll checks stop a direction; a slow load can look like a boundary. The report explicitly identifies this uncertainty. Safety bounds prevent unbounded scanning. Identifiers are tied to the current rendered session; reloads and manual navigation interrupt collection.

Times come from exposed `time` elements or displayed block labels, without hovering every message. A block time can apply to multiple messages. Missing times stay blank. Date filters retain only messages with parseable dates that include a year, or explicit Today/Yesterday labels. Time-only and yearless labels are unknown and excluded, with a count in the report. Thus a date-filtered export can omit messages from the requested year; prefer Meta's account export when date completeness matters. The cap is applied to the newest N messages before date filtering.

Unsupported layouts/locales, nested request folders, hidden or encrypted history, deleted/unsent messages, and disappearing content can be missing. All-chat discovery currently uses the English sidebar's chat row structure; unsupported or empty folders are reported. Duplicate display names/previews can cause a row to be skipped. Review the report and spot-check important conversations. Instagram UI changes can require selector updates.

## Privacy

The extension reads only the Instagram page, scrolls it, opens conversations, writes the clipboard when you click Copy, and creates local downloads. It has no network calls, storage, external libraries, credentials, analytics, or message-sending code. Its only Chrome permission is `clipboardWrite`; content scripts are restricted to `https://www.instagram.com/*`. Your exported files contain private messages: store and share them accordingly.

## Development

Node.js 22+ and Python 3 are used for tests and packaging only.

```sh
npm ci
npm run check
npm test
npm run package
```

The installable ZIP is `dist/instagram-chat-exporter.zip`. `extension/core.js` implements CSV/text/Markdown and a standard uncompressed UTF-8 ZIP writer. `extension/content.js` owns the Shadow DOM panel and Instagram adapter. No bundler or runtime dependencies. Tests cover extraction, replies/reactions, media, Unicode, dates, CSV escaping and ZIP interoperability. See [validation notes](docs/VALIDATION.md) for live-test scope.

## Unattended agents

An agent could process a previously downloaded Meta account archive without a browser. A live personal-inbox exporter would still need an authenticated browser/session and is brittle; this extension intentionally requires an open tab. Meta's supported messaging API is aimed at professional accounts, not a general personal-history archive. See [research](docs/AGENTS.md).
