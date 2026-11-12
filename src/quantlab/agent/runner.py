"""One bounded orchestrator with persistent reservations and actual research evidence."""

import fcntl
import json
import math
import threading
import time
from pathlib import Path

from quantlab.agent.providers import LLMUnavailable, OpenAICompatible, ScriptedPlanner
from quantlab.discovery.common import fingerprint


class Agent:
    def __init__(self, tools, memory, root, provider, *, history_roots=()):
        self.tools = tools
        self.memory = memory
        self.root = Path(root)
        self.provider = provider
        self.history_roots = tuple(map(Path, history_roots))
        self.root.mkdir(parents=True, exist_ok=True)

    def run(self, identity):
        session = self.memory.session(identity)
        if session["policy_hash"] != self.tools.identity:
            raise ValueError("Policy/code changed; cannot resume old session")
        if session["status"] not in ("CREATED", "PAUSED"):
            raise ValueError(
                "Session cannot be resumed automatically from uncertain/completed state"
            )
        lock = (self.root / "agent.lock").open("a")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            raise ValueError("Only one orchestrating research agent may run") from None
        began = time.monotonic()
        prior_elapsed = session["elapsed"]
        stop = threading.Event()
        watch_done = threading.Event()

        def watch():
            while not watch_done.wait(0.1):
                if self.memory.session(identity)["control"] in (
                    "pause",
                    "cancel",
                    "emergency_stop",
                ):
                    stop.set()
                    return

        watcher = threading.Thread(target=watch, daemon=True)
        watcher.start()
        self.memory.update(identity, status="RUNNING")
        try:
            budgets = self.tools.budgets
            for number in range(session["iterations"], budgets.max_iterations):
                current = self.memory.session(identity)
                if current["control"] in ("pause", "cancel", "emergency_stop"):
                    stop.set()
                if stop.is_set():
                    break
                elapsed = prior_elapsed + time.monotonic() - began
                if elapsed + self.tools.wall > budgets.max_runtime_seconds:
                    self.memory.event(
                        identity, "budget_stop", {"reason": "insufficient reserved wall time"}
                    )
                    break
                count = self.tools.experiments_per_study
                if current["experiments"] + count > budgets.max_experiments:
                    self.memory.event(
                        identity,
                        "budget_stop",
                        {"reason": "experiment budget, including conventional controls"},
                    )
                    break
                history = self.memory.relevant_history(self.tools.identity, identity)
                for row in self.memory.records(identity):
                    history.append(
                        {
                            "number": row["number"],
                            "status": row["status"],
                            "result": json.loads(row["result"]) if row["result"] else None,
                        }
                    )
                context = json.dumps(
                    {"objective": current["objective"], **self.tools.context(history)}, default=str
                )
                if len(context.encode()) > budgets.max_context_bytes:
                    # Dataset scope stays complete; bounded iteration summaries may be trimmed.
                    context = json.dumps(
                        {"objective": current["objective"], **self.tools.context(history[-1:])},
                        default=str,
                    )
                if len(context.encode()) > budgets.max_context_bytes:
                    raise ValueError("Context exceeds explicit byte budget")
                reserve = self.provider.reserve_cost(
                    len(context.encode()), budgets.max_output_tokens
                )
                if not math.isfinite(reserve) or reserve < 0:
                    raise ValueError("Invalid provider cost reservation")
                if current["spent"] + reserve > budgets.max_api_spend:
                    self.memory.event(identity, "budget_stop", {"reason": "API spend reservation"})
                    break
                self.memory.update(
                    identity, spent=current["spent"] + reserve, iterations=number + 1
                )
                with self.memory.connection() as db:
                    db.execute(
                        "INSERT INTO iterations VALUES(?,?,?,?,?,?)",
                        (identity, number, "PLANNING", None, None, None),
                    )
                try:
                    answer = self.provider.propose(
                        context, max_output_tokens=budgets.max_output_tokens
                    )
                    charged = max(
                        reserve, answer.cost
                    )  # Conservative reservations never disappear on ambiguous usage.
                    self.memory.update(identity, spent=current["spent"] + charged)
                    self.memory.event(
                        identity,
                        "llm_usage",
                        {
                            "provider": answer.provider,
                            "model": answer.model,
                            "input_tokens": answer.input_tokens,
                            "output_tokens": answer.output_tokens,
                            "reported_cost": answer.cost,
                            "charged_reservation": charged,
                            "capabilities": getattr(self.provider, "capabilities", None),
                        },
                    )
                    if current["spent"] + charged > budgets.max_api_spend:
                        raise ValueError("Provider exceeded reserved spend; stop further calls")
                    plan = self.tools.validate(answer.plan)
                    plan_hash = fingerprint(
                        {"policy": self.tools.identity, "executable": self.tools.executable(plan)}
                    )
                    with self.memory.connection() as db:
                        previous = db.execute(
                            "SELECT session,number FROM plans WHERE hash=?", (plan_hash,)
                        ).fetchone()
                        db.execute(
                            (
                                "UPDATE iterations SET proposal=?,plan_hash=? WHERE session=? AND "
                                "number=?"
                            ),
                            (plan.model_dump_json(), plan_hash, identity, number),
                        )
                        if previous:
                            db.execute(
                                (
                                    "UPDATE iterations SET status='DUPLICATE',result=? WHERE "
                                    "session=? AND number=?"
                                ),
                                (
                                    json.dumps(
                                        {
                                            "previous_session": previous[0],
                                            "previous_iteration": previous[1],
                                        }
                                    ),
                                    identity,
                                    number,
                                ),
                            )
                            continue
                        db.execute("INSERT INTO plans VALUES(?,?,?)", (plan_hash, identity, number))
                    if stop.is_set():
                        with self.memory.connection() as db:
                            db.execute(
                                (
                                    "UPDATE iterations SET status='INTERRUPTED' WHERE session=? "
                                    "AND number=?"
                                ),
                                (identity, number),
                            )
                        break
                    self.memory.update(identity, experiments=current["experiments"] + count)
                    with self.memory.connection() as db:
                        db.execute(
                            "UPDATE iterations SET status='EXECUTING' WHERE session=? AND number=?",
                            (identity, number),
                        )
                    output = self.root / "sessions" / identity / f"iteration-{number}"
                    result = self.tools.run(
                        plan, output, stop_event=stop, history_roots=self.history_roots
                    )
                    evidence = {
                        "counts": result["counts"],
                        "recorded_history": result["recorded_history"],
                        "holdout_state": result["holdout"]["state"],
                        "eligible": result["paper_trading_shortlist"],
                        "observations": [
                            {k: r[k] for k in ("experiment_id", "status", "summary", "statistics")}
                            for r in result["results"]
                        ],
                        "failed": result["failed"],
                        "limitations": result["limitations"],
                        "result_path": str(output / "research/research.json"),
                    }
                    status = (
                        "INTERRUPTED"
                        if stop.is_set()
                        else "REJECTED"
                        if not evidence["eligible"]
                        else "REVIEW_REQUIRED"
                    )
                    with self.memory.connection() as db:
                        db.execute(
                            "UPDATE iterations SET status=?,result=? WHERE session=? AND number=?",
                            (status, json.dumps(evidence), identity, number),
                        )
                except (ValueError, KeyError, TypeError, OSError, LLMUnavailable) as exc:
                    with self.memory.connection() as db:
                        db.execute(
                            (
                                "UPDATE iterations SET status='FAILED',result=? WHERE session=? "
                                "AND number=?"
                            ),
                            (
                                json.dumps({"error_type": type(exc).__name__, "error": str(exc)}),
                                identity,
                                number,
                            ),
                        )
                    self.memory.event(
                        identity, "iteration_failed", {"number": number, "type": type(exc).__name__}
                    )
                    if (
                        isinstance(exc, LLMUnavailable)
                        or self.memory.session(identity)["spent"] > budgets.max_api_spend
                    ):
                        break
            control = self.memory.session(identity)["control"]
            status = (
                "PAUSED"
                if control == "pause"
                else "CANCELLED"
                if control in ("cancel", "emergency_stop")
                else "COMPLETED"
            )
            self.memory.update(
                identity, status=status, elapsed=prior_elapsed + time.monotonic() - began
            )
            return self.report(identity)
        except BaseException:
            self.memory.update(
                identity, status="FAILED", elapsed=prior_elapsed + time.monotonic() - began
            )
            raise
        finally:
            watch_done.set()
            watcher.join(timeout=1)
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()

    def report(self, identity):
        records = self.memory.records(identity)
        document = {
            "session": self.memory.session(identity),
            "iterations": [],
            "provider": getattr(self.provider, "name", "unknown"),
            "external_llm_verified": getattr(self.provider, "external_verified", False),
            "live_enabled": False,
            "holdout_accessed": False,
            "conclusion": (
                "No strategy is eligible without independent statistical evidence and human "
                "approvals."
            ),
            "recommended_next_experiment": (
                "Collect longer verified independent sessions and certified historical margin data "
                "before eligibility assessment."
            ),
            "events": self.memory.events(identity),
            "generated_code_execution": "disabled; review-only text proposals",
        }
        for record in records:
            document["iterations"].append(
                {
                    **record,
                    "proposal": json.loads(record["proposal"]) if record["proposal"] else None,
                    "result": json.loads(record["result"]) if record["result"] else None,
                }
            )
        directory = self.root / "sessions" / identity
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "report.json").write_text(json.dumps(document, indent=2) + "\n")
        return document


