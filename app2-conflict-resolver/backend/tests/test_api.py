"""FastAPI endpoints via TestClient (offline — analysis served from warm cache)."""
import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Isolate resolutions writes to a temp file.
    monkeypatch.setattr(main, "RESOLUTIONS_PATH", tmp_path / "resolutions.json")
    with TestClient(main.app) as c:  # runs lifespan → loads analysis
        yield c


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_conflicts_shape(client):
    d = client.get("/api/conflicts").json()
    assert d["count"] > 0
    assert d["meta"]["pair_count"] > 0
    assert isinstance(d["documents"], dict) and d["documents"]


def test_usage_endpoint(client):
    d = client.get("/api/usage").json()
    assert "total_cost_usd" in d
    assert d["call_count"] >= 0


def test_resolution_roundtrip(client):
    r = client.post("/api/resolve", json={
        "conflict_id": "X1", "decision": "appliquer 3 mois", "resolved_by": "Inspecteur",
    })
    assert r.json()["status"] == "saved"
    stored = client.get("/api/resolutions").json()
    assert stored["X1"]["decision"] == "appliquer 3 mois"
    assert stored["X1"]["resolved_by"] == "Inspecteur"
