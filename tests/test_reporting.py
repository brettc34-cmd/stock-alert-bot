import subprocess
from pathlib import Path

from storage.sqlite_store import init_db, save_signal
from engine.signal_models import Signal
from web.app import app


def test_generate_report_cli_and_reports_endpoint(tmp_path, monkeypatch):
    db_path = tmp_path / "alerts.db"
    reports_dir = tmp_path / "reports"
    conn = init_db(str(db_path))
    signal = Signal(
        ticker="NVDA",
        signal_type="breakout",
        brain="Quant",
        direction="up",
        confidence=88,
        priority="high",
        action_bias="WATCH",
        reason="test",
        why_it_matters="test",
        confirmations=["a", "b"],
        suppressions=[],
        metadata={"quote_timestamp": "2026-03-23T10:00:00+00:00"},
    )
    save_signal(
        conn,
        signal,
        analytics_context={
            "raw_quote": {"ticker": "NVDA", "currentPrice": 100},
            "brain_scores": {"Quant": 88},
            "ranking_score": 1380,
            "gating_reasons": ["low_confidence"],
        },
    )

    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            "python3",
            str(repo_root / "scripts" / "generate_report.py"),
            "--days",
            "7",
            "--db-path",
            str(db_path),
            "--reports-dir",
            str(reports_dir),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    generated = Path(result.stdout.strip())
    assert generated.exists()
    assert "report_" in generated.name

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("STOCK_ALERT_DASHBOARD_KEY", "test-key")
    client = app.test_client()
    listing = client.get("/reports", headers={"X-API-KEY": "test-key"})
    assert listing.status_code == 200
    assert generated.name.encode("utf-8") in listing.data


def test_reports_query_api_key_optional_behavior(tmp_path, monkeypatch):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    sample = reports_dir / "report_sample.md"
    sample.write_text("# sample", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("STOCK_ALERT_DASHBOARD_KEY", "test-key")
    client = app.test_client()

    monkeypatch.delenv("ENABLE_QUERY_API_KEY", raising=False)
    denied = client.get("/reports?key=test-key")
    assert denied.status_code == 403

    monkeypatch.setenv("ENABLE_QUERY_API_KEY", "1")
    allowed = client.get("/reports?key=test-key")
    assert allowed.status_code == 200
    assert b"report_sample.md" in allowed.data
