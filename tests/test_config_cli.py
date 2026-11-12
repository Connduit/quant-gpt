import json
import logging

import pytest

from quantlab.cli import main
from quantlab.config import load_settings
from quantlab.logging import JsonFormatter


def test_configuration_paths_and_overrides(tmp_path, monkeypatch):
    path = tmp_path / "data.toml"
    path.write_text('data_dir = "history"\nprovider = "fixture"\n')
    assert load_settings(path).data_dir == tmp_path / "history"
    monkeypatch.setenv("QUANTLAB_PROVIDER", "stooq")
    monkeypatch.setenv("QUANTLAB_TIMEOUT_SECONDS", "12")
    monkeypatch.setenv("QUANTLAB_DATA_DIR", str(tmp_path / "override"))
    settings = load_settings(path)
    assert settings.data_dir == tmp_path / "override"
    assert settings.provider == "stooq" and settings.timeout_seconds == 12


@pytest.mark.parametrize(
    "text",
    [
        "unexpected = 1",
        'provider = "bad"',
        "timeout_seconds = -1",
        "timeout_seconds = nan",
        'log_level = "SECRET"',
        'data_dir = ""',
    ],
)
def test_bad_config(tmp_path, text):
    path = tmp_path / "bad.toml"
    path.write_text(text)
    with pytest.raises(ValueError):
        load_settings(path)


def test_cli_offline_workflow(tmp_path, capsys):
    prefix = ["--data-dir", str(tmp_path)]
    args = prefix + [
        "download",
        "SYNTH",
        "--start",
        "2024-01-02",
        "--end",
        "2024-01-08",
        "--provider",
        "fixture",
    ]
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    snapshot = result["snapshot_id"]
    assert result["manifest"]["synthetic"] and not result["cached"]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["cached"]
    assert main(prefix + ["inspect", snapshot]) == 0
    assert json.loads(capsys.readouterr().out)["summary"][0]["rows"] == 5
    assert main(prefix + ["query", snapshot, "--sql", "SELECT sum(volume) AS v FROM bars"]) == 0
    # DuckDB sums int64 to Decimal128; JSON preserves exact decimal values as strings.
    assert json.loads(capsys.readouterr().out) == [{"v": "6000"}]


def test_cli_errors_are_json_stderr(tmp_path, capsys):
    assert main(["--data-dir", str(tmp_path), "inspect", "invalid"]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert json.loads(output.err)["event"] == "command_failed"


def test_structured_logging():
    record = logging.LogRecord("quantlab", logging.INFO, "", 0, "Stored %s", ("snapshot",), None)
    record.event = "created"
    value = json.loads(JsonFormatter().format(record))
    assert value["message"] == "Stored snapshot"
    assert value["timestamp"].endswith("+00:00") and value["event"] == "created"
