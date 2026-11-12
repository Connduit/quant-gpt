"""Real ES archival engineering demo; synthetic input requires an explicit flag."""

import argparse
import hashlib
from datetime import UTC, datetime
from pathlib import Path

import yaml

from quantlab.backtesting.report import dumps
from quantlab.discovery.common import fingerprint, read_json, write_json
from quantlab.futures.contracts import contract_from_dict
from quantlab.futures.providers import FuturesRequest, LeanFuturesProvider
from quantlab.futures.research import run_futures_research
from quantlab.futures.storage import FuturesStore, normalize
from quantlab.futures.synthetic import synthetic_futures_snapshot


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inputs", type=Path)
    p.add_argument("--output", type=Path, default=Path("data/futures/milestone-7-demo"))
    p.add_argument("--synthetic", action="store_true")
    p.add_argument("--trials", type=int, default=4)
    args = p.parse_args()
    if args.output.exists():
        raise ValueError("Output exists; select a new directory")
    inputs = (
        args.inputs
        or Path("data/futures/synthetic-inputs" if args.synthetic else "data/futures/real-inputs")
    ).resolve()
    if (inputs / "dataset.json").exists():
        pointer = read_json(inputs / "dataset.json")
        store = FuturesStore(inputs)
        metadata = store.manifest(pointer["snapshot_id"])
        if metadata["synthetic"] != args.synthetic:
            raise ValueError("Explicit fixture/real mode does not match retained dataset")
        for url, digest in metadata["quality"].get("source_hashes", {}).items():
            if (
                hashlib.sha256((inputs / "source" / url.rsplit("/", 1)[1]).read_bytes()).hexdigest()
                != digest
            ):
                raise ValueError("Retained source archive checksum changed")
    elif args.synthetic:
        pointer = synthetic_futures_snapshot(inputs)
    else:
        contracts_file = (
            Path(__file__).resolve().parents[1] / "configs/futures-contracts.example.yaml"
        )
        document = yaml.safe_load(contracts_file.read_text())
        contract = contract_from_dict(document["contracts"]["ESZ13"])
        provider = LeanFuturesProvider(include_auxiliary=True)
        request = FuturesRequest(
            contract,
            datetime(2013, 10, 7, 13, 30, tzinfo=UTC),
            datetime(2013, 10, 11, 20, tzinfo=UTC),
        )
        download = provider.fetch(request)
        frame, quality = normalize(download.raw, contract, request=request)
        quality.update(
            source_hashes=provider.source_hashes,
            quote_coverage=frame["ask_open"].is_not_null().mean(),
            open_interest_coverage=frame["open_interest"].is_not_null().mean(),
        )
        inputs.mkdir(parents=True, exist_ok=True)
        identifier = FuturesStore(inputs).write(
            frame,
            download.raw,
            contract,
            provider=provider.name,
            source=download.source,
            synthetic=False,
            quality=quality,
        )
        (inputs / "source").mkdir(exist_ok=True)
        for url, payload in provider.payloads.items():
            (inputs / "source" / url.rsplit("/", 1)[1]).write_bytes(payload)
        pointer = {
            "snapshot_id": identifier,
            "contract": contract.as_dict(),
            "quality": quality,
            "holdout_start": "2013-10-14T00:00:00+00:00",
            "reserved_period_downloaded": False,
        }
        write_json(inputs / "dataset.json", pointer)
    template = Path(__file__).resolve().parents[1] / "configs/futures-research.example.yaml"
    config = yaml.safe_load(template.read_text())
    config["data"]["store"] = str(inputs)
    config["data"]["snapshots"] = [pointer["snapshot_id"]]
    config["data"]["holdout_start"] = pointer["holdout_start"]
    from datetime import timedelta

    config["data"]["holdout_end"] = (
        datetime.fromisoformat(pointer["holdout_start"]) + timedelta(days=1)
    ).isoformat()
    config["study"]["max_trials"] = args.trials
    if args.synthetic:
        config["study"]["name"] = "explicit_synthetic_futures_engineering"
    path = inputs / f"research-{fingerprint(config)[:12]}.yaml"
    content = yaml.safe_dump(config, sort_keys=False)
    if path.exists() and path.read_text() != content:
        raise ValueError("Configuration identity collision; refusing overwrite")
    path.write_text(content)
    r = run_futures_research(path, args.output)
    print(
        dumps(
            {
                "configuration": str(path),
                "counts": r["counts"],
                "synthetic": r["synthetic"],
                "failed": r["failed"],
                "results": [{k: v[k] for k in ("role", "status", "summary")} for v in r["results"]],
                "paper_trading_shortlist": r["paper_trading_shortlist"],
                "final_holdout": r["final_holdout"],
            }
        )
    )


if __name__ == "__main__":
    main()
