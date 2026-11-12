"""Atomic immutable snapshots with verified normalized and original payloads."""

import hashlib
import json
import re
import shutil
import tempfile
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import duckdb
import polars as pl

from quantlab.data.providers.base import DataRequest, Download


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class SnapshotStore:
    def __init__(self, root: Path) -> None:
        self.root = root / "snapshots"

    def _path(self, snapshot_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{64}", snapshot_id):
            raise ValueError("snapshot_id must be a full SHA-256 identifier")
        return self.root / snapshot_id

    def manifest(self, snapshot_id: str) -> dict:
        directory = self._path(snapshot_id)
        metadata = json.loads((directory / "manifest.json").read_text())
        if digest(json.dumps(metadata, sort_keys=True).encode()) != snapshot_id:
            raise ValueError("Snapshot manifest checksum mismatch")
        for filename, key in (("bars.parquet", "parquet_sha256"), ("source.csv", "raw_sha256")):
            if digest((directory / filename).read_bytes()) != metadata[key]:
                raise ValueError(f"Snapshot checksum mismatch: {filename}")
        return metadata

    def prefix_manifest(self, snapshot_id: str, cutoff) -> dict:
        """Check identity and declared prefix bounds without opening either price payload."""
        directory = self._path(snapshot_id)
        metadata = json.loads((directory / "manifest.json").read_text())
        if digest(json.dumps(metadata, sort_keys=True).encode()) != snapshot_id:
            raise ValueError("Prefix manifest checksum mismatch")
        if metadata["request"]["end"] >= str(cutoff):
            raise ValueError("Prefix-only research cannot open a holdout archive")
        return metadata

    def find_cached(self, provider: str, request: DataRequest) -> str | None:
        candidates = []
        for path in self.root.glob("*/manifest.json"):
            if not re.fullmatch(r"[a-f0-9]{64}", path.parent.name):
                continue
            metadata = self.manifest(path.parent.name)
            if metadata["provider"] == provider and metadata["request"] == request.as_dict():
                candidates.append((metadata["retrieved_at"], path.parent.name))
        return max(candidates)[1] if candidates else None

    def write(
        self,
        provider: str,
        request: DataRequest,
        download: Download,
        frame: pl.DataFrame,
        parent: str | None = None,
    ) -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".pending-", dir=self.root))
        try:
            frame.write_parquet(temporary / "bars.parquet", compression="zstd")
            (temporary / "source.csv").write_bytes(download.raw)
            metadata = {
                "schema_version": 1,
                "software_versions": {
                    name: version(name)
                    for name in (
                        "quant-research-lab",
                        "exchange-calendars",
                        "polars",
                        "pyarrow",
                        "duckdb",
                    )
                },
                "provider": provider,
                "request": request.as_dict(),
                "retrieved_at": datetime.now(UTC).isoformat(),
                "source": download.source,
                "price_basis": download.price_basis,
                "synthetic": download.synthetic,
                "calendar": "XNYS",
                "interval": "1d",
                "row_count": frame.height,
                "raw_sha256": digest(download.raw),
                "parquet_sha256": digest((temporary / "bars.parquet").read_bytes()),
                "parent_snapshot": parent,
                "availability_policy": "following_calendar_day_midnight_New_York_bound",
                "point_in_time": False,
                "corporate_actions_included": False,
                "universe_membership_included": False,
            }
            serialized = json.dumps(metadata, sort_keys=True)
            snapshot_id = digest(serialized.encode())
            (temporary / "manifest.json").write_text(serialized + "\n")
            temporary.rename(self._path(snapshot_id))
            return snapshot_id
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    def read(self, snapshot_id: str) -> pl.DataFrame:
        self.manifest(snapshot_id)
        return pl.read_parquet(self._path(snapshot_id) / "bars.parquet")

    def query(self, snapshot_id: str, sql: str) -> pl.DataFrame:
        frame = self.read(snapshot_id)
        # External file, network and extension access is disabled for user queries.
        with duckdb.connect(config={"enable_external_access": "false"}) as connection:
            statements = connection.extract_statements(sql)
            if len(statements) != 1 or statements[0].type != duckdb.StatementType.SELECT:
                raise ValueError("Only a single SELECT query against bars is supported")
            connection.register("bars", frame.to_arrow())
            return pl.from_arrow(connection.sql(sql).to_arrow_table())
