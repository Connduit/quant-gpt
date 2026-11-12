"""One-use holdout authorization ledger. Routine validation receives development data only."""

import hashlib
import json
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from quantlab.discovery.common import fingerprint


class HoldoutVault:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS holdouts (
                  id TEXT PRIMARY KEY, manifest TEXT NOT NULL, state TEXT NOT NULL,
                  token_hash TEXT, actor TEXT, reason TEXT, result TEXT);
                CREATE TABLE IF NOT EXISTS events (
                  id INTEGER PRIMARY KEY, holdout_id TEXT, at TEXT, event TEXT, detail TEXT);
            """)

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        try:
            c.execute("BEGIN IMMEDIATE")
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def _event(self, c, identifier, event, detail=""):
        c.execute(
            "INSERT INTO events(holdout_id,at,event,detail) VALUES (?,?,?,?)",
            (identifier, datetime.now(UTC).isoformat(), event, detail),
        )

    def register(self, manifest):
        if set(manifest) != {"sources", "start", "end", "purpose"}:
            raise ValueError("Manifest requires source snapshot identities, start/end and purpose")
        if not manifest["sources"] or manifest["start"] > manifest["end"]:
            raise ValueError("Invalid holdout manifest")
        # Purpose is not part of identity: renaming a consumed holdout cannot refresh evidence.
        identifier = fingerprint({k: v for k, v in manifest.items() if k != "purpose"})
        encoded = json.dumps(manifest, sort_keys=True)
        with self.connect() as c:
            old = c.execute("SELECT manifest FROM holdouts WHERE id=?", (identifier,)).fetchone()
            if not old:
                for previous in c.execute("SELECT manifest FROM holdouts"):
                    other = json.loads(previous["manifest"])
                    shared = set(other["sources"].values()) & set(manifest["sources"].values())
                    overlap = (
                        other["start"] <= manifest["end"] and manifest["start"] <= other["end"]
                    )
                    if shared and overlap:
                        raise ValueError(
                            "Overlapping holdout already registered; reuse original manifest"
                        )
            if old and old["manifest"] != encoded:
                raise ValueError("Holdout manifest is immutable")
            if not old:
                c.execute(
                    "INSERT INTO holdouts VALUES (?,?,'SEALED',NULL,NULL,NULL,NULL)",
                    (identifier, encoded),
                )
                self._event(c, identifier, "REGISTERED")
        return identifier

    def authorize(self, identifier, *, actor, reason, confirmation):
        if (
            confirmation != "AUTHORIZE_ONE_FINAL_EVALUATION"
            or not actor.strip()
            or not reason.strip()
        ):
            raise PermissionError(
                "Explicit final-evaluation authorization with actor/reason required"
            )
        token = secrets.token_urlsafe(32)
        with self.connect() as c:
            row = c.execute("SELECT state FROM holdouts WHERE id=?", (identifier,)).fetchone()
            if not row or row["state"] != "SEALED":
                raise PermissionError("Holdout already authorized or consumed")
            c.execute(
                "UPDATE holdouts SET state='AUTHORIZED',token_hash=?,actor=?,reason=? WHERE id=?",
                (hashlib.sha256(token.encode()).hexdigest(), actor, reason, identifier),
            )
            self._event(c, identifier, "AUTHORIZED", f"{actor}: {reason}")
        return token

    def evaluate(self, identifier, token, evaluator):
        with self.connect() as c:
            row = c.execute("SELECT * FROM holdouts WHERE id=?", (identifier,)).fetchone()
            if (
                not row
                or row["state"] != "AUTHORIZED"
                or not secrets.compare_digest(
                    row["token_hash"], hashlib.sha256(token.encode()).hexdigest()
                )
            ):
                raise PermissionError("No valid one-use holdout authorization")
            # Consume before any read/evaluation. Crash or failure cannot make it fresh again.
            c.execute(
                "UPDATE holdouts SET state='CONSUMED',token_hash=NULL WHERE id=?", (identifier,)
            )
            self._event(c, identifier, "EVALUATION_STARTED_CONSUMED")
            manifest = json.loads(row["manifest"])
        try:
            result = evaluator(manifest)
            encoded = json.dumps(result, sort_keys=True, allow_nan=False)
        except BaseException:
            with self.connect() as c:
                self._event(c, identifier, "EVALUATION_FAILED_CONSUMED")
            raise
        with self.connect() as c:
            c.execute("UPDATE holdouts SET result=? WHERE id=?", (encoded, identifier))
            self._event(c, identifier, "EVALUATION_RECORDED_RESULTS_SEALED")
        return {"holdout_id": identifier, "state": "CONSUMED", "results_released": False}

    def release(self, identifier, *, actor, confirmation):
        if confirmation != "AUTHORIZE_RELEASE_FINAL_RESULTS" or not actor.strip():
            raise PermissionError("Explicit authorization to release results required")
        with self.connect() as c:
            row = c.execute(
                "SELECT state,result FROM holdouts WHERE id=?", (identifier,)
            ).fetchone()
            if not row or row["state"] != "CONSUMED" or row["result"] is None:
                raise ValueError("No completed final evaluation")
            self._event(c, identifier, "RESULTS_RELEASED", actor)
            return json.loads(row["result"])

    def status(self, identifier):
        with self.connect() as c:
            row = c.execute(
                "SELECT id,manifest,state FROM holdouts WHERE id=?", (identifier,)
            ).fetchone()
            if not row:
                raise ValueError("Unknown holdout")
            events = [
                dict(e)
                for e in c.execute(
                    "SELECT at,event,detail FROM events WHERE holdout_id=? ORDER BY id",
                    (identifier,),
                )
            ]
            return {**dict(row), "events": events}
