"""Zip the Chrome extension for a GitHub release (load unpacked from the ZIP's folder)."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

root = Path(__file__).resolve().parent.parent
out = root / "dist"
out.mkdir(exist_ok=True)
target = out / "instagram-chat-exporter.zip"
with ZipFile(target, "w", ZIP_DEFLATED) as archive:
    for path in sorted((root / "extension").iterdir()):
        if path.is_file() and not path.name.startswith("."):
            archive.write(path, path.name)
print(target)
