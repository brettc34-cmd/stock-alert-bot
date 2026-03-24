from scheduler import build_scheduler, run_report_job
from config.settings import RuntimeSettings


def test_scheduler_registers_open_and_close_jobs():
    settings = RuntimeSettings(
        discord_webhook_url="https://example.com/webhook",
        market_timezone="US/Eastern",
        market_open="09:30",
        market_close="16:00",
    )

    scheduler = build_scheduler(settings, lambda: None)
    jobs = {j.id for j in scheduler.get_jobs()}

    assert "market_open_cycle" in jobs
    assert "near_close_cycle" in jobs
    assert "nightly_report" in jobs
    assert "daily_market_update" in jobs
    assert "daily_sp500_overview" in jobs
    scheduler.shutdown(wait=False)


def test_report_job_calls_generator_with_days_argument():
    called = {}

    def fake_generate_report(days: int):
        called["days"] = days
        return "reports/report_test.md"

    run_report_job(report_days=3, report_func=fake_generate_report)
    assert called["days"] == 3
