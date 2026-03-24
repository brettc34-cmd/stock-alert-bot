from datetime import datetime, timezone

from alerts.digest_formatter import (
    derive_bias,
    format_digest_embed,
    format_digest_payload,
    format_digest_text,
    normalize_signal_label,
    normalize_strategy_label,
)
from engine.signal_models import Signal


def _sig(
    ticker: str,
    signal_type: str,
    brain: str,
    confidence: int,
    direction: str = "up",
    why: str = "test why",
    confirmations=None,
    metadata=None,
):
    return Signal(
        ticker=ticker,
        signal_type=signal_type,
        brain=brain,
        direction=direction,
        confidence=confidence,
        priority="moderate",
        action_bias="WATCH",
        reason=why,
        why_it_matters=why,
        confirmations=confirmations or ["confirm"],
        suppressions=[],
        metadata=metadata or {"quote_timestamp": datetime.now(timezone.utc).isoformat()},
    )


def test_label_normalization_maps_internal_names():
    assert normalize_signal_label("buy_the_dip") == "Buy Pullback"
    assert normalize_signal_label("breakout") == "Momentum Breakout"


def test_strategy_label_pro_vs_novice():
    assert normalize_strategy_label("Soros", mode="novice") == "Market Conditions"
    assert "Soros" in normalize_strategy_label("Soros", mode="pro")


def test_derive_bias_for_confluence_breakout_and_pullback():
    signals = [
        _sig("VLO", "buy_the_dip", "Buffett", 40),
        _sig("VLO", "breakout", "Druckenmiller", 78),
    ]
    assert derive_bias(signals) == "Breakout + Pullback Buy"


def test_digest_text_dynamic_title_for_single_top_opportunity():
    signals = [_sig("AXP", "dip", "Quant-Ladder", 62)]
    out = format_digest_text(signals, mode="pro")
    assert "Top Opportunity: 1" in out


def test_digest_text_groups_by_ticker_and_shows_agreement_confluence():
    signals = [
        _sig("VLO", "buy_the_dip", "Buffett", 40),
        _sig("VLO", "breakout", "Druckenmiller", 78, confirmations=["volume_confirmed", "ma_align"]),
        _sig("AXP", "dip", "Quant-Ladder", 50, metadata={"crossed_level": 300.99}),
    ]
    out = format_digest_text(signals, mode="pro")
    assert "VLO" in out
    assert "Active signals:" in out
    assert "Aligned signals:" in out
    assert "Signal Agreement:" in out
    assert "Breakout + Pullback Buy" in out
    assert "Key Levels:" in out


def test_digest_text_mixed_bias_uses_yellow_icon_and_low_agreement():
    signals = [
        _sig("AXP", "buy_the_dip", "Buffett", 62, direction="up"),
        _sig("AXP", "risk", "Soros", 65, direction="down"),
    ]
    out = format_digest_text(signals, mode="pro")
    assert "🟡 AXP — Bias: Mixed / Needs Confirmation" in out
    assert "Signal Agreement: Low" in out


def test_digest_text_dynamic_why_it_matters_is_data_driven():
    signals = [
        _sig("VLO", "breakout", "Druckenmiller", 78, confirmations=["volume_confirmed", "ma_align"]),
    ]
    out = format_digest_text(signals, mode="pro")
    assert "Volume confirmed breakout with moving-average alignment suggests continuation." in out


def test_digest_text_novice_mode_adds_extra_explanation_line():
    signals = [
        _sig("AXP", "dip", "Quant-Ladder", 62),
        _sig("AAPL", "buy_the_dip", "Buffett", 58),
    ]
    out = format_digest_text(signals, mode="novice")
    assert "What this means:" in out


def test_legend_completeness():
    signals = [_sig("AXP", "dip", "Quant-Ladder", 62)]
    out = format_digest_text(signals, mode="pro")
    assert "🟢 bullish" in out
    assert "🟡 mixed/watch" in out
    assert "🔴 bearish risk" in out
    assert "⭐ confidence" in out


def test_digest_embed_contains_structured_fields_and_color_mapping():
    signals = [
        _sig("VLO", "buy_the_dip", "Buffett", 40),
        _sig("VLO", "breakout", "Druckenmiller", 78),
        _sig("CVX", "breakout", "Druckenmiller", 72),
    ]
    embed = format_digest_embed(signals, use_colored_embed=True)
    assert embed["title"]
    assert "fields" in embed
    assert len(embed["fields"]) >= 1
    assert embed["color"] == 0x1F9D55


def test_embed_and_text_coherence_on_top_ticker():
    signals = [
        _sig("CVX", "breakout", "Druckenmiller", 72),
        _sig("AAPL", "dip", "Buffett", 58),
    ]
    text = format_digest_text(signals, mode="pro")
    embed = format_digest_embed(signals, mode="pro")
    assert "CVX" in text
    assert any(field.get("name") == "CVX" for field in embed.get("fields", []))


def test_digest_payload_embed_mode_includes_fallback_content():
    signals = [_sig("AXP", "dip", "Quant-Ladder", 62)]
    payload = format_digest_payload(signals, prefer_embed=True)
    assert "embeds" in payload
    assert payload.get("fallback_content")


def test_digest_text_truncates_to_discord_limit():
    signals = [_sig(f"T{i}", "buy_the_dip", "Buffett", 60, why="x" * 200) for i in range(30)]
    out = format_digest_text(signals, mode="novice")
    assert len(out) <= 1900
