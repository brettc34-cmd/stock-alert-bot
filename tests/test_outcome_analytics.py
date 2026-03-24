import sqlite3

from storage.outcome_analytics import compute_brain_multipliers


def test_compute_brain_multipliers_returns_expected_bounds():
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE signals (alert_id TEXT PRIMARY KEY, brain TEXT);
        CREATE TABLE outcomes (
          alert_id TEXT PRIMARY KEY,
          ticker TEXT,
          signal_time TIMESTAMP,
          action_bias TEXT,
          outcome TEXT,
          close_time TIMESTAMP,
          return_pct REAL
        );
        """
    )
    for i in range(12):
        cur.execute("INSERT INTO signals(alert_id, brain) VALUES (?, ?)", (f"a{i}", "Druckenmiller"))
        cur.execute(
            "INSERT INTO outcomes(alert_id, ticker, signal_time, action_bias, outcome, close_time, return_pct) VALUES (?, 'AAPL', '2026-01-01', 'WATCH', 'win', '2026-01-02', ?)",
            (f"a{i}", 0.02 if i < 9 else -0.01),
        )
    conn.commit()

    multipliers = compute_brain_multipliers(conn, lookback=50)
    assert "Druckenmiller" in multipliers
    assert 0.85 <= multipliers["Druckenmiller"] <= 1.15
