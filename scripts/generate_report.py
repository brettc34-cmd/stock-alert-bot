"""Generate offline analytics report from local SQLite data."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if (ROOT / ".env").exists():
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except Exception:
        pass

from services.reporting import generate_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate stock alert analytics report")
    parser.add_argument("--days", type=int, default=7, help="Window size in days")
    parser.add_argument("--db-path", default="./storage/stock_alerts.db", help="SQLite database path")
    parser.add_argument("--reports-dir", default="reports", help="Output reports directory")
    args = parser.parse_args()

    output = generate_report(days=args.days, db_path=args.db_path, reports_dir=args.reports_dir)
    print(output)


if __name__ == "__main__":
    main()
