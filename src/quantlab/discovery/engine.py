"""Bounded local process execution with persistent attempts, budgets and cancellation."""

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from threading import Event

import psutil

from quantlab.discovery.common import read_json, write_json
from quantlab.discovery.registry import Registry
from quantlab.discovery.tracking import Tracker


class SchedulingBudgetExhausted(RuntimeError):
    pass


class ExperimentEngine:
    def __init__(self, root, name, resources):
        self.registry = Registry(Path(root))
        self.root = self.registry.root
        self.resources = resources
        self.cancel = Event()
        self.registry.recover()
        self.tracker = Tracker(self.root, name)
        available = (
            sorted(os.sched_getaffinity(0))
            if hasattr(os, "sched_getaffinity")
            else list(range(os.cpu_count() or 1))
        )
        if resources.workers * resources.cpu_threads > len(available):
            raise ValueError("Requested workers * CPU threads exceeds available CPUs")
        self.cpus = available

    def run(
        self,
        definition,
        *,
        slot=0,
        role="trial",
        parent_id=None,
        reproduce=False,
        trial=None,
        deadline=None,
    ):
        identity, attempt, claimed = self.registry.claim(
            definition, role, parent_id, reproduce, self.resources.max_attempts
        )
        if not claimed:
            return {
                "experiment_id": identity,
                "attempt": attempt,
                "duplicate": True,
                "result": json.loads(attempt["result"]) if attempt.get("result") else None,
            }
        output = Path(attempt["artifact_path"])
        run_id = None
        process = None
        result = None
        status, reason = "FAILED", None
        started = time.monotonic()
        try:
            output.mkdir(parents=True)
            write_json(output / "definition.json", definition)
            run_id = self.tracker.start(
                identity, attempt, definition, trial.number if trial else None
            )
            self.registry.update(attempt["id"], run_id=run_id)
            if deadline is not None and time.monotonic() >= deadline:
                raise SchedulingBudgetExhausted("Study/batch budget exhausted before worker launch")
            affinity = self.cpus[
                slot * self.resources.cpu_threads : (slot + 1) * self.resources.cpu_threads
            ]
            request = {
                "definition": definition,
                "output": str(output),
                "resources": asdict(self.resources),
                "cpu_affinity": affinity,
                "progress_handshake": trial is not None,
            }
            write_json(output / "request.json", request)
            environment = os.environ.copy()
            for name in (
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "MKL_NUM_THREADS",
                "NUMEXPR_NUM_THREADS",
                "POLARS_MAX_THREADS",
            ):
                environment[name] = str(self.resources.cpu_threads)
            environment["CUDA_VISIBLE_DEVICES"] = ""
            environment["NVIDIA_VISIBLE_DEVICES"] = "void"
            environment["PYTHONHASHSEED"] = str(definition["model"]["seed"])
            with (output / "worker.log").open("w") as log:
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "quantlab.discovery.worker",
                        str(output / "request.json"),
                    ],
                    cwd=output,
                    env=environment,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                child = psutil.Process(process.pid)
                self.registry.update(
                    attempt["id"], child_pid=process.pid, child_start=child.create_time()
                )
                reported = set()
                while process.poll() is None:
                    if self.cancel.is_set():
                        status, reason = "INTERRUPTED", "Study controller cancellation"
                        break
                    now = time.monotonic()
                    if (
                        now - started >= self.resources.trial_wall_seconds
                        or deadline is not None
                        and now >= deadline
                    ):
                        status, reason = "TIMEOUT", "Wall-time budget exhausted"
                        break
                    try:
                        memory = child.memory_info().rss + sum(
                            p.memory_info().rss for p in child.children(recursive=True)
                        )
                        if memory > self.resources.memory_mb * 1024**2:
                            status, reason = "MEMORY_LIMIT", "Resident-memory budget exhausted"
                            break
                    except psutil.Error:
                        pass
                    progress = output / "progress.json"
                    if trial and progress.exists():
                        record = read_json(progress)
                        step = record["completed_windows"] - 1
                        if step not in reported:
                            trial.report(record["intermediate_score"], step)
                            reported.add(step)
                            if (
                                record["completed_windows"] >= 2
                                and record["completed_windows"] < record["total_windows"]
                                and trial.should_prune()
                            ):
                                (output / "cancel").touch()
                                status, reason = (
                                    "PRUNED",
                                    "Optuna validation-window threshold pruning",
                                )
                                break
                            (output / f"ack-{record['completed_windows']}").touch()
                    time.sleep(0.05)
                if reason:
                    self._stop(process)
                elif process.returncode == 0 and (output / "result.json").exists():
                    result = read_json(output / "result.json")
                    status = "COMPLETE" if result["summary"]["eligible"] else "REJECTED"
                    reason = ";".join(result["summary"]["rejection_reasons"]) or None
                elif (output / "failure.json").exists():
                    failure = read_json(output / "failure.json")
                    reason = f"{failure['type']}: {failure['reason']}"
                    status = (
                        "MEMORY_LIMIT"
                        if failure["type"] == "MemoryError"
                        or "allocate memory" in failure["reason"].lower()
                        or "failed to map segment" in failure["reason"].lower()
                        else "FAILED"
                    )
                else:
                    reason = f"Worker exited with status {process.returncode}; inspect worker.log"
                    status = (
                        "CPU_LIMIT"
                        if process.returncode == -signal.SIGXCPU
                        else "RESOURCE_EXIT"
                        if process.returncode == -signal.SIGKILL
                        else "FAILED"
                    )
        except SchedulingBudgetExhausted as exc:
            status, reason = "NOT_RUN_BUDGET", str(exc)
        except KeyboardInterrupt:
            status, reason = "INTERRUPTED", "Interrupted by operator"
            if process:
                self._stop(process)
            raise
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            if process:
                self._stop(process)
        finally:
            write_json(
                output / "execution.json",
                {
                    "status": status,
                    "reason": reason,
                    "elapsed_seconds": time.monotonic() - started,
                    "resources": asdict(self.resources),
                    "cpu_enforcement": "RLIMIT_CPU + affinity on Linux",
                    "memory_enforcement": "RLIMIT_AS + sampled RSS",
                    "experiment_id": identity,
                    "attempt_id": attempt["id"],
                    "mlflow_run_id": run_id,
                },
            )
            if run_id:
                try:
                    self.tracker.finish(run_id, status, output, result, reason)
                except Exception as exc:
                    status, reason = "TRACKING_FAILED", f"{type(exc).__name__}: {exc}"
                    try:
                        self.tracker.client.set_tag(run_id, "quantlab.status", "TRACKING_FAILED")
                        self.tracker.client.set_terminated(run_id, "FAILED")
                    except Exception:
                        pass  # Registry still preserves the tracking failure and local artifacts.
            self.registry.update(
                attempt["id"], status=status, reason=reason, ended=time.time(), result=result
            )
        return {
            "experiment_id": identity,
            "attempt": self.registry.attempt(attempt["id"]),
            "duplicate": False,
            "result": result,
        }

    @staticmethod
    def _stop(process):
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                return
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=2)
