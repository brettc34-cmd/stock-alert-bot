"""Tests for premium signal completion and state management."""

import pytest
from datetime import datetime, timezone
from engine.signal_models import Signal
from engine.signal_completion import (
    complete_signal_for_premium_quality,
    derive_confirmations_from_evidence,
    validate_signal_completeness,
    VALID_CONFIRMATION_TYPES,
)
from engine.state_manager import (
    initialize_premium_state,
    record_cycle_error,
    update_cycle_metrics,
    sanitize_state_for_json,
)


def test_derive_confirmations_from_evidence():
    """Test that confirmations are correctly extracted from evidence."""
    evidence = [
        {"type": "breakout_confirmed", "value": True},
        {"type": "volume_unusual", "value": 2.5},
        {"type": "invalid_type", "value": "ignored"},
    ]
    confirmations = derive_confirmations_from_evidence(evidence)
    assert "breakout_confirmed" in confirmations
    assert "volume_unusual" in confirmations
    assert "invalid_type" not in confirmations


def test_complete_signal_fills_mandatory_fields():
    """Test that signal completion populates all mandatory fields."""
    signal = Signal(
        ticker="NVDA",
        signal_type="breakout",
        brain="Quant",
        direction="up",
        confidence=75,
        priority="strong",
        action_bias="HOLD_ADD_ON_STRENGTH",
        reason="Volume spike detected",
        why_it_matters="",
        confirmations=[],
        suppressions=[],
        metadata={},
        price=100.0,
        change_pct=2.5,
    )
    
    quotes = {
        "NVDA": {
            "timestamp": datetime.now(timezone.utc),
            "sector": "Technology",
            "iv_rank": 65,
        }
    }
    
    completed, notes = complete_signal_for_premium_quality(signal, {"NVDA": quotes["NVDA"]})
    
    # Verify mandatory fields are set
    assert completed.metadata.get("quote_timestamp") is not None
    assert completed.metadata.get("thesis_id") is not None
    assert completed.metadata.get("sector") == "Technology"
    assert completed.metadata.get("invalidation_price") is not None
    assert len(completed.reason) > 0
    assert len(completed.why_it_matters) > 0


def test_signal_completeness_validation():
    """Test that signal completeness validation catches missing fields."""
    invalid_signal = Signal(
        ticker="",  # Missing ticker
        signal_type="",
        brain="",
        direction="invalid",
        confidence=75,  # Valid after post_init clamping
        priority="",
        action_bias="",
        reason="",
        why_it_matters="",
    )
    
    is_complete, issues = validate_signal_completeness(invalid_signal)
    assert is_complete is False
    assert len(issues) > 0
    assert any("missing ticker" in issue for issue in issues)
    assert any("direction invalid" in issue for issue in issues)


def test_premium_state_initialization():
    """Test that state initialization creates all required keys."""
    state = initialize_premium_state()
    
    # Verify all schema keys exist
    assert "last_run" in state
    assert isinstance(state["last_run"], str)
    assert "suppression_counts" in state
    assert isinstance(state["suppression_counts"], dict)
    assert "cycle_metrics" in state
    assert isinstance(state["cycle_metrics"], dict)
    assert "sent_signals" in state
    assert "cooldowns" in state
    assert "error_details" in state
    assert isinstance(state["error_details"], list)


def test_premium_state_upgrade_from_legacy():
    """Test that legacy state is upgraded to premium schema."""
    legacy_state = {
        "last_run": datetime.now(timezone.utc).isoformat(),
        "some_legacy_field": "value",
    }
    
    upgraded = initialize_premium_state(legacy_state)
    
    # Old fields preserved
    assert upgraded.get("some_legacy_field") == "value"
    
    # New fields added
    assert "suppression_counts" in upgraded
    assert "cycle_metrics" in upgraded
    assert "error_details" in upgraded


def test_record_cycle_error():
    """Test error recording in state."""
    state = initialize_premium_state()
    
    record_cycle_error(state, "Test error message", "test_error_type")
    
    assert state["errors"] == 1
    assert state["last_error"] == "Test error message"
    assert len(state["error_details"]) == 1
    assert state["error_details"][0]["type"] == "test_error_type"


def test_update_cycle_metrics():
    """Test cycle metrics recording."""
    state = initialize_premium_state()
    
    update_cycle_metrics(
        state,
        raw_count=100,
        approved_count=50,
        sent_count=10,
        webhook_sent_count=10,
        persist_failed_count=0,
        suppressed_counts={"cooldown_active": 30, "low_confidence": 10},
        regime="bullish",
        regime_drivers=["strong_volume"],
        event_risk_active=False,
    )
    
    metrics = state["cycle_metrics"]
    assert metrics["raw_signal_count"] == 100
    assert metrics["approved_signal_count"] == 50
    assert metrics["sent_signal_count"] == 10
    assert metrics["total_suppressed"] == 40
    assert metrics["market_regime"] == "bullish"


def test_sanitize_state_for_json():
    """Test that datetime objects are converted to ISO strings."""
    state = initialize_premium_state()
    state["last_run"] = datetime.now(timezone.utc)  # Set as datetime object
    
    sanitized = sanitize_state_for_json(state)
    
    # Verify datetime was converted to ISO string
    assert isinstance(sanitized["last_run"], str)
    assert "T" in sanitized["last_run"]  # ISO format


def test_invalid_confirmation_types_excluded():
    """Test that invalid confirmation types are not in VALID_CONFIRMATION_TYPES."""
    assert "invalid_type" not in VALID_CONFIRMATION_TYPES
    assert "breakout_confirmed" in VALID_CONFIRMATION_TYPES
    assert "volume_unusual" in VALID_CONFIRMATION_TYPES


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
