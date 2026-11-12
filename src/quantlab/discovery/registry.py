"""Transactional identities and attempts are independent of Optuna and MLflow state."""

import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import psutil

from quantlab.backtesting.report import dumps
from quantlab.discovery.common import fingerprint


class Registry:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "registry.sqlite"
        with self.connect() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS experiments (
                  id TEXT PRIMARY KEY, definition TEXT NOT NULL, hypothesis TEXT NOT NULL,
                  created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS attempts (
                  id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL, number INTEGER NOT NULL,
                  role TEXT NOT NULL, parent_id TEXT, status TEXT NOT NULL, reason TEXT,
                  owner_pid INTEGER, owner_start REAL, child_pid INTEGER, child_start REAL,
                  run_id TEXT, started REAL, ended REAL, result TEXT, artifact_path TEXT,
                  UNIQUE(experiment_id, number));
                CREATE TABLE IF NOT EXISTS studies (
                  name TEXT PRIMARY KEY, policy_hash TEXT NOT NULL,
                  elapsed REAL NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS trial_links (
                  study TEXT, number INTEGER, experiment_id TEXT, attempt_id TEXT,
                  disposition TEXT, reason TEXT, PRIMARY KEY(study,number));
            """)

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        try:
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def claim(self, definition, role="trial", parent_id=None, reproduce=False, max_attempts=2):
        identity = fingerprint({k: v for k, v in definition.items() if k != "git_commit"})
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute(
                "INSERT OR IGNORE INTO experiments VALUES (?,?,?,?)",
                (identity, dumps(definition), definition["hypothesis"], time.time()),
            )
            previous = c.execute(
                "SELECT * FROM attempts WHERE experiment_id=? ORDER BY number DESC LIMIT 1",
                (identity,),
            ).fetchone()
            if previous:
                if previous["status"] == "RUNNING" or (
                    previous["status"] in ("COMPLETE", "REJECTED") and not reproduce
                ):
                    return identity, dict(previous), False
                if previous["number"] >= max_attempts and not reproduce:
                    return identity, dict(previous), False
            number = previous["number"] + 1 if previous else 1
            attempt = f"{identity[:16]}-{number}-{uuid.uuid4().hex[:8]}"
            artifact = self.root / "attempts" / attempt
            c.execute(
                """INSERT INTO attempts
              (id,experiment_id,number,role,parent_id,status,owner_pid,owner_start,started,artifact_path)
              VALUES (?,?,?,?,?,'RUNNING',?,?,?,?)""",
                (
                    attempt,
                    identity,
                    number,
                    role,
                    parent_id,
                    os.getpid(),
                    psutil.Process().create_time(),
                    time.time(),
                    str(artifact),
                ),
            )
            row = c.execute("SELECT * FROM attempts WHERE id=?", (attempt,)).fetchone()
        return identity, dict(row), True

    def update(self, attempt_id, **values):
        allowed = {"status", "reason", "child_pid", "child_start", "run_id", "ended", "result"}
        if set(values) - allowed:
            raise ValueError("Invalid registry update")
        if "result" in values and values["result"] is not None:
            values["result"] = dumps(values["result"])
        with self.connect() as c:
            c.execute(
                "UPDATE attempts SET " + ",".join(f"{key}=?" for key in values) + " WHERE id=?",
                (*values.values(), attempt_id),
            )

    def rows(self):
        with self.connect() as c:
            return [
                dict(row)
                for row in c.execute("""SELECT a.*,e.hypothesis,e.definition FROM attempts a
                         JOIN experiments e ON a.experiment_id=e.id ORDER BY a.started""")
            ]

    def attempt(self, attempt_id):
        return next((row for row in self.rows() if row["id"] == attempt_id), None)

    def recover(self):
        recovered = []
        for row in self.rows():
            if row["status"] != "RUNNING":
                continue
            try:
                owner = psutil.Process(row["owner_pid"])
                if abs(owner.create_time() - row["owner_start"]) < 0.01 and owner.is_running():
                    continue
            except (psutil.Error, TypeError):
                pass
            if row["child_pid"]:
                try:
                    child = psutil.Process(row["child_pid"])
                    if abs(child.create_time() - row["child_start"]) < 0.01:
                        child.terminate()
                        try:
                            child.wait(timeout=3)
                        except psutil.TimeoutExpired:
                            child.kill()
                            child.wait(timeout=3)
                except psutil.Error:
                    pass
            self.update(
                row["id"],
                status="INTERRUPTED",
                reason="Owner process ended; recovered orphan attempt",
                ended=time.time(),
            )
            recovered.append(row["id"])
        return recovered

    def study(self, name, policy_hash):
        with self.connect() as c:
            c.execute("INSERT OR IGNORE INTO studies VALUES (?,?,0)", (name, policy_hash))
            row = c.execute("SELECT * FROM studies WHERE name=?", (name,)).fetchone()
            if row["policy_hash"] != policy_hash:
                raise ValueError("Study configuration/code/data changed; use a new study name")
            return row["elapsed"]

    def add_elapsed(self, name, value):
        with self.connect() as c:
            c.execute("UPDATE studies SET elapsed=elapsed+? WHERE name=?", (value, name))

    def link(self, study, number, experiment, attempt, disposition, reason=None):
        with self.connect() as c:
            c.execute(
                "INSERT OR REPLACE INTO trial_links VALUES (?,?,?,?,?,?)",
                (study, number, experiment, attempt, disposition, reason),
            )

    def counts(self):
        with self.connect() as c:
            return {
                "unique_hypotheses": c.execute("SELECT count(*) FROM experiments").fetchone()[0],
                "attempts": c.execute("SELECT count(*) FROM attempts").fetchone()[0],
                "optuna_trials": c.execute("SELECT count(*) FROM trial_links").fetchone()[0],
            }

    def links(self):
        with self.connect() as c:
            return [
                dict(row) for row in c.execute("SELECT * FROM trial_links ORDER BY study,number")
            ]
