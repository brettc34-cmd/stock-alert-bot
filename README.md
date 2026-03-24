Stock Alert Bot - local-first portfolio alert engine

This project is designed to run 24/7 on personal hardware (Mac mini or Raspberry Pi), with no required cloud hosting.

Core capabilities:

- Multi-brain signal generation (Quant, Buffett, Druckenmiller, Soros, Lynch, Analyst, Dalio)
- Scoring + verification gates (freshness, confidence, confirmations, cooldown, duplicate suppression)
- Portfolio-aware action biasing
- Discord webhook and interactive slash-command bot
- Local SQLite persistence for signals/outcomes
- Local dashboard + health + metrics endpoints
- Optional local tracing via OpenTelemetry + Jaeger
- Daily S&P 500 overview delivery to Discord with fresh online market data, plus a separate broader market preview command in Discord

## Local hardware directory layout

Recommended layout on your Mac mini / Raspberry Pi:

```text
~/stock-alert-bot/
	.env
	config.json
	state.json
	anchors.json
	storage/
	local_data/
```

Keep `.env` in the repo root (same folder as `bot.py`).

## Environment configuration

Copy `.env.example` to `.env` and fill values.

Required:

- `DISCORD_WEBHOOK_URL`
- `DISCORD_BOT_TOKEN`
- `STOCK_ALERT_DASHBOARD_KEY`

Optional (local durability/observability):

- `REDIS_URL` (recommended for durable, shared `/run` cooldown state)
- `OTEL_EXPORTER_OTLP_ENDPOINT` (local collector endpoint, optional)
- `OTEL_ENABLE_PROMETHEUS` (optional OTel metrics reader toggle)

Market session (safe defaults for US markets):

- `MARKET_TIMEZONE` default: `US/Eastern`
- `MARKET_OPEN` default: `09:30`
- `MARKET_CLOSE` default: `16:00`

Scheduler controls:

- `DISABLE_INTERNAL_SCHEDULER` default: `0`
- `SCHEDULER_RUN_NEAR_CLOSE` default: `1`
- `SCHEDULER_CLOSE_OFFSET_MINUTES` default: `10`

Broader market update preview controls:

- `MARKET_UPDATE_ENABLED` default: `1`
- `MARKET_UPDATE_TIME` default: `07:00`
- `MARKET_UPDATE_TIMEZONE` default: `America/Chicago`

Daily S&P 500 overview controls:

- `SP500_OVERVIEW_ENABLED` default: `1`
- `SP500_OVERVIEW_TIME` default: `07:00`
- `SP500_OVERVIEW_TIMEZONE` default: `America/Chicago`
- `SP500_OVERVIEW_MAX_WORDS` default: `250`
- `SP500_OVERVIEW_LOG_PATH` default: `storage/sp500_overview_history.jsonl`
- delivery uses the existing `DISCORD_WEBHOOK_URL` env var, same as the rest of the repo

Nightly report controls:

- `REPORT_TIME` default: `21:00`
- `REPORT_DAYS` default: `1`
- scheduler runs report generation daily in `MARKET_TIMEZONE`

Optional browser convenience:

- `ENABLE_QUERY_API_KEY` default: `0`
- when `1`, `/reports?key=<api-key>` is accepted for browser access

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Running modes

One-off cycle:

```bash
./run_bot.sh
```

Cross-platform internal scheduler:

```bash
python bot.py --scheduler
```

This replaces launchd as the primary scheduling method. The launchd plist is deprecated.
The internal scheduler now also runs a nightly report job based on `REPORT_TIME` and `REPORT_DAYS`, a weekday broader market preview job using `MARKET_UPDATE_TIME` and `MARKET_UPDATE_TIMEZONE`, and a weekday S&P 500 overview delivery job using `SP500_OVERVIEW_TIME` and `SP500_OVERVIEW_TIMEZONE`.

## Optional service installation

### Linux / Raspberry Pi via systemd

Files:

- [systemd/stock-alert-bot.service](/Users/brettchapman/stock-alert-bot/systemd/stock-alert-bot.service)
- [scripts/install_systemd.sh](/Users/brettchapman/stock-alert-bot/scripts/install_systemd.sh)

Install:

```bash
chmod +x scripts/install_systemd.sh
sudo RUN_USER="$USER" bash scripts/install_systemd.sh
```

What it does:

- installs the service unit into `/etc/systemd/system/`
- creates `/etc/stock-alert-bot.env` from `.env.example` if missing
- enables and starts the service

Common commands:

```bash
sudo systemctl status stock-alert-bot.service
sudo systemctl restart stock-alert-bot.service
sudo journalctl -u stock-alert-bot.service -f
```

### macOS via Launch Agent

Template file:

- [launchd/stock-alert-bot.plist](/Users/brettchapman/stock-alert-bot/launchd/stock-alert-bot.plist)

The template uses `$HOME/stock-alert-bot`; clone the repo into that path or adjust the command string if your location differs.

Load:

