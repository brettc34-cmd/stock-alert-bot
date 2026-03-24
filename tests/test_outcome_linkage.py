from datetime import datetime, timezone

from engine.signal_models import Signal
from storage.sqlite_store import init_db, save_signal
from storage.outcome_tracker import init_outcomes_db, evaluate_pending_outcomes


def test_outcome_is_linked_by_alert_id(tmp_path):
    db_path = tmp_path / "alerts.db"
    conn_signals = init_db(str(db_path))
    conn_outcomes = init_outcomes_db(str(db_path))

    signal = Signal(
        ticker="NVDA",
        signal_type="breakout",
        brain="Quant",
        direction="up",
        confidence=75,
        priority="strong",
        action_bias="WATCH",
        reason="test",
        why_it_matters="test",
        confirmations=["breakout_confirmed", "volume_unusual"],
        suppressions=[],
        price=100.0,
        metadata={"quote_timestamp": datetime.now(timezone.utc).isoformat()},
    )

    alert_id = save_signal(conn_signals, signal)
    assert alert_id

    evaluate_pending_outcomes(conn_outcomes)

    cur = conn_outcomes.cursor()
    cur.execute("SELECT alert_id, ticker, outcome FROM outcomes WHERE alert_id = ?", (alert_id,))
    row = cur.fetchone()

    assert row is not None
    assert row[0] == alert_id
    assert row[1] == "NVDA"
    assert row[2] in {"win", "loss"}