def scripted_plans(dataset_id):
    for model, horizon in (("ridge", 5), ("random_forest", 15)):
        yield {
            "hypothesis": {
                "market": "futures",
                "instruments": ["ES"],
                "relationship": (
                    "Past-only intraday momentum and volatility may predict subsequent ES returns "
                    "after realistic costs."
                ),
                "biases": [
                    "Short historical sample",
                    "Repeated chronological discovery",
                    "Assumed historical margins",
                ],
                "rejection_criteria": (
                    "Reject if net return is nonpositive, benchmark excess is nonpositive, or "
                    "independent-session evidence is insufficient."
                ),
                "evaluation": "purged_walk_forward",
            },
            "dataset_id": dataset_id,
            "feature_set": "technical",
            "model": model,
            "target": "forward_return",
            "horizon_minutes": horizon,
            "decision_minutes": 5,
            "interpretation": (
                "Engineering proposal, not observed profitability. Any conclusion must follow "
                "stored statistical evidence."
            ),
        }


def provider_from_policy(tools, *, scripted=False):
    if scripted:
        return ScriptedPlanner(scripted_plans(tools.config["dataset_id"]))
    config = tools.config.get("llm", {})
    from urllib.parse import urlsplit

    if tools.budgets.max_api_spend <= 0 and urlsplit(
        config.get("endpoint", "https://api.openai.com/v1")
    ).hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError(
            "Remote LLM calls require explicit reviewed pricing and a positive spend budget"
        )
    return OpenAICompatible(**config)