```bash
cp launchd/stock-alert-bot.plist ~/Library/LaunchAgents/com.stockalertbot.scheduler.plist
launchctl load ~/Library/LaunchAgents/com.stockalertbot.scheduler.plist
launchctl start com.stockalertbot.scheduler
```

Unload:

```bash
launchctl unload ~/Library/LaunchAgents/com.stockalertbot.scheduler.plist
```

These service wrappers are optional. If you prefer containers, use Docker Compose instead.

Dashboard:

```bash
python web/app.py
```

Interactive Discord bot:

```bash
./run_interactive_bot.sh
```

The bot sets `DISABLE_INTERNAL_SCHEDULER=1` by default to avoid duplicate scheduled runs.

Manual fallback:

```bash
source .venv/bin/activate
python3 interactive_discord_bot.py
```

## Dashboard security

- `POST /run_bot` requires `X-API-KEY` header matching `STOCK_ALERT_DASHBOARD_KEY`.
- Invalid or missing key returns 403.

## Interactive Discord commands

- `/status`: last run + counts + top suppressions
- `/update`: generate a fresh broader market preview in Discord
- `/sp500`: generate the mobile S&P 500 daily overview in Discord
- `/run`: trigger one cycle now (admin only, cooldown enforced)
- `/top`: top recent ranked signals without starting a new cycle
- `/summary`: summarize latest alerts, ranking, suppressions, and last-cycle transparency counters
- `/config`: show or update market session settings and ticker universe (admin only)
- `/help`: command summary

Message-based commands work in chat as well (`status`, `update`, `s&p`, `run`, `top 5`, `summary 10`, `help`).

## Daily S&P 500 Overview

The project includes a dedicated S&P 500 overview pipeline for concise mobile delivery to Discord, plus an on-demand `s&p` command inside Discord. It stays separate from the broader `update` text.

Folder structure:

```text
sp500_overview/
  __init__.py
  config.py
  models.py
  market_data.py
  headlines.py
  summary.py
  senders.py
  log_store.py
  job.py
scripts/
  send_sp500_overview.py
.github/workflows/
  daily-sp500-overview.yml
```

Code layout:

- `sp500_overview/market_data.py`: fresh online S&P 500, 10-year yield, VIX, WTI, Fed funds, and sector data
- `sp500_overview/headlines.py`: RSS headline collection and market-driver classification
- `sp500_overview/summary.py`: concise mobile summary generation with bull vs bear framing and the required disclaimer
- `sp500_overview/log_store.py`: append-only local log of every scheduled send attempt
- `sp500_overview/job.py`: build, send, and scheduled-run orchestration
- `scripts/send_sp500_overview.py`: one-shot CLI for VPS cron or GitHub Actions

Public sources used:

- Yahoo Finance via `yfinance`: S&P 500, 10-year Treasury yield, VIX, WTI crude, sector ETFs
- FRED CSV endpoint: effective fed funds rate context
- CNBC Markets RSS, CNBC Economy RSS, Federal Reserve RSS: headline flow and driver context

No scraping is required. This keeps the feature inside free public endpoints and RSS feeds. The tradeoff is that headline coverage depends on the availability of those feeds.

Sample message:

```text
S&P 500 Daily Overview
- Index level: 6,577.49
- Daily move: -0.05%
- YTD: +7.84%
- Top drivers: Fed expectations; Oil; leaders: Energy, Technology; laggards: Utilities, Real Estate
- Key headlines: CNBC Markets: Fed still expects to cut rates once this year despite spiking oil prices; CNBC Economy: Jobs data keeps labor market resilience in focus
- Bull case: the index is still positive YTD; leadership includes Energy
- Bear case: the index is trading lower on the day; higher yields are a headwind; volatility is still elevated
- Bottom line: The S&P 500 is trading lower by -0.05%; the 10-year yield is near 4.40%; the latest fed funds rate was 3.64% as of 2026-02-01; VIX is 26.68.

“This is general information only and not financial advice. For personal guidance, please talk to a licensed professional.”
```

Step-by-step setup:

1. Create and activate a virtual environment.
2. Install dependencies with `python -m pip install -r requirements.txt`.
3. Copy `.env.example` to `.env`.
4. Set `DISCORD_WEBHOOK_URL` and `DISCORD_BOT_TOKEN`.
5. Set `SP500_OVERVIEW_TIME`, `SP500_OVERVIEW_TIMEZONE`, and `SP500_OVERVIEW_MAX_WORDS`.
6. Start the interactive bot with `./run_interactive_bot.sh` for manual `s&p` previews.
7. Start the scheduler with `python bot.py --scheduler` for automatic weekday delivery.

Manual run:

```bash
source .venv/bin/activate
python scripts/send_sp500_overview.py
```

Local log output:

- Each scheduled run appends one JSON line to `SP500_OVERVIEW_LOG_PATH`
- Default path: `storage/sp500_overview_history.jsonl`

How to change the send time:

- Internal scheduler: update `SP500_OVERVIEW_TIME` and `SP500_OVERVIEW_TIMEZONE`
- GitHub Actions: keep the workflow schedule broad and let `scripts/send_sp500_overview.py --respect-schedule` enforce the exact configured local time

