"""Fixed, administrator-approved research jobs outside request handlers."""

import hashlib
import json
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
    def __init__(self, root, approved=None, provider_credentials=None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "jobs.sqlite"
        self.approved = approved or {}
        self.provider_credentials = provider_credentials
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

    def submit_workflow(self, workflow, payload, library, workspace):
        """Persist a typed request before enqueueing; callers supply no command/path arguments."""
        from quantlab.web.workflows import DownloadRequest, ProfitabilityRequest, ResearchRequest

        if workflow not in ("download", "training", "discovery", "profitability"):
            raise ValueError("Unsupported dashboard workflow")
        model = {"download": DownloadRequest, "profitability": ProfitabilityRequest}.get(
            workflow, ResearchRequest
        )
        checked = model.model_validate(payload)
        if workflow in ("training", "discovery") and checked.workflow != workflow:
            raise ValueError("Workflow does not match request")
        source = None
        if workflow == "profitability":
            with self.connection() as connection:
                row = connection.execute(
                    "SELECT name,status FROM jobs WHERE id=?", (checked.source_job_id,)
                ).fetchone()
            if not row or not row[0].startswith("training-") or row[1] != "COMPLETED":
                raise ValueError("Select a completed saved training job")
            source = (self.root / checked.source_job_id / "artifacts").resolve()
            if not source.is_relative_to(self.root.resolve()):
                raise ValueError("Source job escaped its trusted directory")
        name = f"{workflow}-{uuid.uuid4().hex}"
        directory = self.root / "requests"
        directory.mkdir(exist_ok=True)
        path = directory / f"{name}.json"
        path.write_text(
            json.dumps(
                {
                    "workflow": workflow,
                    "payload": checked.model_dump(mode="json"),
                    "library": str(Path(library).resolve()),
                    **(
                        {
                            "source_artifacts": str(source),
                            "registry_root": str(self.root.parent / "profitability-registry"),
                        }
                        if source
                        else {}
                    ),
                }
            )
        )
        self.approved[name] = {
            "arguments": ["dashboard-workflow"],
            "configuration": str(path),
            "configuration_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "workspace": str(workspace),
            "wall_seconds": 1200,
        }
        try:
            return self.submit(name)
        except BaseException:
            self.approved.pop(name, None)
            path.unlink(missing_ok=True)
            raise

    def result(self, identity):
        if not any(row["id"] == identity for row in self.rows()):
            raise KeyError(identity)
        path = self.root / identity / "artifacts" / "result.json"
        if not path.exists():
            return None
        if path.stat().st_size > 20 * 1024**2:
            raise ValueError("Job report exceeds size budget")
        return json.loads(path.read_text())

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
        workflow = args == ["dashboard-workflow"]
        if not workflow and args[:2] not in (
            ["futures", "research"],
            ["validate", "run"],
            ["agent", "run"],
        ):
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
        if workflow:
            configuration = json.loads(Path(specification["configuration"]).read_text())
            if configuration["workflow"] == "download":
                if configuration["payload"].get("provider", "alpaca") == "alpaca":
                    allowed.update(("APCA_API_KEY_ID", "APCA_API_SECRET_KEY"))
                elif configuration["payload"]["provider"] == "databento":
                    allowed.add("DATABENTO_API_KEY")
        env = {k: v for k, v in os.environ.items() if k in allowed}
        if workflow and configuration["workflow"] == "download" and self.provider_credentials:
            try:
                env.update(
                    self.provider_credentials(configuration["payload"].get("provider", "alpaca"))
                )
            except (ValueError, OSError):
                self._status(
                    identity, "FAILED", "Provider keys unavailable; review provider settings"
                )
                return
        env["CUDA_VISIBLE_DEVICES"] = ""
        env["POLARS_MAX_THREADS"] = "1"
        for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
            env[variable] = "1"
        try:
            with (output / "worker.log").open("w") as log:
                command = [sys.executable, "-m", "quantlab", *args]
                if workflow:
                    command = [
                        sys.executable,
                        "-m",
                        "quantlab.web.workflow_worker",
                        "--spec",
                        specification["configuration"],
                        "--output",
                        str(output / "artifacts"),
                    ]
                elif args[:2] != ["agent", "run"]:
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
                with self.connection() as db:
                    state = db.execute("SELECT status FROM jobs WHERE id=?", (identity,)).fetchone()
                if state and state[0] == "CANCELLED":
                    return
                result = self.result(identity) if workflow else None
                self._status(
                    identity,
                    result["status"]
                    if result
                    else "COMPLETED"
                    if process.returncode == 0
                    else "FAILED",
                    str(result.get("reason", result.get("note", "")))[:1000]
                    if result
                    else f"exit={process.returncode}",
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
