from fastapi.testclient import TestClient

from tinli_api.main import app

client = TestClient(app)


def test_healthz_live(monkeypatch):
    monkeypatch.delenv("TINLI_DEMO", raising=False)
    monkeypatch.delenv("TINLI_READONLY", raising=False)
    r = client.get("/healthz")
    assert r.status_code == 200
    # stream False here: TestClient without lifespan never starts the hub
    assert r.json() == {"status": "ok", "mode": "live", "readonly": False, "stream": False, "byok": False}


def test_healthz_demo(monkeypatch):
    monkeypatch.setenv("TINLI_DEMO", "1")
    r = client.get("/healthz")
    assert r.json()["mode"] == "demo"
