"""Build a small collector-only add-on; never distribute the app's credentials."""
import gzip
import hashlib
import io
from pathlib import Path
import tarfile

root = Path(__file__).resolve().parents[1]
files = ["LICENSE", "README_COLLECTOR.md", "telemediation/__init__.py", "telemediation/collector.py",
         "scripts/install_collector.sh", "scripts/check_collector.py", "tests/test_collector.py"]
buffer = io.BytesIO()
with tarfile.open(fileobj=buffer, mode="w") as archive:
    for name in sorted(files):
        data = (root / name).read_bytes()
        info = tarfile.TarInfo("telemediation-convergent/" + name)
        info.size, info.mtime = len(data), 0
        info.mode = 0o755 if name.endswith(".sh") else 0o644
        archive.addfile(info, io.BytesIO(data))
out = root / "dist/tmc-collector-0.1.0.tar.gz"
out.parent.mkdir(exist_ok=True)
with out.open("wb") as raw:
    with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as stream:
        stream.write(buffer.getvalue())
digest = hashlib.sha256(out.read_bytes()).hexdigest()
Path(str(out) + ".sha256").write_text(digest + "  " + out.name + "\n")
print(out.name, digest)
