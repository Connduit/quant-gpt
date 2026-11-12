"""Durable actual hypotheses/results, reservations and independent operator controls."""

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path


class Memory:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,objective TEXT,status TEXT,
                    policy_hash TEXT,iterations INTEGER,experiments INTEGER,spent REAL,elapsed REAL,
                    control TEXT,created TEXT);
                CREATE TABLE IF NOT EXISTS iterations(session TEXT,number INTEGER,status TEXT,
                    proposal TEXT,plan_hash TEXT,result TEXT,PRIMARY KEY(session,number));
                CREATE TABLE IF NOT EXISTS plans(hash TEXT PRIMARY KEY,session TEXT,number INTEGER);
                CREATE TABLE IF NOT EXISTS events(
                    id INTEGER PRIMARY KEY,session TEXT,at TEXT,kind TEXT,detail TEXT);
            """)

    def connection(self):
        return sqlite3.connect(self.path, timeout=10)

    def create(self, objective, policy_hash):
        if not 10 <= len(objective) <= 1200:
            raise ValueError("Testable research objective required")
        identity = uuid.uuid4().hex
        with self.connection() as db:
            db.execute(
                "INSERT INTO sessions VALUES(?,?,?,?,0,0,0,0,NULL,?)",
                (identity, objective, "CREATED", policy_hash, datetime.now(UTC).isoformat()),
            )
        return identity

    def session(self, identity):
        with self.connection() as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM sessions WHERE id=?", (identity,)).fetchone()
            if row is None:
                raise KeyError(identity)
            return dict(row)

    def sessions(self):
        with self.connection() as db:
            db.row_factory = sqlite3.Row
            return [
                dict(r)
                for r in db.execute("SELECT * FROM sessions ORDER BY created DESC LIMIT 100")
            ]

    def records(self, identity):
        with self.connection() as db:
            db.row_factory = sqlite3.Row
            return [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM iterations WHERE session=? ORDER BY number", (identity,)
                )
            ]

    def event(self, identity, kind, detail):
        with self.connection() as db:
            db.execute(
                "INSERT INTO events(session,at,kind,detail) VALUES(?,?,?,?)",
                (identity, datetime.now(UTC).isoformat(), kind, json.dumps(detail)),
            )

    def relevant_history(self, policy_hash, exclude_session):
        with self.connection() as db:
            rows = db.execute(
                "SELECT i.session,i.number,i.status,i.proposal,i.result FROM iterations i "
                "JOIN sessions s ON s.id=i.session WHERE s.policy_hash=? AND s.id!=? "
                "AND i.result IS NOT NULL ORDER BY s.created DESC,i.number DESC LIMIT 4",
                (policy_hash, exclude_session),
            ).fetchall()
        return [
            {
                "session": session,
                "number": number,
                "status": status,
                "proposal": json.loads(proposal) if proposal else None,
                "result": json.loads(result),
            }
            for session, number, status, proposal, result in rows
        ]

    def events(self, identity):
        with self.connection() as db:
            return [
                {"at": at, "kind": kind, "detail": json.loads(detail)}
                for at, kind, detail in db.execute(
                    "SELECT at,kind,detail FROM events WHERE session=? ORDER BY id", (identity,)
                )
            ]

    def update(self, identity, **fields):
        allowed = {"status", "iterations", "experiments", "spent", "elapsed", "control"}
        if not fields or set(fields) - allowed:
            raise ValueError("Unknown session field")
        with self.connection() as db:
            db.execute(
                "UPDATE sessions SET " + ",".join(k + "=?" for k in fields) + " WHERE id=?",
                (*fields.values(), identity),
            )

    def control(self, identity, action, reason):
        if action not in ("pause", "resume", "cancel", "emergency_stop") or not reason:
            raise ValueError("Explicit research control and reason required")
        self.session(identity)
        with self.connection() as db:
            if action == "resume":
                status = db.execute(
                    "SELECT status FROM sessions WHERE id=?", (identity,)
                ).fetchone()[0]
                if status != "PAUSED":
                    raise ValueError("Only paused sessions may resume")
                db.execute(
                    "UPDATE sessions SET control=NULL,status='PAUSED' WHERE id=?", (identity,)
                )
            else:
                db.execute("UPDATE sessions SET control=? WHERE id=?", (action, identity))
        self.event(identity, "operator_control", {"action": action, "reason": reason})
