import pytest
from fastapi.testclient import TestClient

import main
import regime_detector
from tests.conftest import make_ohlcv


@pytest.fixture
def client(monkeypatch):
    async def fake_fetch(symbol, bars):
        if symbol == "BAD.NS":
            raise regime_detector.MarketDataError("No data for BAD.NS")
        return make_ohlcv()

    monkeypatch.setattr(regime_detector, "fetch_ohlcv", fake_fetch)
    monkeypatch.setattr(main, "cache", main.AnalysisCache())
    monkeypatch.setattr(main, "executor", None)
    monkeypatch.delenv("DHAN_CLIENT_ID", raising=False)
    monkeypatch.delenv("DHAN_ACCESS_TOKEN", raising=False)
    with TestClient(main.app) as c:
        yield c


def test_health(client):
    r = client.get("/health").json()
    assert r == {"status": "ok", "executor_running": False, "dhan_configured": False}


def test_status_idle(client):
    assert client.get("/status").json()["status"] == "IDLE"


def test_analysis_and_current(client):
    a = client.get("/regime/analysis", params={"symbol": "syn.ns"}).json()
    assert a["symbol"] == "SYN.NS"
    assert len(a["timeline"]) == len(a["bars"]) > 30
    cur = client.get("/regime/current", params={"symbol": "SYN.NS"}).json()
    assert cur["type"] in {"TRENDING", "MEAN_REVERTING", "VOLATILE", "CALM"}


def test_bad_symbol_is_422(client):
    r = client.get("/regime/analysis", params={"symbol": "BAD.NS"})
    assert r.status_code == 422
    assert "BAD.NS" in r.json()["detail"]


def test_live_without_credentials_is_rejected(client):
    r = client.post("/start", json={"symbol": "RELIANCE.NS", "capital": 100000, "mode": "LIVE"})
    assert r.status_code == 400
    assert "DHAN_CLIENT_ID" in r.json()["detail"]


def test_invalid_capital(client):
    assert client.post("/start", json={"symbol": "X.NS", "capital": -5}).status_code == 422


def test_start_stop_and_ws(client, monkeypatch):
    monkeypatch.setattr("executor.TICK_SECONDS", 300)
    r = client.post("/start", json={"symbol": "syn.ns", "capital": 100000, "mode": "PAPER"})
    assert r.json() == {"status": "started", "symbol": "SYN.NS", "mode": "PAPER"}
    assert client.post("/start", json={"symbol": "SYN.NS", "capital": 1}).status_code == 409
    with client.websocket_connect("/ws/live") as ws:
        snap = ws.receive_json()
        assert snap["status"]["symbol"] == "SYN.NS"
    st = client.post("/stop").json()
    assert st["status"] == "STOPPED"
    assert client.get("/health").json()["executor_running"] is False
