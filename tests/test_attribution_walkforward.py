import sqlite3

from services.attribution import attribution_summary
from services.walkforward import walkforward_summary


def test_attribution_and_walkforward_with_missing_tables_is_safe():
    conn = sqlite3.connect(":memory:")
    attr = attribution_summary(conn)
    wf = walkforward_summary(conn)
    assert isinstance(attr, dict)
    assert isinstance(wf, dict)
    assert "by_brain" in attr
    assert "windows" in wf
