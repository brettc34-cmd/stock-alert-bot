from web.app import app


def test_pm_dashboard_requires_key(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("STOCK_ALERT_DASHBOARD_KEY", "test-key")
    client = app.test_client()
    denied = client.get("/pm")
    assert denied.status_code == 403


def test_pm_dashboard_returns_payload(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("STOCK_ALERT_DASHBOARD_KEY", "test-key")
    client = app.test_client()
    resp = client.get("/pm", headers={"X-API-KEY": "test-key"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "execution" in data
    assert "attribution" in data
    assert "walkforward" in data
