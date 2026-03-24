from datetime import datetime, timezone

from data.event_calendar import resolve_event_risk


def test_event_risk_activates_for_high_importance_events_in_horizon():
    now = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)
    calendar = {
        "events": [
            {"name": "CPI", "importance": "high", "datetime": "2026-04-01T18:00:00+00:00"},
            {"name": "Low importance", "importance": "low", "datetime": "2026-04-03T18:00:00+00:00"},
        ]
    }
    ctx = resolve_event_risk(now, horizon_hours=12, calendar=calendar)
    assert ctx.active is True
    assert len(ctx.events) == 1
