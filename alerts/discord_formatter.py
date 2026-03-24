import json
import requests
from typing import Any, Dict, List, Optional

from engine.signal_models import Signal


def send_discord_message(webhook_url: str, message_text: str) -> bool:
    """Send a message to Discord via webhook. Returns True on success."""
    payload = {"content": message_text}
    return send_discord_payload(webhook_url, payload)


def send_discord_payload(webhook_url: str, payload: Dict[str, Any]) -> bool:
    """Send a Discord webhook payload supporting content and embeds."""
    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        if response.status_code in (200, 204):
            print("  Discord alert sent successfully.")
            return True
        else:
            print(f"  Discord alert failed: {response.status_code} {response.text}")
            return False
    except Exception as e:
        print(f"  Discord send exception: {e}")
        return False


def format_signal(signal: Signal) -> str:
    """Convert a `Signal` into a premium Discord-readable message string."""
    signal_emoji = {
        "breakout": "🚀",
        "trend_continuation": "🚀",
        "dip": "🛒",
        "buy_the_dip": "🛒",
        "quality_dip": "🛒",
        "risk": "⚠️",
        "concentration_risk": "⚠️",
        "overlap_exposure_warning": "⚠️",
        "trim": "✂️",
        "trim_watch": "✂️",
        "macro_divergence": "🌐",
        "caution": "🧭",
    }
    priority = (signal.priority or "moderate").lower()
    severity = {
        "high": "🚨",
        "strong": "🔵",
        "moderate": "🟡",
        "low": "⚪",
    }.get(priority, "🔔")
    icon = signal_emoji.get(signal.signal_type, "🔔")
    header = f"{severity} {icon} {signal.signal_type.upper()} | {signal.ticker} | {priority.upper()}"

    body = [header]
    body.append(f"- Confidence: {int(signal.confidence)} / 100")
    body.append(f"- Priority: {priority.upper()}")
    if signal.price is not None:
        body.append(f"- Price: ${signal.price:,.2f}")
    if signal.change_pct is not None:
        body.append(f"- Move: {signal.change_pct:+.2%}")
    if signal.volume_ratio is not None:
        body.append(f"- Volume: {signal.volume_ratio:.2f}x normal")
    body.append(f"- Brain(s): {signal.brain}")
    if signal.confirmations:
        conf_display = ", ".join(signal.confirmations[:4])
        suffix = f" (+{len(signal.confirmations) - 4} more)" if len(signal.confirmations) > 4 else ""
        body.append(f"- Confirmations: {conf_display}{suffix}")
    body.append(f"- Why it matters: {signal.why_it_matters}")
    body.append(f"- Action bias: {signal.action_bias}")
    if signal.portfolio_note:
        body.append(f"- Portfolio note: {signal.portfolio_note}")

    risk_note = []
    if signal.suppressions:
        risk_note.append(f"suppression history={', '.join(signal.suppressions)}")
    earnings_days = signal.metadata.get("earnings_days") if isinstance(signal.metadata, dict) else None
    earnings_window = (signal.metadata or {}).get("earnings_risk_window_days", 14) if isinstance(signal.metadata, dict) else 14
    if isinstance(earnings_days, (int, float)) and 0 <= earnings_days <= earnings_window:
        risk_note.append(f"earnings in {int(earnings_days)}d ⚡")
    if risk_note:
        body.append(f"- Risk note: {'; '.join(risk_note)}")
    body.append(f"- Reason: {signal.reason}")

    return "\n".join(body)
