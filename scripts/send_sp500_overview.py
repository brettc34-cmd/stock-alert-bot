"""Run the daily S&P 500 overview once, optionally only at the configured time."""

from __future__ import annotations

import argparse
import logging
import sys

from sp500_overview import run_sp500_overview_job, should_run_now


def main() -> int:
    parser = argparse.ArgumentParser(description="Send the S&P 500 daily overview")
    parser.add_argument(
        "--respect-schedule",
        action="store_true",
        help="Send only if the current time is within the configured schedule window.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    if args.respect_schedule and not should_run_now():
        logging.info("sp500_overview_cli_skip reason=outside_schedule_window")
        return 0

    result = run_sp500_overview_job()
    if result.sent:
        logging.info("sp500_overview_cli_success method=%s destination=%s", result.delivery_method, result.destination)
        return 0

    if result.warnings:
        logging.warning("sp500_overview_cli_preview_or_failure warnings=%s", result.warnings)
    return 0


if __name__ == "__main__":
    sys.exit(main())