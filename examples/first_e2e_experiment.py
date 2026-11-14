"""Thin execution recipe using the existing download CLI and dashboard job API.

No training, feature, signal, accounting or metric implementation lives here.
Start `quantlab dashboard` first. Outputs are immutable; repeated train/backtest
stages create new jobs and update this experiment's run index.
"""

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from quantlab.data.storage import SnapshotStore
from quantlab.profitability.inputs import permitted_dates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--stage", choices=("download", "train", "backtest", "all"), required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    # This example deliberately uses the existing token-free loopback development mode.
    if urlsplit(args.base_url).hostname not in ("127.0.0.1", "localhost", "::1"):
        parser.error("Use a local dashboard URL")
    workspace = Path(__file__).resolve().parents[1]
    config = yaml.safe_load(args.config.read_text())
    root = (workspace / config["root"]).resolve()
    if not root.is_relative_to(workspace):
        parser.error("Experiment outputs must stay inside the repository")
    root.mkdir(parents=True, exist_ok=True)
    history = config["history"]
    start, end = date.fromisoformat(history["start"]), date.fromisoformat(history["end"])
    permitted_dates(start, end)
    if end >= date(2025, 1, 1):
        parser.error("This first-experiment recipe reserves 2025 onward; do not consume it")
    library = root / "library"
    index_path = root / "run-index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {}

    def api(path, payload=None):
        request = urllib.request.Request(
            args.base_url.rstrip("/") + "/api/v1" + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)

    def run_job(workflow, payload):
        submitted = api(
            "/workflows/" + ("research" if workflow == "training" else workflow), payload
        )
        identity = submitted["id"]
        print(json.dumps({"workflow": workflow, "job_id": identity}), flush=True)
        deadline = time.monotonic() + 1800
        while time.monotonic() < deadline:
            result = api("/workflows/jobs/" + identity)
            if result.get("result"):
                outcome = result["result"]
                if outcome.get("status") != "COMPLETED":
                    raise RuntimeError(json.dumps(outcome))
                return identity
            job = next(j for j in api("/jobs")["items"] if j["id"] == identity)
            if job["status"] not in ("RUNNING", "QUEUED"):
                raise RuntimeError(f"{identity}: {job['status']} {job['detail']}")
            time.sleep(3)
        raise TimeoutError(f"Job {identity} still active; inspect or cancel it in the dashboard")

    if args.stage in ("download", "all"):
        for number, symbol in enumerate(config["symbols"]):
            command = [
                sys.executable,
                "-m",
                "quantlab",
                "--data-dir",
                str(library),
                "download",
                symbol,
                "--provider",
                history["provider"],
                "--alpaca-feed",
                history["feed"],
                "--start",
                history["start"],
                "--end",
                history["end"],
            ]
            subprocess.run(command, cwd=workspace, check=True)
            # Stay within the observed 200-request/minute SIP entitlement even
            # when a five-year minute request spans many provider pages.
            if number + 1 < len(config["symbols"]):
                time.sleep(60)
    if args.stage in ("train", "all"):
        store = SnapshotStore(library)
        snapshots = {}
        for path in sorted(store.root.glob("*/manifest.json")):
            metadata = store.inspect(path.parent.name)
            bounds = metadata["request"]
            if (bounds["start"], bounds["end"]) != (history["start"], history["end"]):
                continue
            if metadata.get("dataset_role") == "protected_test":
                continue
            if bounds["symbol"] in config["symbols"]:
                snapshots[bounds["symbol"]] = path.parent.name
        if set(snapshots) != set(config["symbols"]):
            raise ValueError("Download all configured symbols before training")
        payload = {
            **config["training"],
            "workflow": "training",
            "name": config["name"],
            "snapshot_ids": [snapshots[s] for s in config["symbols"]],
            "start": history["start"],
            "end": history["end"],
            "confirmed": True,
        }
        index["snapshots"] = snapshots
        index["training_job"] = run_job("training", payload)
        index["backtest_jobs"] = {}
        index_path.write_text(json.dumps(index, indent=2) + "\n")
    if args.stage in ("backtest", "all"):
        for model in config["training"]["models"]:
            payload = {
                **config["backtest"],
                "source_job_id": index["training_job"],
                "model": model,
                "start": history["start"],
                "end": history["end"],
                "confirmed": True,
            }
            index.setdefault("backtest_jobs", {})[model] = run_job("profitability", payload)
            index_path.write_text(json.dumps(index, indent=2) + "\n")
    print(json.dumps(index, indent=2), flush=True)


if __name__ == "__main__":
    main()
