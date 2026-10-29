from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
root = Path(__file__).resolve().parent.parent
out = root / 'dist'
out.mkdir(exist_ok=True)
with ZipFile(out / 'instagram-chat-exporter.zip', 'w', ZIP_DEFLATED) as z:
    for f in sorted((root / 'extension').iterdir()):
        z.write(f, f.name)
print(out / 'instagram-chat-exporter.zip')
