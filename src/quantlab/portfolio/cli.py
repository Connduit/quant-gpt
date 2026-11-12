from pathlib import Path

from quantlab.backtesting.report import dumps
from quantlab.discovery.common import read_json
from quantlab.portfolio.runner import run_portfolio


def execute(args):
    if args.portfolio_command in ("create", "register", "allocate"):
        return configure(args)
    if args.portfolio_command in ("backtest", "stress"):
        report = run_portfolio(
            args.portfolio_config, args.output, stress=args.portfolio_command == "stress"
        )
        print(
            dumps(
                {
                    "output": str(args.output),
                    "mode": report["mode"],
                    "paper_eligible": report["paper_eligible"],
                    "runs": {k: v["performance"] for k, v in report["runs"].items()},
                    "final_holdout": report["final_holdout"],
                }
            )
        )
    else:
        report = read_json(
            Path(args.report) / "portfolio.json"
            if Path(args.report).is_dir()
            else Path(args.report)
        )
        print(
            dumps(
                report
                if args.portfolio_command == "report"
                else {
                    "runs": {
                        k: {"risk": v["diversification"], "decisions": v["risk_decision_counts"]}
                        for k, v in report["runs"].items()
                    },
                    "overlap": report["exposure_overlap"],
                }
                if args.portfolio_command == "risk"
                else report["strategies"]
            )
        )
    return 0


def configure(args):
    import yaml

    from quantlab.portfolio.runner import load_portfolio

    path = args.output_config if args.portfolio_command == "create" else args.portfolio_config
    if args.portfolio_command == "create":
        if path.exists():
            raise ValueError("Configuration exists")
        source = read_json(args.source_validation)
        doc = {
            "name": "research_portfolio",
            "mode": "research",
            "validation_report": str(args.source_validation.resolve()),
            "verified_inputs": str(args.verified_inputs.resolve()),
            "strategies": [],
            "start": args.start,
            "end": args.end,
            "holdout_start": source["configuration"]["holdout"]["start"],
            "allocation_methods": ["equal", "inverse_volatility"],
            "allocation": {"cash_buffer": 0.1},
            "rebalance": {"schedule": "weekly"},
            "risk": {},
            "execution": {"initial_cash": "100000"},
        }
    else:
        doc = yaml.safe_load(path.read_text())
    if args.portfolio_command == "register":
        source_path = (path.resolve().parent / doc["validation_report"]).resolve()
        source = read_json(source_path)
        if args.strategy_id not in {c["strategy_id"] for c in source["candidates"]}:
            raise ValueError("Unknown evaluated strategy")
        if any(
            s["name"] == args.name or s["strategy_id"] == args.strategy_id
            for s in doc["strategies"]
        ):
            raise ValueError("Strategy already registered")
        doc["strategies"].append(
            {"name": args.name, "strategy_id": args.strategy_id, "paper_approved": False}
        )
    elif args.portfolio_command == "allocate":
        doc["allocation_methods"] = [args.method]
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(yaml.safe_dump(doc, sort_keys=False))
        if doc["strategies"]:
            load_portfolio(temporary)
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    print(
        dumps(
            {"configuration": str(path), "strategies": len(doc["strategies"]), "mode": doc["mode"]}
        )
    )
    return 0
