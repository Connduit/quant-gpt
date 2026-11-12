"""Baseline hypotheses and saved OOS ML scores; all decisions follow observed bar close."""

import math

from quantlab.futures.continuous import select_contract
from quantlab.portfolio.risk import size_position


class FuturesStrategy:
    def __init__(
        self,
        features,
        contracts,
        *,
        family="momentum",
        threshold=0.0005,
        contracts_per_trade=1,
        scores=None,
        classification=False,
        maximum_holding_minutes=15,
        stop_loss=0.003,
        take_profit=0.006,
        regime="all",
        position_sizing="fixed",
        roll_method="calendar",
        roll_days=5,
        allowed_times=None,
        prediction_target="forward_return",
    ):
        if family not in ("momentum", "vwap", "opening_range", "regime", "ml", "buy_hold"):
            raise ValueError("Unknown futures hypothesis family")
        if (
            not math.isfinite(threshold)
            or threshold < 0
            or type(contracts_per_trade) is not int
            or contracts_per_trade < 1
        ):
            raise ValueError("Invalid entry threshold/contracts")
        if (
            not 1 <= maximum_holding_minutes <= 1440
            or not 0 < stop_loss < 1
            or not 0 < take_profit < 1
        ):
            raise ValueError("Invalid bounded exit rules")
        if regime not in ("all", "high_volatility", "low_volatility") or position_sizing not in (
            "fixed",
            "atr",
            "risk_budget",
        ):
            raise ValueError("Invalid regime/sizing rule")
        self.prediction_target = prediction_target
        self.family = family
        self.threshold = threshold
        self.contracts_per_trade = contracts_per_trade
        self.features = {(r["available_at"], r["contract"]): r for r in features.to_dicts()}
        self.source = features
        self.contracts = contracts
        self.scores = scores or {}
        self.classification = classification
        self.maximum_holding_minutes = maximum_holding_minutes
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.regime = regime
        self.position_sizing = position_sizing
        self.roll_method = roll_method
        self.roll_days = roll_days
        self.allowed_times = set(allowed_times) if allowed_times is not None else None
        self.active_contract = None
        self.roll_events = []
        self.entered = {}
        self.last_decision = None
        self.regime_events = []

    def on_bar(self, context):
        now = context["now"]
        if self.last_decision == now:
            return {}
        self.last_decision = now
        allowed_entry = self.allowed_times is None or now in self.allowed_times
        selected = select_contract(
            self.source, self.contracts, now, method=self.roll_method, roll_days=self.roll_days
        )
        row = self.features.get((now, selected))
        if row is None:
            return {}
        if self.active_contract and selected != self.active_contract:
            self.roll_events.append({"at": now, "old": self.active_contract, "new": selected})
        self.active_contract = selected
        held = context["positions"].get(selected, {}).get("quantity", 0)
        targets = {
            identifier: 0
            for identifier, p in context["positions"].items()
            if p["quantity"] and identifier != selected
        }
        vol = row.get("realized_volatility")
        state = "high" if vol is not None and vol > 0.2 else "low"
        self.regime_events.append({"at": now, "state": state})
        if held:
            self.entered.setdefault(
                selected, context["positions"][selected].get("opened_at") or now
            )
            entry = float(context["positions"][selected]["entry"])
            change = (float(row["close"]) / entry - 1) * (1 if held > 0 else -1)
            if (
                change <= -self.stop_loss
                or change >= self.take_profit
                or (now - self.entered[selected]).total_seconds()
                >= self.maximum_holding_minutes * 60
            ):
                targets[selected] = 0
                self.entered.pop(selected, None)
                return targets
        else:
            self.entered.pop(selected, None)
        if not allowed_entry:
            return targets
        if (
            self.regime == "high_volatility"
            and state != "high"
            or self.regime == "low_volatility"
            and state != "low"
        ):
            targets[selected] = 0
            return targets
        family = self.family
        if family == "regime":
            family = "momentum" if abs(row.get("market_trend") or 0) > 0.0005 else "vwap"
        score = None
        if family == "buy_hold":
            score = 1.0
        elif family == "ml":
            item = self.scores.get((now, selected))
            if item is None:
                return targets
            if not item["train_label_max"] < item["model_available_at"] <= now:
                raise ValueError("Future model/label reached a historical signal")
            score = item["prediction"] - (0.5 if self.classification else 0)
            if self.prediction_target == "breakout_continuation":
                strength = row.get("breakout_strength") or 0
                score *= 1 if strength > 0 else -1 if strength < 0 else 0
        elif family == "momentum":
            score = row.get("return_5m")
        elif family == "vwap":
            score = -(row.get("vwap_deviation") or 0)
        elif family == "opening_range":
            if not row.get("opening_range_ready"):
                return targets
            score = row.get("breakout_strength")
        if score is None:
            return targets
        sign = 1 if score > self.threshold else -1 if score < -self.threshold else 0
        count = self.contracts_per_trade
        if self.position_sizing != "fixed" and sign:
            contract = self.contracts[selected]
            atr = row.get("atr")
            if not atr or atr <= 0:
                count = 0
            else:
                count = min(
                    count,
                    int(
                        size_position(
                            context["portfolio"]["equity"],
                            row["close"],
                            method="atr",
                            atr=atr,
                            risk_fraction=0.005,
                            multiplier=contract.spec.multiplier,
                            maximum_weight=1,
                        )
                    ),
                )
        targets[selected] = sign * count
        return targets
