"""Read-only source fingerprints and ordinary concurrent-change detection."""

import hashlib
from pathlib import Path


def signature(path: Path) -> tuple[int, ...]:
    stat = path.stat()
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_source(path: Path, expected: str) -> tuple[int, ...]:
    if not path.is_absolute() or not path.is_file():
        raise ValueError("Source must be an existing absolute local file; relink if moved")
    before = signature(path)
    if file_digest(path) != expected:
        raise ValueError("Source fingerprint changed; ingest changed media as a new asset")
    if before != signature(path):
        raise ValueError("Source changed while hashing; retry with stable media")
    return before
