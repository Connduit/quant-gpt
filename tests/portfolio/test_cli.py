import json

import yaml

from quantlab.cli import main


def test_create_register_and_allocate_config(tmp_path, capsys):
    source = tmp_path / "validation.json"
    source.write_text(
        json.dumps(
            {
                "configuration": {"holdout": {"start": "2019-01-02"}},
                "candidates": [{"strategy_id": "candidate"}],
            }
        )
    )
    config = tmp_path / "portfolio.yaml"
    assert (
        main(
            [
                "portfolio",
                "create",
                "--output-config",
                str(config),
                "--source-validation",
                str(source),
                "--verified-inputs",
                str(tmp_path),
                "--start",
                "2017-01-03",
                "--end",
                "2018-12-31",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "portfolio",
                "register",
                "--portfolio-config",
                str(config),
                "--strategy-id",
                "candidate",
                "--name",
                "research",
            ]
        )
        == 0
    )
    doc = yaml.safe_load(config.read_text())
    assert doc["mode"] == "research" and doc["strategies"][0]["paper_approved"] is False
    before = config.read_bytes()
    assert (
        main(
            [
                "portfolio",
                "register",
                "--portfolio-config",
                str(config),
                "--strategy-id",
                "missing",
                "--name",
                "bad",
            ]
        )
        != 0
    )
    assert config.read_bytes() == before
    assert (
        main(
            ["portfolio", "allocate", "--portfolio-config", str(config), "--method", "risk_parity"]
        )
        == 0
    )
    assert yaml.safe_load(config.read_text())["allocation_methods"] == ["risk_parity"]
