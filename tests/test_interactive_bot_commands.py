import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from interactive_discord_bot import _chat_answer, _looks_like_chat_addressed, _is_keyword_trigger, handle_config, handle_summary


class FakePermissions:
    def __init__(self, administrator: bool = False):
        self.administrator = administrator


class FakeUser:
    def __init__(self, user_id: int = 1, administrator: bool = False):
        self.id = user_id
        self.guild_permissions = FakePermissions(administrator=administrator)


class FakeResponse:
    def __init__(self):
        self.messages = []
        self._done = False

    async def send_message(self, content=None, embed=None, ephemeral=False):
        self.messages.append({"content": content, "embed": embed, "ephemeral": ephemeral})
        self._done = True

    async def defer(self, ephemeral=False, thinking=False):
        self.messages.append({"defer": True, "ephemeral": ephemeral, "thinking": thinking})
        self._done = True

    def is_done(self):
        return self._done


class FakeFollowup:
    def __init__(self):
        self.messages = []

    async def send(self, content=None, embed=None, ephemeral=False):
        self.messages.append({"content": content, "embed": embed, "ephemeral": ephemeral})


class FakeInteraction:
    def __init__(self, administrator: bool = False):
        self.user = FakeUser(administrator=administrator)
        self.guild = object()
        self.guild_id = 123
        self.response = FakeResponse()
        self.followup = FakeFollowup()


class FakeMessage:
    def __init__(self, content: str, guild: object | None = object(), mentions=None, reference=None):
        self.content = content
        self.guild = guild
        self.mentions = mentions or []
        self.reference = reference


def test_summary_command_returns_recent_alert_analytics(monkeypatch):
    interaction = FakeInteraction(administrator=True)
    monkeypatch.setattr(
        "interactive_discord_bot.alert_summary",
        lambda limit=5: {
            "last_run": "2026-03-23T12:00:00+00:00",
            "average_ranking_score": 1250.5,
            "last_cycle_raw_signal_count": 12,
            "last_cycle_approved_count": 3,
            "last_cycle_sent_count": 1,
            "last_cycle_webhook_sent_count": 1,
            "last_cycle_persist_failed_count": 0,
            "top_suppression_reasons": [("low_confidence", 8), ("duplicate_state", 3)],
            "recent_alerts": [
                {
                    "created_at": "2026-03-23 11:30:00",
                    "ticker": "NVDA",
                    "signal_type": "breakout",
                    "brain": "Quant",
                    "ranking_score": 1400,
                }
            ],
        },
    )

    asyncio.run(handle_summary(interaction, n=1))

    assert interaction.response.messages
    content = interaction.response.messages[0]["content"]
    assert "Average ranking score: 1250.5" in content
    assert "Last cycle: raw=12 | approved=3 | sent=1 | webhook_sent=1 | persist_failed=0" in content
    assert "NVDA" in content
    assert "low_confidence=8" in content


def test_summary_command_indicates_when_latest_run_sent_none(monkeypatch):
    interaction = FakeInteraction(administrator=True)
    monkeypatch.setattr(
        "interactive_discord_bot.alert_summary",
        lambda limit=5: {
            "last_run": "2026-03-24T17:15:17+00:00",
            "average_ranking_score": 850.0,
            "last_cycle_raw_signal_count": 26,
            "last_cycle_approved_count": 0,
            "last_cycle_sent_count": 0,
            "last_cycle_webhook_sent_count": 0,
            "last_cycle_persist_failed_count": 0,
            "top_suppression_reasons": [("low_confidence", 90)],
            "recent_alerts": [
                {
                    "created_at": "2026-03-18 16:01:48",
                    "ticker": "AXP",
                    "signal_type": "macro_divergence",
                    "brain": "Soros",
                    "ranking_score": 1000.0,
                }
            ],
        },
    )

    asyncio.run(handle_summary(interaction, n=1))

    content = interaction.response.messages[0]["content"]
    assert "Last cycle: raw=26 | approved=0 | sent=0 | webhook_sent=0 | persist_failed=0" in content
    assert "No alerts were approved" in content


