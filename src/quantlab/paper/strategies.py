"""Bounded deterministic strategies and version-pinned train-time ML inference."""

import hashlib
import json
import time
from datetime import timedelta
from pathlib import Path

import polars as pl

from quantlab.backtesting.models import decimal
from quantlab.ml.models import ResearchModel
from quantlab.paper.orders import PaperOrder


class QuoteMomentum:
    """Quote-event features, distinct from historical OHLCV minute features."""

    def __init__(
        self,
        strategy,
        instrument,
        *,
        lookback=5,
        units=1,
        threshold=0.0001,
        model=None,
        model_hash=None,
        training_mean=0,
        training_std=0.001,
        horizon_events=5,
    ):
        if (
            not 1 <= lookback <= 1000
            or type(units) is not int
            or units < 1
            or threshold < 0
            or training_std <= 0
        ):
            raise ValueError("Invalid bounded strategy settings")
        self.strategy = strategy
        self.instrument = instrument
        self.lookback = lookback
        self.units = units
        self.threshold = threshold
        self.mean = training_mean
        self.std = training_std
        self.model = None
        if model:
            model = Path(model)
            manifest = json.loads((model / "manifest.json").read_text())
            if (
                not model_hash
                or manifest["sha256"] != model_hash
                or hashlib.sha256((model / "model.joblib").read_bytes()).hexdigest() != model_hash
            ):
                raise ValueError("Approved model checksum required")
            self.model = ResearchModel.load(model)
            if tuple(self.model.feature_names) != ("quote_return", "quote_spread"):
                raise ValueError("Model must explicitly use the quote-event feature schema")
        self.model_hash = model_hash
        if type(horizon_events) is not int or not 1 <= horizon_events <= 1000:
            raise ValueError("Bound outcome horizon to 1–1000 quote events")
        self.horizon_events = horizon_events

    def on_event(self, runtime, event):
        if event.instrument != self.instrument or event.kind != "quote":
            return
        if not runtime.state["connected"] or runtime.state["killed"]:
            return
        if not runtime.in_session(self.instrument, event.event_at):
            return
        last = runtime.state["last_events"].get(self.instrument)
        if not last or last["event_at"] != event.event_at.isoformat():
            return
        s = runtime.state["strategies"][self.strategy]
        if s["execution"] != "RUNNING":
            return
        if s["model_hash"] != self.model_hash:
            raise ValueError("Deployment model pin differs from inference artifact")
        key = self.strategy + ":" + event.identity

        def decide():
            memory = s["memory"]
            session = str(runtime.session(self.instrument, event.event_at))
            if memory.get("session") != session:
                memory["prices"] = []
                memory["session"] = session
                for old in runtime.state["predictions"]:
                    if old["strategy"] == self.strategy and old["outcome"] is None:
                        old["remaining_events"] = -1
            history = memory.setdefault("prices", [])
            mid = float((decimal(event.bid) + decimal(event.ask)) / 2)
            history.append(mid)
            del history[: -self.lookback - 1]
            ret = mid / history[0] - 1
            spread = float((decimal(event.ask) - decimal(event.bid)) / decimal(mid))
            started = time.perf_counter()
            score = (
                float(
                    self.model.predict(
                        pl.DataFrame({"quote_return": [ret], "quote_spread": [spread]})
                    )[0]
                )
                if self.model
                else ret
            )
            if self.model and self.model.spec.objective == "classification":
                score = 2 * score - 1
            target = self.units if len(history) > self.lookback and score > self.threshold else 0
            closing = event.event_at >= runtime.session_end(
                self.instrument, event.event_at
            ) - timedelta(minutes=5)
            if closing:
                target = 0
            if (
                self.instrument in runtime.contracts
                and len(history) > self.lookback
                and score < -self.threshold
                and not closing
            ):
                target = -self.units
            filled = sum(
                f["quantity"]
                for f in runtime.account.fills
                if f["strategy"] == self.strategy and f["instrument"] == self.instrument
            )
            pending = sum(
                o.remaining
                for o in runtime.orders.values()
                if o.strategy == self.strategy
                and o.instrument == self.instrument
                and o.state in ("ACCEPTED", "PARTIALLY_FILLED")
            )
            if filled * target < 0:
                target = 0  # Close before reversal; each subsequent entry receives new risk checks.
            quantity = target - filled - pending
            for old in runtime.state["predictions"]:
                if old["strategy"] == self.strategy and old["outcome"] is None:
                    if old["remaining_events"] < 0:
                        continue
                    old["remaining_events"] -= 1
                    if old["remaining_events"] == 0:
                        old["outcome"] = mid / old["origin_price"] - 1
                        old["accuracy"] = int((old["score"] > 0) == (old["outcome"] > 0))
                        old["matured_at"] = event.event_at.isoformat()
            prediction = {
                "origin_price": mid,
                "remaining_events": self.horizon_events,
                "at": event.event_at.isoformat(),
                "strategy": self.strategy,
                "model_hash": self.model_hash,
                "score": score,
                "quote_return": ret,
                "quote_spread": spread,
                "feature_z": (ret - self.mean) / self.std,
                "latency_ms": (time.perf_counter() - started) * 1000,
                "outcome": None,
                "accuracy": None,
                "note": "Matured quote-event directional accuracy; observations remain dependent",
            }
            runtime.state["predictions"].append(prediction)
            runtime.state["decisions"][key] = {"quantity": quantity, "at": runtime.state["clock"]}

        runtime._transaction(
            "decision:" + key,
            "strategy_decision",
            {"strategy": self.strategy, "event": event.identity},
            decide,
        )
        d = runtime.state["decisions"][key]
        if d["quantity"]:
            identity = "signal:" + key
            if identity in runtime.orders:
                return
            if d["at"] != runtime.state["clock"]:
                # A crash may leave an unsubmitted intent; never backdate it after recovery.
                return
            runtime.submit(
                PaperOrder("signal:" + key, self.strategy, self.instrument, d["quantity"], d["at"]),
                now=runtime.time(d["at"]),
            )
