def test_health_returns_200(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["client_id"] == "test"


def test_health_includes_version(client):
    resp = client.get("/health")
    assert "version" in resp.json()
