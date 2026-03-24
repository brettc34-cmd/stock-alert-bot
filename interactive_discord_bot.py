"""Interactive Discord bot for stock-alert-bot operations."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from typing import Any, List

try:
    import discord
    from discord import app_commands
    from discord.ext import commands
except Exception:  # pragma: no cover
    class _DummyEmbed:
        def __init__(self, title: str = "", color: Any = None):
            self.title = title
            self.color = color
            self.fields = []

        def add_field(self, name: str, value: str, inline: bool = False) -> None:
            self.fields.append({"name": name, "value": value, "inline": inline})

    class _DummyColor:
        @staticmethod
        def blue() -> int:
            return 0

    class _DummyIntents:
        @staticmethod
        def default():
            return None

    class _DummyTree:
        def command(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator

        async def sync(self):
            return None

    class _DummyBotBase:
        def __init__(self, *args, **kwargs) -> None:
            self.tree = _DummyTree()
            self.user = "dummy-bot"

        def event(self, func):
            return func

        def run(self, token: str) -> None:
            return None

    class _DummyCommandsModule:
        Bot = _DummyBotBase

    class _DummyAppCommands:
        @staticmethod
        def describe(**kwargs):
            def decorator(func):
                return func
            return decorator

    class _DummyDiscordModule:
        Embed = _DummyEmbed
        Color = _DummyColor
        Intents = _DummyIntents
        Interaction = object

    discord = _DummyDiscordModule()
    app_commands = _DummyAppCommands()
    commands = _DummyCommandsModule()

try:
    from prometheus_client import start_http_server
except Exception:  # pragma: no cover
    def start_http_server(*args, **kwargs):
        return None

from alerts.digest_formatter import format_digest
from market_update import build_market_update, format_discord_update
from sp500_overview import build_sp500_overview
from services.core import (
    alert_summary,
    get_market_session_config,
    get_top_signals,
    run_pipeline,
    status_snapshot,
    update_market_config,
)
from services.metrics import record_interactive_command
from services.run_cooldown_store import RunCooldownStore
from telemetry import configure_opentelemetry, get_tracer
from utils.config import get_discord_bot_token


if os.path.exists(".env"):
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        pass

os.environ.setdefault("DISABLE_INTERNAL_SCHEDULER", "1")
configure_opentelemetry(service_name="stock-alert-bot-interactive")
tracer = get_tracer("interactive_discord_bot")

try:
    start_http_server(int(os.environ.get("INTERACTIVE_BOT_METRICS_PORT", "9101")))
except Exception as exc:
    logging.getLogger("interactive_discord_bot").warning("metrics_server_start_failed error=%s", exc)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("interactive_discord_bot")

RUN_COOLDOWN_SECONDS = 120
run_cooldown_store = RunCooldownStore()


class StockAlertBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        try:
            intents.message_content = True
        except Exception:
            pass
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self) -> None:
        guild_id_raw = os.environ.get("DISCORD_GUILD_ID")
        if guild_id_raw:
            try:
                guild_id = int(guild_id_raw)
                guild = discord.Object(id=guild_id)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                logger.info("slash_commands_synced_guild guild_id=%s", guild_id)
                return
            except Exception as exc:
                logger.warning("slash_commands_sync_guild_failed guild_id=%s error=%s", guild_id_raw, exc)
        await self.tree.sync()
        logger.info("slash_commands_synced_global")


bot = StockAlertBot()


def _set_span_attr(span: Any, key: str, value: Any) -> None:
    if span is None:
        return
    setter = getattr(span, "set_attribute", None)
    if callable(setter):
        try:
            setter(key, value)
        except Exception:
            pass


def _status_embed(data: dict[str, object]) -> Any:
    embed = discord.Embed(title="Stock Alert Bot Status", color=discord.Color.blue())
    embed.add_field(name="Last Run", value=str(data.get("last_run") or "N/A"), inline=False)
    embed.add_field(name="Raw Signals", value=str(data.get("raw_signal_count", 0)), inline=True)
    embed.add_field(name="Approved", value=str(data.get("approved_count", 0)), inline=True)
    embed.add_field(name="Sent", value=str(data.get("sent_count", 0)), inline=True)

    suppressions = data.get("suppressed_counts", {}) or {}
    if isinstance(suppressions, dict) and suppressions:
        top = sorted(suppressions.items(), key=lambda kv: kv[1], reverse=True)[:3]
        embed.add_field(
            name="Top Suppressions",
            value="\n".join(f"{k}: {v}" for k, v in top),
            inline=False,
        )
    else:
        embed.add_field(name="Top Suppressions", value="None", inline=False)
    return embed


def _parse_tickers(value: str | None) -> List[str] | None:
    if value is None:
        return None
    tickers = [item.strip().upper() for item in value.split(",") if item.strip()]
    return tickers


def _looks_like_chat_addressed(message: Any) -> bool:
    mode = (os.environ.get("DISCORD_CHAT_MODE", "mention") or "mention").strip().lower()
    guild = getattr(message, "guild", None)
    if guild is None:
        return True

    if mode in {"all", "channel", "always"}:
        return True

    if _is_reply_to_bot(message):
        return True

    mentions = getattr(message, "mentions", []) or []
    bot_user = getattr(bot, "user", None)
    if bot_user is not None and any(getattr(m, "id", None) == getattr(bot_user, "id", None) for m in mentions):
        return True

    content = (getattr(message, "content", "") or "").strip().lower()
    if _is_keyword_trigger(content):
        return True
    prefixes = ("!sa", "!bot", "stockbot", "stock bot")
    return any(content.startswith(p) for p in prefixes)


def _extract_chat_query(message: Any) -> str:
    content = (getattr(message, "content", "") or "").strip()
    if not content:
        return ""

    content = re.sub(r"^<@!?\d+>\s*", "", content).strip()
    lower = content.lower()
    for prefix in ("!sa", "!bot", "stockbot", "stock bot"):
        if lower.startswith(prefix):
            return content[len(prefix):].strip()
    return content


def _is_keyword_trigger(content: str) -> bool:
    triggers = (
        "status",
        "update",
        "s&p",
        "sp500",
        "sp 500",
        "run",
        "top",
        "summary",
        "config",
        "help",
        "brains",
        "explain",
        "why",
    )
    return any(content == t or content.startswith(f"{t} ") for t in triggers)


def _is_reply_to_bot(message: Any) -> bool:
    reference = getattr(message, "reference", None)
    if reference is None:
        return False
    resolved = getattr(reference, "resolved", None)
    if resolved is None:
        return False
    ref_author = getattr(resolved, "author", None)
    if ref_author is None:
        return False
    return bool(getattr(ref_author, "bot", False))


async def _send_reply(message: Any, reply: str) -> None:
    max_len = 1900
    if len(reply) <= max_len:
        await message.channel.send(reply)
        return
    for i in range(0, len(reply), max_len):
        await message.channel.send(reply[i:i + max_len])


def _format_status_text(data: dict[str, object]) -> str:
    lines = [
        "Status:",
        f"- Last run: {data.get('last_run') or 'N/A'}",
        f"- Raw signals: {data.get('raw_signal_count', 0)}",
        f"- Approved: {data.get('approved_count', 0)}",
        f"- Sent: {data.get('sent_count', 0)}",
    ]
    suppressions = data.get("suppressed_counts", {}) or {}
    if isinstance(suppressions, dict) and suppressions:
        top = sorted(suppressions.items(), key=lambda kv: kv[1], reverse=True)[:3]
        lines.append("- Top suppressions: " + ", ".join(f"{k}={v}" for k, v in top))
    else:
        lines.append("- Top suppressions: none")
    return "\n".join(lines)


def _help_text() -> str:
    return (
        "Try: status, run, top 5, summary 5, config, brains, help\n"
        "Try: update for a broader market snapshot or s&p for the mobile S&P 500 daily overview.\n"
        "You can use slash commands or message me directly.\n"
        "Examples: `@bot top 3`, `!sa summary`, `update`, `s&p`, or DM `run`."
    )


def _top_n_from_text(text: str, default: int = 5, min_n: int = 1, max_n: int = 10) -> int:
    match = re.search(r"\b(\d{1,2})\b", text)
    if not match:
        return default
    try:
        value = int(match.group(1))
        return max(min_n, min(max_n, value))
    except Exception:
        return default


async def _chat_answer(query: str, is_admin: bool) -> str:
    q = (query or "").strip().lower()
    if not q or q in {"hi", "hello", "hey"}:
        return _help_text()

    if "help" in q:
        return _help_text()

    if "status" in q:
        return _format_status_text(status_snapshot())

    if q.startswith("update") or "market update" in q or "morning note" in q:
        result = await asyncio.to_thread(build_market_update)
        preview = format_discord_update(result, max_chars=1800)
        if result.warnings:
            warn_text = "\n".join(f"- {w}" for w in result.warnings[:3])
            return f"{preview}\n\n*Data notes:*\n{warn_text}"
        return preview

    if q.startswith("s&p") or q.startswith("sp500") or q.startswith("sp 500") or "s&p 500" in q:
        result = await asyncio.to_thread(build_sp500_overview)
        if result.warnings:
            warn_text = "\n".join(f"- {w}" for w in result.warnings[:3])
            return f"{result.body}\n\n*Data notes:*\n{warn_text}"
        return result.body

    if q.startswith("top") or " top " in f" {q} ":
        n = _top_n_from_text(q, default=5, min_n=1, max_n=10)
        top = get_top_signals(top_n=n)
        if not top:
            return "No recent signals available yet."
        return format_digest(top, title=f"Top {n} Signals")

    if q.startswith("summary") or "summary" in q:
        n = _top_n_from_text(q, default=5, min_n=1, max_n=20)
        summary = alert_summary(limit=n)
        last_cycle_raw = int(summary.get("last_cycle_raw_signal_count", 0) or 0)
        last_cycle_approved = int(summary.get("last_cycle_approved_count", 0) or 0)
        last_cycle_sent = int(summary.get("last_cycle_sent_count", 0) or 0)
        last_cycle_webhook_sent = int(summary.get("last_cycle_webhook_sent_count", 0) or 0)
        last_cycle_persist_failed = int(summary.get("last_cycle_persist_failed_count", 0) or 0)
        lines = [
            f"Last run: {summary.get('last_run') or 'N/A'}",
            f"Average ranking score: {summary.get('average_ranking_score', 0)}",
            (
                f"Last cycle: raw={last_cycle_raw} | approved={last_cycle_approved} | sent={last_cycle_sent} | "
                f"webhook_sent={last_cycle_webhook_sent} | persist_failed={last_cycle_persist_failed}"
            ),
        ]
        suppressions = summary.get("top_suppression_reasons", []) or []
        if suppressions:
            lines.append("Top suppressions: " + ", ".join(f"{k}={v}" for k, v in suppressions))
        else:
            lines.append("Top suppressions: none")
        if last_cycle_approved == 0:
            lines.append("No alerts were approved in the latest run, so alert history below may be older.")
        elif last_cycle_sent == 0:
            lines.append("Approved alerts were not sent in the latest run; check webhook/persistence counters above.")
        rows = summary.get("recent_alerts", []) or []
        if rows:
            lines.append("")
            lines.append(f"Last {len(rows)} alerts:")
            for row in rows:
                lines.append(
                    f"- {row['created_at']} | {row['ticker']} | {row['signal_type']} | "
                    f"{row['brain']} | rank {row.get('ranking_score') or 'n/a'}"
                )
        return "\n".join(lines)

    if q.startswith("config") or "session" in q or "market hours" in q:
        cfg = get_market_session_config()
        return (
            "Current configuration:\n"
            f"- Market timezone: {cfg['market_timezone']}\n"
            f"- Market open: {cfg['market_open']}\n"
            f"- Market close: {cfg['market_close']}\n"
            f"- Tickers: {', '.join(cfg['stocks']) if cfg['stocks'] else 'none'}"
        )

    if q.startswith("run") or "run now" in q:
        if not is_admin:
            return "Admin role required to run the pipeline from chat."
        result = await asyncio.to_thread(run_pipeline)
        top = get_top_signals(top_n=3)
        summary = format_digest(top, title="Top Signals") if top else "No recent ranked signals available."
        return (
            f"Run result: {result.get('status')} | raw={result.get('raw_signal_count', 0)} | "
            f"approved={result.get('approved_count', 0)} | sent={result.get('sent_count', 0)} | "
            f"webhook_sent={result.get('webhook_sent_count', 0)} | "
            f"persist_failed={result.get('persist_failed_count', 0)}\n\n{summary}"
        )

    if "brain" in q or "why" in q or "explain" in q:
        rows = alert_summary(limit=5).get("recent_alerts", []) or []
        if not rows:
            return "I can explain brain decisions once recent alerts exist. Try `run` first."
        lines = ["Recent brain calls:"]
        for row in rows[:5]:
            lines.append(f"- {row['ticker']}: {row['brain']} -> {row['signal_type']} (rank {row.get('ranking_score') or 'n/a'})")
        lines.append("Ask: `top 3` or `summary` for more detail.")
        return "\n".join(lines)

    return "I didn't understand that. " + _help_text()


async def _send_error(interaction: Any, message: str) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


async def _execute_instrumented(command_name: str, interaction: Any, handler) -> None:
    start = time.perf_counter()
    status = "success"
    with tracer.start_as_current_span(f"discord.command.{command_name}") as span:
        user_id = getattr(getattr(interaction, "user", None), "id", None)
        _set_span_attr(span, "command.name", command_name)
        _set_span_attr(span, "discord.user_id", user_id or 0)
        try:
            await handler()
        except Exception as exc:
            status = "error"
            _set_span_attr(span, "error", True)
            logger.exception("command_failed command=%s user=%s error=%s", command_name, user_id, exc)
            await _send_error(interaction, f"{command_name} failed: {type(exc).__name__}: {exc}")
        finally:
            duration = time.perf_counter() - start
            _set_span_attr(span, "command.duration_seconds", duration)
            record_interactive_command(command_name, status, duration)


def _is_admin(interaction: Any) -> bool:
    guild = getattr(interaction, "guild", None)
    if guild is None:
        return True
    perms = getattr(getattr(interaction, "user", None), "guild_permissions", None)
    return bool(getattr(perms, "administrator", False))


async def handle_status(interaction: Any) -> None:
    async def _inner() -> None:
        data = status_snapshot()
        await interaction.response.send_message(embed=_status_embed(data), ephemeral=True)

    await _execute_instrumented("status", interaction, _inner)


async def handle_run(interaction: Any) -> None:
    user = getattr(interaction, "user", None)

    async def _inner() -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message("Admin role required for /run.", ephemeral=True)
            return

        scope_key = f"guild:{getattr(interaction, 'guild_id', None)}" if getattr(interaction, "guild_id", None) else "guild:dm"
        remaining = run_cooldown_store.seconds_remaining(scope_key, RUN_COOLDOWN_SECONDS)
        if remaining > 0:
            await interaction.response.send_message(f"Cooldown active. Try again in {int(remaining)}s.", ephemeral=True)
            return

        run_cooldown_store.mark_run(scope_key)
        await interaction.response.defer(ephemeral=True, thinking=True)

        result = await asyncio.to_thread(run_pipeline)
        top = get_top_signals(top_n=3)
        summary = format_digest(top, title="Top Signals") if top else "No recent ranked signals available."
        await interaction.followup.send(
            f"Run result: {result.get('status')} | raw={result.get('raw_signal_count', 0)} | "
            f"approved={result.get('approved_count', 0)} | sent={result.get('sent_count', 0)} | "
            f"webhook_sent={result.get('webhook_sent_count', 0)} | "
            f"persist_failed={result.get('persist_failed_count', 0)}\n\n{summary}",
            ephemeral=True,
        )

    await _execute_instrumented("run", interaction, _inner)


async def handle_top(interaction: Any, n: int = 5) -> None:
    async def _inner() -> None:
        top = get_top_signals(top_n=max(1, min(10, n)))
        if not top:
            await interaction.response.send_message("No recent signals available.", ephemeral=True)
            return
        await interaction.response.send_message(format_digest(top, title=f"Top {max(1, min(10, n))} Signals"), ephemeral=True)

    await _execute_instrumented("top", interaction, _inner)


async def handle_summary(interaction: Any, n: int = 5) -> None:
    async def _inner() -> None:
        summary = alert_summary(limit=max(1, min(20, n)))
        last_cycle_raw = int(summary.get("last_cycle_raw_signal_count", 0) or 0)
        last_cycle_approved = int(summary.get("last_cycle_approved_count", 0) or 0)
        last_cycle_sent = int(summary.get("last_cycle_sent_count", 0) or 0)
        last_cycle_webhook_sent = int(summary.get("last_cycle_webhook_sent_count", 0) or 0)
        last_cycle_persist_failed = int(summary.get("last_cycle_persist_failed_count", 0) or 0)
        lines = [
            f"Last run: {summary.get('last_run') or 'N/A'}",
            f"Average ranking score: {summary.get('average_ranking_score', 0)}",
            (
                f"Last cycle: raw={last_cycle_raw} | approved={last_cycle_approved} | sent={last_cycle_sent} | "
                f"webhook_sent={last_cycle_webhook_sent} | persist_failed={last_cycle_persist_failed}"
            ),
        ]
        suppressions = summary.get("top_suppression_reasons", []) or []
        if suppressions:
            lines.append("Top suppressions: " + ", ".join(f"{k}={v}" for k, v in suppressions))
        else:
            lines.append("Top suppressions: none")
        if last_cycle_approved == 0:
            lines.append("No alerts were approved in the latest run, so alert history below may be older.")
        elif last_cycle_sent == 0:
            lines.append("Approved alerts were not sent in the latest run; check webhook/persistence counters above.")
        rows = summary.get("recent_alerts", []) or []
        if rows:
            lines.append("")
            lines.append(f"Last {len(rows)} alerts:")
            for row in rows:
                lines.append(
                    f"- {row['created_at']} | {row['ticker']} | {row['signal_type']} | "
                    f"{row['brain']} | rank {row.get('ranking_score') or 'n/a'}"
                )
        else:
            lines.append("No recent alerts available.")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    await _execute_instrumented("summary", interaction, _inner)


async def handle_config(interaction: Any, market_open: str | None = None, market_close: str | None = None, tickers: str | None = None) -> None:
    async def _inner() -> None:
        if not _is_admin(interaction):
            await interaction.response.send_message("Admin role required for /config.", ephemeral=True)
            return

        tickers_list = _parse_tickers(tickers)
        if market_open or market_close or tickers is not None:
            config_view = update_market_config(market_open=market_open, market_close=market_close, tickers=tickers_list)
            prefix = "Configuration updated."
        else:
            config_view = get_market_session_config()
            prefix = "Current configuration."

        lines = [
            prefix,
            f"Market timezone: {config_view['market_timezone']}",
            f"Market open: {config_view['market_open']}",
            f"Market close: {config_view['market_close']}",
            f"Tickers: {', '.join(config_view['stocks']) if config_view['stocks'] else 'none'}",
        ]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    await _execute_instrumented("config", interaction, _inner)


async def handle_help(interaction: Any) -> None:
    async def _inner() -> None:
        help_text = (
            "Commands:\n"
            "/status - current run metrics and suppressions\n"
            "/update - generate today's broader market update preview\n"
            "/sp500 - generate the mobile S&P 500 daily overview\n"
            "/run - execute one cycle now (admin only, cooldown enforced)\n"
            "/top n - show top ranked recent signals\n"
            "/summary n - summarize recent alerts and analytics\n"
            "/config - show or update market session settings and ticker universe\n"
            "/help - show this help"
        )
        await interaction.response.send_message(help_text, ephemeral=True)

    await _execute_instrumented("help", interaction, _inner)


async def handle_update(interaction: Any) -> None:
    async def _inner() -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await asyncio.to_thread(build_market_update)
        preview = format_discord_update(result, max_chars=1800)
        if result.warnings:
            text = preview + "\n\n*Data notes: " + " | ".join(result.warnings[:3]) + "*"
        else:
            text = preview
        await interaction.followup.send(text, ephemeral=True)

    await _execute_instrumented("update", interaction, _inner)


async def handle_sp500(interaction: Any) -> None:
    async def _inner() -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await asyncio.to_thread(build_sp500_overview)
        text = result.body
        if result.warnings:
            text += "\n\n*Data notes: " + " | ".join(result.warnings[:3]) + "*"
        await interaction.followup.send(text, ephemeral=True)

    await _execute_instrumented("sp500", interaction, _inner)


@bot.tree.command(name="status", description="Show latest bot run status")
async def status_cmd(interaction: Any) -> None:
    await handle_status(interaction)


@bot.tree.command(name="update", description="Generate today's broader market update preview")
async def update_cmd(interaction: Any) -> None:
    await handle_update(interaction)


@bot.tree.command(name="sp500", description="Generate the S&P 500 daily overview")
async def sp500_cmd(interaction: Any) -> None:
    await handle_sp500(interaction)


@bot.tree.command(name="run", description="Run one alert cycle now (admin only)")
async def run_cmd(interaction: Any) -> None:
    await handle_run(interaction)


@bot.tree.command(name="top", description="Show current top ranked recommendations")
@app_commands.describe(n="Number of signals to return")
async def top_cmd(interaction: Any, n: int = 5) -> None:
    await handle_top(interaction, n=n)


@bot.tree.command(name="summary", description="Summarize recent alerts and analytics")
@app_commands.describe(n="Number of recent alerts to include")
async def summary_cmd(interaction: Any, n: int = 5) -> None:
    await handle_summary(interaction, n=n)


@bot.tree.command(name="config", description="Show or update market session settings and ticker universe")
@app_commands.describe(market_open="HH:MM market open", market_close="HH:MM market close", tickers="Comma-separated tickers")
async def config_cmd(interaction: Any, market_open: str | None = None, market_close: str | None = None, tickers: str | None = None) -> None:
    await handle_config(interaction, market_open=market_open, market_close=market_close, tickers=tickers)


@bot.tree.command(name="help", description="Show command help")
async def help_cmd(interaction: Any) -> None:
    await handle_help(interaction)


@bot.event
async def on_ready() -> None:
    logger.info("bot_ready user=%s", bot.user)
    intents = getattr(bot, "intents", None)
    message_content = bool(getattr(intents, "message_content", False)) if intents is not None else False
    chat_mode = (os.environ.get("DISCORD_CHAT_MODE", "mention") or "mention").strip().lower()
    logger.info("chat_mode_enabled mode=%s dm=true reply_to_bot=true", chat_mode)
    logger.info("discord_intents message_content=%s", message_content)


@bot.event
async def on_message(message: Any) -> None:
    try:
        author = getattr(message, "author", None)
        if author is None:
            return
        if getattr(author, "bot", False):
            return
        if not _looks_like_chat_addressed(message):
            return

        query = _extract_chat_query(message)
        if not query:
            await message.channel.send(_help_text())
            return

        perms = getattr(author, "guild_permissions", None)
        is_admin = bool(getattr(perms, "administrator", False))

        with tracer.start_as_current_span("discord.chat.message") as span:
            _set_span_attr(span, "chat.query", query[:200])
            _set_span_attr(span, "chat.user_id", getattr(author, "id", 0))
            _set_span_attr(span, "chat.is_admin", is_admin)
            start = time.perf_counter()
            status = "success"
            try:
                reply = await _chat_answer(query, is_admin=is_admin)
            except Exception as exc:
                status = "error"
                logger.exception("chat_handler_failed error=%s", exc)
                reply = f"Sorry, chat handling failed: {type(exc).__name__}: {exc}"
            duration = time.perf_counter() - start
            _set_span_attr(span, "chat.duration_seconds", duration)
            record_interactive_command("chat_message", status, duration)

        try:
            await _send_reply(message, reply)
        except Exception as exc:
            logger.exception("chat_send_failed channel_id=%s error=%s", getattr(getattr(message, "channel", None), "id", None), exc)
            dm_channel = None
            create_dm = getattr(author, "create_dm", None)
            if callable(create_dm):
                try:
                    dm_channel = await create_dm()
                except Exception:
                    dm_channel = None
            if dm_channel is not None:
                try:
                    await dm_channel.send(
                        "I received your message but could not reply in that channel. "
                        "Please verify my channel Send Messages permission or DM me directly."
                    )
                except Exception:
                    pass
    finally:
        process = getattr(bot, "process_commands", None)
        if callable(process):
            await process(message)


def main() -> None:
    token = get_discord_bot_token()
    try:
        bot.run(token)
    except Exception as exc:
        login_failure_cls = getattr(getattr(discord, "errors", None), "LoginFailure", None)
        if login_failure_cls is not None and isinstance(exc, login_failure_cls):
            logger.error(
                "discord_login_failed reason=invalid_token token_len=%s dot_count=%s",
                len(token),
                token.count("."),
            )
            logger.error(
                "discord_login_help Ensure .env DISCORD_BOT_TOKEN is the latest Bot token from Developer Portal > Bot > Reset Token; no quotes, no spaces."
            )
        raise


if __name__ == "__main__":
    main()