How to change the message length:

- Update `SP500_OVERVIEW_MAX_WORDS`
- Default is `250`

How to deploy on a VPS:

1. Clone the repo and create `.env`.
2. Install dependencies in `.venv`.
3. Set delivery credentials in `.env`.
4. Run `python bot.py --scheduler` under systemd, launchd, Docker, or another process manager.
5. Check `storage/sp500_overview_history.jsonl` and service logs after the first scheduled run.

How to deploy on GitHub Actions:

1. Add the workflow at `.github/workflows/daily-sp500-overview.yml`.
2. Create repository secrets for `DISCORD_WEBHOOK_URL`, `SP500_OVERVIEW_TIME`, `SP500_OVERVIEW_TIMEZONE`, and optionally `SP500_OVERVIEW_MAX_WORDS`.
3. The workflow runs every 15 minutes on weekdays and sends only when `--respect-schedule` matches your configured local time. This avoids DST drift.

## Broader Market Update Preview

The existing `update` command remains available in Discord for a broader market snapshot built from Yahoo Finance, FRED, and RSS headlines. It is a preview-oriented note, while the S&P 500 overview is the delivery-oriented morning message.

Deployment notes:

- Local machine via cron: use the cron entry above
- GitHub Actions: store SMTP and recipient values as repository secrets
- Railway / Render / VPS: run `python scripts/send_market_update.py` as a scheduled job or run the existing internal scheduler in a long-lived process

### Digest presentation options

`config/features.yaml` supports digest presentation flags:

- `digest.display_mode`: `pro` or `novice`
- `digest.use_embed`: `true` or `false`
- `digest.use_colored_embed_scheme`: `true` or `false`
- `digest.show_signal_agreement`: `true` or `false`

Digest output includes:

- grouped opportunities by ticker
- bias with consistent color/icon mapping (`🟢` bullish, `🟡` mixed/watch, `🔴` bearish risk)
- confidence stars and labels
- active vs aligned signal counts plus optional signal agreement
- concise, data-driven `Why it matters`
- top opportunities and watchlist split

Summary output includes run transparency counters:

- `raw`, `approved`, `sent`, `webhook_sent`, `persist_failed`
- explicit note when latest run approved/sent zero alerts (history may be older)

Discord setup:

1. Create an application in Discord Developer Portal.
2. Add bot user and copy token to `DISCORD_BOT_TOKEN`.
3. Invite with `applications.commands` scope.
4. Ensure channel permissions for read/send.
5. `/run` is admin-only by role check.
6. `/config` is also admin-only.

## OpenTelemetry tracing (local only)

The project initializes tracing in `telemetry.py`:

- If `OTEL_EXPORTER_OTLP_ENDPOINT` is set, OTLP exporter is used.
- If not set, console span exporter is used (stdout traces).

Flask is instrumented in `web/app.py` using `FlaskInstrumentor`.

To run local Jaeger collector:

```bash
docker run --rm -p 4317:4317 -p 16686:16686 jaegertracing/all-in-one
```

Then set:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

Open Jaeger UI:

- `http://localhost:16686`

## Local observability stack

`docker-compose.yml` includes local-only services:

- dashboard (Flask)
- interactive-bot
- redis
- prometheus
- grafana

All published ports are bound to `127.0.0.1`.

Start stack:

```bash
docker compose up --build
```

Access:

- Dashboard: `http://localhost:8000/signals`
- Health: `http://localhost:8000/healthz`
- Dashboard metrics: `http://localhost:8000/metrics`
- Interactive bot metrics: `http://localhost:9101/metrics`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000` (admin/admin)

Preloaded Grafana dashboard includes:

- cycle throughput
- suppression reason rates
- quote fetch latency p95
- quote fetch success/failure rates

## ARM64 notes (Raspberry Pi)

The compose images used (`python`, `redis`, `prom/prometheus`, `grafana/grafana`, `jaegertracing/all-in-one`) provide ARM64-compatible tags.

On Raspberry Pi:

1. Install Docker + Compose plugin.
2. Use the same compose file; no cloud dependencies required.
3. If needed, force platform per service using `platform: linux/arm64`.

## Testing

```bash
python -m pytest -q
```

Coverage includes telemetry initialization, scheduler behavior, analytics schema persistence, and full pipeline integration.

## Offline analytics reports

Generate a report manually:

```bash
python scripts/generate_report.py --days 7
```

Reports are written to the local `reports/` directory.

Dashboard access:

- `GET /reports` lists generated reports
- `GET /reports/<filename>` serves a report file
- both use the same `X-API-KEY` protection as `POST /run_bot`
- optional convenience when enabled: `GET /reports?key=<api-key>`

Scheduling options:


- built-in nightly APScheduler report job (default)
- optional external cron if you want a second/backup report schedule

Example cron entry:

```bash
0 21 * * 1-5 cd ~/stock-alert-bot && /usr/bin/env python3 scripts/generate_report.py --days 7
```
