"""Single-writer durable journal with atomic materialized state and hash checks."""

import fcntl
import json
import sqlite3
from pathlib import Path

from quantlab.discovery.common import fingerprint


class PaperStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = self.path.with_suffix(".lock").open("a")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close()
            raise ValueError("Paper account already has a writer") from None
        self.db = sqlite3.connect(self.path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS journal(
                number INTEGER PRIMARY KEY, identity TEXT UNIQUE, kind TEXT,
                payload TEXT, previous TEXT, checksum TEXT, state_checksum TEXT);
            CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT);
            CREATE TABLE IF NOT EXISTS controls(
                id INTEGER PRIMARY KEY, payload TEXT, applied INTEGER DEFAULT 0);
        """)
        try:
            self.verify()
        except BaseException:
            self.close()
            raise

    def verify(self):
        if self.db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Paper database integrity failure")
        previous = ""
        count = 0
        state_checksum = None
        for number, identity, kind, payload, prior, checksum, state_checksum in self.db.execute(
            "SELECT * FROM journal ORDER BY number"
        ):
            count += 1
            if (
                number != count
                or prior != previous
                or checksum
                != fingerprint([identity, kind, json.loads(payload), prior, state_checksum])
            ):
                raise ValueError("Paper audit journal integrity failure")
            previous = checksum
        row = self.db.execute("SELECT payload FROM state WHERE id=1").fetchone()
        if bool(row) != bool(count) or (row and fingerprint(json.loads(row[0])) != state_checksum):
            raise ValueError("Paper materialized state does not reconcile to journal")

    def load(self):
        row = self.db.execute("SELECT payload FROM state WHERE id=1").fetchone()
        return json.loads(row[0]) if row else None

    def contains(self, identity):
        return (
            self.db.execute("SELECT 1 FROM journal WHERE identity=?", (identity,)).fetchone()
            is not None
        )

    def commit(self, identity, kind, payload, state):
        previous = self.db.execute(
            "SELECT checksum FROM journal ORDER BY number DESC LIMIT 1"
        ).fetchone()
        previous = previous[0] if previous else ""
        state_checksum = fingerprint(state)
        checksum = fingerprint([identity, kind, payload, previous, state_checksum])
        with self.db:
            self.db.execute(
                (
                    "INSERT INTO "
                    "journal(identity,kind,payload,previous,checksum,state_checksum) "
                    "VALUES(?,?,?,?,?,?)"
                ),
                (identity, kind, json.dumps(payload), previous, checksum, state_checksum),
            )
            self.db.execute("INSERT OR REPLACE INTO state VALUES(1,?)", (json.dumps(state),))

    def close(self):
        if self.lock.closed:
            return
        self.db.close()
        fcntl.flock(self.lock, fcntl.LOCK_UN)
        self.lock.close()

    @staticmethod
    def queue(path, control):
        with sqlite3.connect(path) as db:
            db.execute("INSERT INTO controls(payload) VALUES(?)", (json.dumps(control),))
