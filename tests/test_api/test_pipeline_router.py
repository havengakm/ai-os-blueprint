def test_pipeline_trigger_requires_cron_secret(client):
    r = client.post("/api/pipeline/trigger")
    assert r.status_code == 401


def test_pipeline_trigger_accepts_valid_secret(client):
    r = client.post(
        "/api/pipeline/trigger",
        headers={"X-Cron-Secret": "test-cron"},
        json={"stage": "pull", "dry_run": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["stage"] == "pull"
    assert body["dry_run"] is True
    assert "status" in body
