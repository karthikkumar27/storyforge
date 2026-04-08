# tests/test_main.py
import pytest
from unittest.mock import patch


@patch("main.run_pipeline")
def test_run_endpoint_returns_200_on_success(mock_pipeline):
    mock_pipeline.return_value = {"status": "done", "youtube_url": "https://youtube.com/watch?v=abc"}

    from main import app
    client = app.test_client()
    resp = client.post("/run")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "done"


@patch("main.run_pipeline")
def test_run_endpoint_returns_200_for_no_pending(mock_pipeline):
    mock_pipeline.return_value = {"status": "no_pending_rows"}

    from main import app
    client = app.test_client()
    resp = client.post("/run")

    assert resp.status_code == 200
    assert resp.get_json()["status"] == "no_pending_rows"


@patch("main.run_pipeline")
def test_run_endpoint_returns_500_on_exception(mock_pipeline):
    mock_pipeline.side_effect = RuntimeError("Kling API down")

    from main import app
    client = app.test_client()
    resp = client.post("/run")

    assert resp.status_code == 500
    assert "Kling API down" in resp.get_json()["error"]


def test_health_endpoint_returns_ok():
    from main import app
    client = app.test_client()
    resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"
