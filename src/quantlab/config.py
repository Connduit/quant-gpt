"""Small, strict TOML configuration with explicit environment overrides."""

import math
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path("data")
    provider: str = "stooq"
    timeout_seconds: float = 30.0
    log_level: str = "INFO"


def load_settings(path: Path | None = None) -> Settings:
    values = {}
    base = Path.cwd()
    if path is not None:
        with path.open("rb") as handle:
            values = tomllib.load(handle)
        base = path.resolve().parent
    unknown = set(values) - {"data_dir", "provider", "timeout_seconds", "log_level"}
    if unknown:
        raise ValueError(f"Unknown configuration keys: {', '.join(sorted(unknown))}")
    for key in ("data_dir", "provider", "timeout_seconds", "log_level"):
        override = os.environ.get(f"QUANTLAB_{key.upper()}")
        if override is not None:
            values[key] = override
    directory = values.get("data_dir", "data")
    if not isinstance(directory, str) or not directory.strip():
        raise ValueError("data_dir must be a nonempty path")
    data_dir = Path(directory).expanduser()
    if not data_dir.is_absolute():
        # Environment path overrides are relative to the invoking directory.
        root = Path.cwd() if "QUANTLAB_DATA_DIR" in os.environ else base
        data_dir = root / data_dir
    provider = values.get("provider", "stooq")
    if provider not in ("stooq", "fixture"):
        raise ValueError("provider must be stooq or fixture")
    timeout = float(values.get("timeout_seconds", 30))
    if not math.isfinite(timeout) or not 0 < timeout <= 300:
        raise ValueError("timeout_seconds must be between 0 and 300")
    level = values.get("log_level", "INFO")
    if level not in ("DEBUG", "INFO", "WARNING", "ERROR"):
        raise ValueError("Unsupported log_level")
    return Settings(data_dir.resolve(), provider, timeout, level)
