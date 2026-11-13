"""Plain-text extraction and comparison keys. Never evaluates HTML or loads URLs."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

_TAG = re.compile(r"</?(?:p|br|img|a|strong|em|code|pre|span|b|i|s|del|blockquote|ul|ol|li)\b", re.I)
_BLOCK = ("p", "pre", "blockquote", "li")


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        if self.skip:
            return
        if tag in (*_BLOCK, "br"):
            self.out.append("\n")
        if tag == "img":
            self.out.append(dict(attrs).get("alt") or "")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1
        elif not self.skip and tag in _BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def plain(value: object) -> str:
    """Rich text (HTML fragments from bridges) to readable plain text."""
    text = str(value or "")
    if not _TAG.search(text):
        return html.unescape(text)
    parser = _Text()
    parser.feed(text)
    parser.close()
    return re.sub(r"\n[ \t]*\n[\n \t]*", "\n\n", "".join(parser.out)).strip()


def comparable(value: object) -> str:
    """A formatting-insensitive key for matching one message seen by two sources."""
    text = plain(value)
    text = re.sub(r"```[^\n]*\n", "", text).replace("```", "")
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"<a?:([A-Za-z0-9_]+):[0-9]+>", r":\1:", text)
    text = re.sub(r"<(https?://[^>]+)>", r"\1", text)
    text = text.replace("**", "").replace("__", "").replace("`", "")
    return " ".join(text.split()).casefold()
