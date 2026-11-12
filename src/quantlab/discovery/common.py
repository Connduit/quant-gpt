import hashlib
import json
import subprocess
from pathlib import Path

from quantlab.backtesting.report import dumps, json_default


def fingerprint(value) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        default=lambda v: str(v) if isinstance(v, Path) else json_default(v),
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def code_version() -> dict:
    package = Path(__file__).resolve().parents[1]
    sources = {
        str(p.relative_to(package)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(package.rglob("*.py"))
    }
    try:
        commit = subprocess.check_output(
            ["git", "-C", str(package), "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    return {"source_sha256": fingerprint(sources), "git_commit": commit}


def write_json(path: Path, value) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(dumps(value) + "\n")
    temporary.replace(path)


def read_json(path: Path):
    return json.loads(path.read_text())
