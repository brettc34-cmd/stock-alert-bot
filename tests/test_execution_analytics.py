from datetime import datetime, timezone, timedelta

from services.execution_analytics import init_execution_db, record_execution_metric, execution_summary


def test_execution_metrics_record_and_summarize(tmp_path):
    conn = init_execution_db(str(tmp_path / "alerts.db"))
    t0 = datetime.now(timezone.utc)
    t1 = t0 + timedelta(milliseconds=350)
    record_execution_metric(
        conn,
        alert_id="a1",
        ticker="AAPL",
        decision_time=t0,
        dispatch_time=t1,
        decision_price=100.0,
        dispatch_price=100.1,
    )
    summary = execution_summary(conn)
    assert summary["count"] == 1
    assert summary["avg_latency_ms"] >= 350
