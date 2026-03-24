import json
from datetime import datetime, timezone

from engine.signal_models import Signal
from storage.sqlite_store import init_db, save_signal


def test_save_signal_persists_analytics_context(tmp_path):
    db_path = tmp_path / "alerts.db"
    conn = init_db(str(db_path))

    sig = Signal(
        ticker="NVDA",
        signal_type="breakout",
        brain="Quant",
        direction="up",
        confidence=80,
        priority="high",
        action_bias="WATCH",
        reason="test",
        why_it_matters="test",
        confirmations=["a", "b"],
        suppressions=[],
        metadata={"quote_timestamp": datetime.now(timezone.utc).isoformat()},
    )

    ctx = {
        "raw_quote": {"ticker": "NVDA", "currentPrice": 100.0, "volume": 1200},
        "brain_scores": {"Quant": 80, "Buffett": 65},
        "ranking_score": 1300,
        "gating_reasons": ["none"],
    }
    alert_id = save_signal(conn, sig, analytics_context=ctx)
    assert alert_id

    cur = conn.cursor()
    cur.execute(
        "SELECT alert_id, raw_quote, brain_scores, ranking_score, gating_reasons FROM signals WHERE alert_id = ?",
        (alert_id,),
    )
    row = cur.fetchone()

    assert row is not None
    assert row[0] == alert_id
    assert json.loads(row[1])["ticker"] == "NVDA"
    assert json.loads(row[2])["Quant"] == 80
    assert float(row[3]) == 1300.0
    assert json.loads(row[4]) == ["none"]


def test_init_db_backfills_null_ranking_scores(tmp_path):
    """Signals saved without ranking_score should be backfilled on next init_db call."""
    db_path = str(tmp_path / "alerts.db")
    conn = init_db(db_path)

    payload = json.dumps({
        "ticker": "AAPL",
        "brain": "Buffett",
        "signal_type": "buy_the_dip",
        "category": "buy_the_dip",
        "confidence": 40,
        "direction": "up",
        "priority": "moderate",
        "action_bias": "scale_in",
        "reason": "test",
        "why_it_matters": "test",
        "timestamp": "2026-03-18T14:00:00+00:00",
    })
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO signals (ticker, brain, category, confidence, summary, payload) VALUES (?,?,?,?,?,?)",
        ("AAPL", "Buffett", "buy_the_dip", 40, "test", payload),
    )
    conn.commit()

    # Re-init triggers the backfill pass
    conn2 = init_db(db_path)
    cur2 = conn2.cursor()
    cur2.execute("SELECT ranking_score FROM signals WHERE ticker='AAPL'")
    score = cur2.fetchone()[0]
    # buy_the_dip priority=4, confidence=40 => (40*10)+(4*100) = 800
    assert score == 800.0
