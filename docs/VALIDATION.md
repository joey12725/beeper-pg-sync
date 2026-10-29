# Validation

Validated 2026-10-28/29 against a signed-in Instagram web session through T3's collaborative browser. No message content, account credentials, screenshots of private chats, or exported conversations are committed to this repository.

Observed live:

- English Instagram message articles and sidebar Primary/General/Requests selectors.
- Usernames, Unicode text, emoji reactions, quoted reply extraction.
- Displayed block labels including narrow-space AM/PM timestamps.
- Range collection ending at a selected message returned exactly 3 messages.
- Automatic scrolling and a bounded newest-history collection returned exactly 10 messages.
- Panel displayed on the live page in its isolated Shadow DOM.

Automated tests cover CSV escaping and formula protection, UTF-8 ZIP CRC/interoperability using Python zipfile, post URLs, image counts, emoji variants, date ambiguity, a navigation race, boundary reporting, and all-chat ZIP retention with an empty folder.

Two independent GPT-6.1-Sol review rounds were performed. Fixed navigation race, empty-folder ZIP loss, yearless date parsing, and emoji attachment misclassification (including skin tone variants).

Limits of this validation: the content script was injected into the collaborative browser for live testing, rather than installed through Chrome's extension manager. Clipboard/download behavior uses standard Chrome APIs and was covered by code inspection/fixtures, not a live Chrome installation. A full account-wide export was not run, and no claim of complete DM history is made. Native Windows/Linux Chrome was not available; the extension has no OS-specific runtime dependencies. CI runs the syntax, automated and packaging checks on Linux.
