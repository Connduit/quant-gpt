"""Actionable schema errors without returning submitted values or contexts."""

import pytest
from fastapi.testclient import TestClient

from quantlab.web.app import create_app
from quantlab.web.catalog import Catalog

TOKEN = "validation-researcher-0000000000000000"


@pytest.fixture
def client(tmp_path):
    path = tmp_path / "catalog.yaml"
    path.write_text("artifacts: []\n")
    app = create_app(
        Catalog(path, tmp_path), state_root=tmp_path / "state", tokens={TOKEN: "researcher"}
    )
    with TestClient(app) as value:
        yield value


def body():
    return dict(
        source_job_id="a" * 32,
        model="ridge",
        start="2016-01-01",
        end="2019-12-31",
        research_mode="exploratory",
        confirmed=True,
    )


def test_holdout_schema_error_explains_required_new_training_run(client):
    response = client.post(
        "/api/v1/workflows/profitability", json=body(), headers={"Authorization": "Bearer " + TOKEN}
    )
    assert response.status_code == 422
    message = response.json()["error"]["message"]
    assert "protected 2019" in message
    assert "2018-12-31" in message and "2020-01-01" in message
    assert "source run" in message
    assert "ctx" not in response.text and "input" not in response.json()["error"]


@pytest.mark.parametrize(
    "change,expected",
    [
        ({"top_n": 0}, "top n"),
        ({"maximum_position_weight": 10}, "maximum position weight"),
        ({"start": "bad-date"}, "start"),
        ({"source_job_id": "bad-id"}, "saved ML report"),
        ({"start": "2018-12-31", "end": "2016-01-01"}, "start must be on or before end"),
    ],
)
def test_field_errors_are_specific(client, change, expected):
    response = client.post(
        "/api/v1/workflows/profitability",
        json={**body(), "end": "2018-12-31", **change},
        headers={"Authorization": "Bearer " + TOKEN},
    )
    assert response.status_code == 422
    assert expected in response.json()["error"]["message"]


def test_unknown_field_values_are_not_echoed(client):
    response = client.post(
        "/api/v1/workflows/profitability",
        json={**body(), "end": "2018-12-31", "secret-token-field": "DO-NOT-LEAK"},
        headers={"Authorization": "Bearer " + TOKEN},
    )
    assert response.status_code == 422
    assert "unsupported fields" in response.json()["error"]["message"]
    assert "DO-NOT-LEAK" not in response.text and "secret-token-field" not in response.text
