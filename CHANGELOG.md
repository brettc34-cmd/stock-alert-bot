# Changelog

## 2026-03-23

- Added systemd and launchd service assets for unattended local operation.
- Added Discord `/summary` and `/config` command support with tracing and metrics.
- Added offline analytics report generation and protected dashboard report browsing.
- Added OpenTelemetry local tracing support, internal scheduler, and local observability stack.
- Added nightly APScheduler report automation (`REPORT_TIME`, `REPORT_DAYS`) without external cron.
- Added optional query-parameter API key support for `/reports` when `ENABLE_QUERY_API_KEY=1`.
