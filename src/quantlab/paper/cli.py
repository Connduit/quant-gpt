"""Safe local paper account controls and replay/service configuration."""

import json
import sqlite3
from pathlib import Path

import yaml

from quantlab.backtesting.report import dumps
from quantlab.futures.contracts import contract_from_dict
from quantlab.paper.risk import PaperLimits
from quantlab.paper.runtime import PaperRuntime
from quantlab.paper.store import PaperStore


def configured(path):
    doc = yaml.safe_load(Path(path).read_text())
    if (
        set(doc) - {"execution", "account", "market_data", "risk", "strategies"}
        or doc["execution"].get("mode") != "simulated"
    ):
        raise ValueError("Strict simulated-only paper configuration required")
    account = doc["account"]
    if set(account) - {"database", "capital", "symbols", "contracts"}:
        raise ValueError("Unknown account field")
    db = Path(account["database"])
    db = db if db.is_absolute() else Path(path).resolve().parent / db
    contracts = {c["identifier"]: contract_from_dict(c) for c in account.get("contracts", [])}
    kwargs = {
        "capital": account.get("capital", 100000),
        "symbols": account.get("symbols", ()),
        "contracts": contracts,
        "mode": doc["market_data"]["mode"],
        "limits": PaperLimits(**doc.get("risk", {})),
    }
    return doc, db, kwargs


def execute(args):
    if args.paper_command in (
        "pause",
        "resume",
        "stop",
        "kill",
        "reset-kill",
        "connect",
        "disconnect",
    ):
        action = args.paper_command.replace("-", "_")
        PaperStore.queue(
            args.database, {"action": action, "strategy": args.strategy, "reason": args.reason}
        )
        print(dumps({"queued": True, "action": action, "execution": "simulated"}))
        return 0
    if args.paper_command == "replay":
        from quantlab.paper.demo import demonstrate

        print(dumps(demonstrate(args.output)))
        return 0
    if args.paper_command == "start":
        from quantlab.paper.feeds import AlpacaQuotes
        from quantlab.paper.service import run_service
        from quantlab.paper.strategies import QuoteMomentum

        doc, db, kwargs = configured(args.paper_config)
        if doc["market_data"]["provider"] != "alpaca" or kwargs["mode"] == "replay":
            raise ValueError(
                "Service requires explicitly configured Alpaca data feed; use "
                "replay command for archival data"
            )
        runtime = PaperRuntime(db, **kwargs)
        try:
            strategies = []
            for s in doc.get("strategies", []):
                # Deployment approval is provisioned by trusted operator API, never YAML assertions.
                if s["id"] not in runtime.state["strategies"]:
                    raise ValueError("Strategy must already have an approved, persisted deployment")
                if runtime.state["strategies"][s["id"]]["deployment"] == "RESEARCH":
                    raise ValueError("RESEARCH deployment cannot use a live/delayed feed")
                strategies.append(QuoteMomentum(s["id"], **s["settings"]))
            feed = AlpacaQuotes(kwargs["symbols"], feed=doc["market_data"].get("feed", "iex"))
            run_service(runtime, feed, strategies)
        finally:
            runtime.close()
        return 0
    uri = Path(args.database).resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        row = db.execute("SELECT payload FROM state WHERE id=1").fetchone()
        state = json.loads(row[0])
        field = {
            "orders": "orders",
            "fills": "fills",
            "strategies": "strategies",
            "logs": "alerts",
            "equity": "equity_history",
            "positions": "fills",
            "report": None,
        }[args.paper_command]
        if args.paper_command == "positions":
            positions = {}
            for f in state["fills"]:
                positions[f["instrument"]] = positions.get(f["instrument"], 0) + f["quantity"]
            result = {
                "positions": positions,
                "mode": state["configuration"]["mode"],
                "execution": "SIMULATED",
            }
        else:
            result = state[field] if field else state
        print(dumps(result))
    return 0