def test_config_command_updates_market_hours_and_tickers(tmp_path, monkeypatch):
    interaction = FakeInteraction(administrator=True)
    monkeypatch.chdir(tmp_path)
    Path("config.json").write_text(
        json.dumps(
            {
                "stocks": ["AAPL", "NVDA"],
                "market_hours": {"open": "09:30", "close": "16:00", "timezone": "US/Eastern"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.com/webhook")

    asyncio.run(handle_config(interaction, market_open="10:00", market_close="15:45", tickers="MSFT, AMD"))

    updated = json.loads(Path("config.json").read_text(encoding="utf-8"))
    assert updated["market_hours"]["open"] == "10:00"
    assert updated["market_hours"]["close"] == "15:45"
    assert updated["stocks"] == ["MSFT", "AMD"]
    assert "Configuration updated." in interaction.response.messages[0]["content"]


def test_chat_answer_status_formats_snapshot(monkeypatch):
    monkeypatch.setattr(
        "interactive_discord_bot.status_snapshot",
        lambda: {
            "last_run": "2026-03-24T14:00:00+00:00",
            "raw_signal_count": 12,
            "approved_count": 4,
            "sent_count": 3,
            "suppressed_counts": {"low_confidence": 2},
        },
    )

    result = asyncio.run(_chat_answer("status", is_admin=False))

    assert "Status:" in result
    assert "Raw signals: 12" in result
    assert "Top suppressions: low_confidence=2" in result


def test_chat_answer_run_requires_admin():
    result = asyncio.run(_chat_answer("run", is_admin=False))
    assert "Admin role required" in result


def test_chat_answer_update_returns_preview(monkeypatch):
    monkeypatch.setattr(
        "interactive_discord_bot.build_market_update",
        lambda: SimpleNamespace(
            subject="Today's Market Update | Tue Mar 24, 2026",
            body=(
                "Big picture\nA concise summary.\n\n"
                "Major U.S. indexes\n- S&P 500: 1.00 (+0.10%)\n\n"
                "Rates and macro\n- U.S. 10-year Treasury yield: 4.40% (+1.00%)\n\n"
                "Commodities\n- WTI crude oil: $80.00 (+0.50%)\n\n"
                "Crypto\n- Bitcoin: $70000.00 (+1.00%)\n\n"
                "Market drivers\n- Fed and rates are in focus.\n\n"
                "What to watch next\n- Whether themes intensify."
            ),
            timestamp_label="2026-03-24 07:00 AM CDT",
            warnings=[],
        ),
    )

    result = asyncio.run(_chat_answer("update", is_admin=False))

    assert "Subject:" not in result
    assert "Timestamp:" not in result
    assert "Big picture" in result


def test_chat_answer_sp500_returns_overview(monkeypatch):
    monkeypatch.setattr(
        "interactive_discord_bot.build_sp500_overview",
        lambda: SimpleNamespace(
            body=(
                "S&P 500 Daily Overview\n"
                "- Index level: 6,577.49\n"
                "- Daily move: -0.05%\n"
                "- YTD: +7.84%\n"
                "- Top drivers: Fed expectations; leaders: Energy, Technology\n"
                "- Key headlines: CNBC Markets: Fed still expects to cut rates once this year\n"
                "- Bull case: the index is still positive YTD\n"
                "- Bear case: higher yields are a headwind\n"
                "- Bottom line: The S&P 500 is trading lower by -0.05%; the 10-year yield is near 4.40%.\n\n"
                "“This is general information only and not financial advice. For personal guidance, please talk to a licensed professional.”"
            ),
            warnings=[],
        ),
    )

    result = asyncio.run(_chat_answer("s&p", is_admin=False))

    assert result.startswith("S&P 500 Daily Overview")
    assert "- Index level:" in result
    assert "licensed professional" in result


def test_chat_answer_research_routes_to_ticker_research(monkeypatch):
    monkeypatch.setattr(
        "interactive_discord_bot.build_ticker_research",
        lambda ticker: f"Research: {ticker}\n- Brain consensus: bullish=2, bearish=1, risk_flags=1",
    )

    result = asyncio.run(_chat_answer("research nvda", is_admin=False))

    assert result.startswith("Research: NVDA")
    assert "Brain consensus" in result


def test_looks_like_chat_addressed_with_prefix(monkeypatch):
    monkeypatch.delenv("DISCORD_CHAT_MODE", raising=False)
    msg = FakeMessage("!sa status")
    assert _looks_like_chat_addressed(msg) is True


def test_looks_like_chat_addressed_channel_mode_all(monkeypatch):
    monkeypatch.setenv("DISCORD_CHAT_MODE", "all")
    msg = FakeMessage("hello")
    assert _looks_like_chat_addressed(msg) is True


def test_keyword_trigger_detects_known_commands():
    assert _is_keyword_trigger("status") is True
    assert _is_keyword_trigger("top 3") is True
    assert _is_keyword_trigger("s&p") is True
    assert _is_keyword_trigger("research nvda") is True
    assert _is_keyword_trigger("hello there") is False


def test_looks_like_chat_addressed_with_keyword_no_mention(monkeypatch):
    monkeypatch.delenv("DISCORD_CHAT_MODE", raising=False)
    msg = FakeMessage("summary 3")
    assert _looks_like_chat_addressed(msg) is True
