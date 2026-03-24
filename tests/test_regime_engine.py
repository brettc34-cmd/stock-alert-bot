from engine.regime_engine import classify_regime, regime_allows_signal


def test_classify_regime_risk_off_when_vix_high_and_spx_below_ma200():
    regime = classify_regime({
        "vix": 32.0,
        "spx_price": 4800.0,
        "spx_ma200": 5000.0,
        "yield_curve_10y_3m": -0.01,
        "credit_risk_proxy_20d": -0.02,
    })
    assert regime["regime"] == "risk_off"


def test_regime_policy_blocks_add_signals_in_risk_off():
    assert regime_allows_signal("breakout", "risk_off") is False
    assert regime_allows_signal("dip", "risk_off") is False
    assert regime_allows_signal("risk", "risk_off") is True
