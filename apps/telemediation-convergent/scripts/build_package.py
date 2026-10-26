"""Reproducible source package; excludes databases, credentials and vendor material."""
import gzip
import hashlib
import io
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]
out = ROOT / "dist"
out.mkdir(exist_ok=True)
name = "telemediation-convergent-0.1.0.tar.gz"
files = [ROOT / f for f in ("run.py", "README.md", "README_COLLECTOR.md", "LICENSE", ".env.example")]
for folder in ("telemediation", "web", "scripts", "tests"):
    files.extend(p for p in (ROOT / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts)
buffer = io.BytesIO()
with tarfile.open(fileobj=buffer, mode="w") as archive:
    for path in sorted(files):
        content = path.read_bytes()
        info = tarfile.TarInfo("telemediation-convergent/" + path.relative_to(ROOT).as_posix())
        info.size = len(content)
        info.mtime = 0
        info.mode = 0o755 if path.suffix == ".sh" else 0o644
        archive.addfile(info, io.BytesIO(content))
with (out / name).open("wb") as raw:
    with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as zipped:
        zipped.write(buffer.getvalue())
digest = hashlib.sha256((out / name).read_bytes()).hexdigest()
(out / (name + ".sha256")).write_text(digest + "  " + name + "\n")
print(name, digest)
