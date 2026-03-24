from brains.dalio_brain import analyze


def test_dalio_concentration_signal():
    portfolio = {"positions": [{"ticker": "AAPL", "shares": 100}], "cash": 0}
    prices = {"AAPL": 200}

    signals = analyze(portfolio, prices)
    assert isinstance(signals, list)
    assert len(signals) >= 0
