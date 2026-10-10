"""Skeptic repro: storage.upload keys blobs by {org}/{customer}/{filename}, so a same-name upload overwrites
the earlier file, and the basename of '..' crashes. Local backend, temp dir. Exit 0 only if both reproduce."""
import sys, os, tempfile, hashlib
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.pop("AMLKIT_GCS_BUCKET", None)
from amlkit import storage
storage.DOCS_DIR = Path(tempfile.mkdtemp())
storage._GCS_BUCKET = None
a, b = b"%PDF-1 first passport scan", b"%PDF-1 second, different customer document"
p1 = storage.upload(a, 1, 7, "scan.pdf"); h1 = hashlib.sha256(a).hexdigest()
p2 = storage.upload(b, 1, 7, "scan.pdf")
now = Path(p1).read_bytes()
overwritten = (p1 == p2 and hashlib.sha256(now).hexdigest() != h1)
print("same stored_path:", p1 == p2, "| first doc's recorded sha256 matches stored bytes:", hashlib.sha256(now).hexdigest() == h1)
crash = False
for name in (Path("..").name, ""):
    try: storage.upload(a, 1, 7, name); print(repr(name), "stored")
    except Exception as e: crash = True; print(repr(name), type(e).__name__)
sys.exit(0 if overwritten and crash else 1)
