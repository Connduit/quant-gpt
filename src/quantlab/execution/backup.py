"""Consistent SQLite backup/restore; never overwrite an active account."""

import hashlib
import json
import sqlite3
from pathlib import Path

from quantlab.paper.store import PaperStore


def backup(database, destination):
    database = Path(database).resolve()
    destination = Path(destination).resolve()
    if destination.exists() or not database.is_file():
        raise ValueError("Existing source and new backup destination required")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as source:
        with sqlite3.connect(destination) as target:
            source.backup(target)
    store = PaperStore(destination)
    try:
        store.verify()
    finally:
        store.close()
    manifest = {
        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "credentials_included": False,
        "authorization_key_included": False,
        "reconciliation_required_before_resume": True,
    }
    destination.with_suffix(destination.suffix + ".json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )
    return manifest


def restore(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    manifest = json.loads(source.with_suffix(source.suffix + ".json").read_text())
    if hashlib.sha256(source.read_bytes()).hexdigest() != manifest["sha256"]:
        raise ValueError("Backup checksum mismatch")
    return backup(source, destination)
