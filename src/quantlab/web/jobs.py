"""Fixed, administrator-approved research jobs outside request handlers."""

import hashlib
import os
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path


class JobManager:
    def __init__(self, root, approved=None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "jobs.sqlite"
        self.approved = approved or {}
        self.lock = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="quantlab-jobs")
        self.processes = {}
        with self.connection() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,name TEXT,"
                "status TEXT,created TEXT,detail TEXT)"
            )
            # Never resubmit a job whose completion status became uncertain after restart.
            db.execute(
                "UPDATE jobs SET status='RECOVERY_REQUIRED',detail='Review retained workers' "
                "WHERE status IN ('QUEUED','RUNNING')"
            )

    def connection(self):
        return sqlite3.connect(self.path, timeout=10)

    def rows(self):
        with self.connection() as db:
            return [
                dict(zip(("id", "name", "status", "created", "detail"), r, strict=True))
                for r in db.execute("SELECT * FROM jobs ORDER BY created DESC LIMIT 100")
            ]

    def submit(self, name):
        if name not in self.approved:
            raise ValueError("Job is not in the approved server allowlist")
        with self.connection() as db:
            if db.execute("SELECT 1 FROM jobs WHERE status='RECOVERY_REQUIRED'").fetchone():
                raise ValueError("Uncertain previous worker requires operator reconciliation")
        identity = uuid.uuid4().hex
        with self.lock, self.connection() as db:
            if (
                db.execute(
                    "SELECT count(*) FROM jobs WHERE status IN ('QUEUED','RUNNING')"
                ).fetchone()[0]
                >= 2
            ):
                raise ValueError("Bounded job queue is full")
            db.execute(
                "INSERT INTO jobs VALUES(?,?,?,?,?)",
                (identity, name, "QUEUED", datetime.now(UTC).isoformat(), ""),
            )
        self.pool.submit(self._run, identity, name)
        return identity

    def _status(self, identity, status, detail=""):
        with self.connection() as db:
            db.execute("UPDATE jobs SET status=?,detail=? WHERE id=?", (status, detail, identity))

    def _run(self, identity, name):
        output = self.root / identity
        output.mkdir()
        specification = self.approved[name]
        args = specification["arguments"]
        if "configuration" in specification:
            digest = hashlib.sha256(Path(specification["configuration"]).read_bytes()).hexdigest()
            if digest != specification["configuration_sha256"]:
                self._status(identity, "FAILED", "Approved configuration changed; review required")
                return
        if any(not isinstance(a, str) for a in args):
            self._status(identity, "FAILED", "Invalid administrator job arguments")
            return
        # Allow only reviewed CLI workflows; no shell and no user-selected command.
        if args[:2] not in (["futures", "research"], ["validate", "run"], ["agent", "run"]):
            self._status(identity, "FAILED", "Unsupported approved workflow")
            return
        with self.connection() as db:
            row = db.execute("SELECT status FROM jobs WHERE id=?", (identity,)).fetchone()
            if not row or row[0] == "CANCELLED":
                return
        self._status(identity, "RUNNING")
        allowed = {
            "PATH",
            "HOME",
            "LANG",
            "TZ",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "NO_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
            "no_proxy",
            "SSL_CERT_FILE",
            "SSL_CERT_DIR",
            "REQUESTS_CA_BUNDLE",
        }
        if args[:2] == ["agent", "run"] and "--scripted-engineering" not in args:
            allowed.add("QUANTLAB_LLM_API_KEY")
        env = {k: v for k, v in os.environ.items() if k in allowed}
        env["CUDA_VISIBLE_DEVICES"] = ""
        env["POLARS_MAX_THREADS"] = "1"
        try:
            with (output / "worker.log").open("w") as log:
                command = [sys.executable, "-m", "quantlab", *args]
                if args[:2] != ["agent", "run"]:
                    command.extend(["--output", str(output / "artifacts")])
                process = subprocess.Popen(
                    command,
                    cwd=specification["workspace"],
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                with self.lock:
                    self.processes[identity] = process
                began = time.monotonic()
                maximum = min(1800, float(specification.get("wall_seconds", 600)))
                while process.poll() is None:
                    with self.connection() as db:
                        status = db.execute(
                            "SELECT status FROM jobs WHERE id=?", (identity,)
                        ).fetchone()[0]
                    if status == "CANCELLED" or time.monotonic() - began >= maximum:
                        os.killpg(process.pid, signal.SIGTERM)
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait()
                        if status != "CANCELLED":
                            self._status(identity, "FAILED", "Outer wall-time budget exhausted")
                        return
                    time.sleep(0.1)
                self._status(
                    identity,
                    "COMPLETED" if process.returncode == 0 else "FAILED",
                    f"exit={process.returncode}",
                )
        except (OSError, ValueError) as exc:
            self._status(identity, "FAILED", type(exc).__name__)
        finally:
            with self.lock:
                self.processes.pop(identity, None)

    def cancel(self, identity):
        with self.connection() as db:
            row = db.execute("SELECT status FROM jobs WHERE id=?", (identity,)).fetchone()
            if row is None:
                raise KeyError(identity)
            if row[0] in ("QUEUED", "RUNNING"):
                db.execute(
                    "UPDATE jobs SET status='CANCELLED',detail='Operator cancellation' WHERE id=?",
                    (identity,),
                )

    def close(self):
        for row in self.rows():
            if row["status"] in ("QUEUED", "RUNNING"):
                self.cancel(row["id"])
        self.pool.shutdown(wait=True, cancel_futures=True)
