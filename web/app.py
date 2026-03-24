"""Simple dashboard web UI for the stock alert bot."""

from flask import Flask, render_template, jsonify, request, redirect, url_for, send_from_directory
import json
import sys
from pathlib import Path
import yaml
import os
from functools import wraps
try:
    from opentelemetry.instrumentation.flask import FlaskInstrumentor
except Exception:  # pragma: no cover
    class FlaskInstrumentor:  # type: ignore[override]
        def instrument_app(self, app):
            app._is_instrumented_by_opentelemetry = True


try:
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
except Exception:  # pragma: no cover
    class RequestsInstrumentor:  # type: ignore[override]
        def instrument(self):
            return None

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from storage.sqlite_store import init_db
from storage.outcome_tracker import init_outcomes_db
from utils.config import load_thresholds, load_features, save_yaml
from safety.health_checks import health_status
from config.settings import build_runtime_settings
from services.metrics import render_metrics_payload
from services.reporting import list_reports
from telemetry import configure_opentelemetry


configure_opentelemetry(service_name="stock-alert-bot-dashboard")
RequestsInstrumentor().instrument()

app = Flask(__name__)
FlaskInstrumentor().instrument_app(app)


def require_dashboard_key(view_func):
    @wraps(view_func)
    def _wrapped(*args, **kwargs):
        expected = os.environ.get("STOCK_ALERT_DASHBOARD_KEY")
        provided = request.headers.get("X-API-KEY")
        allow_query = os.environ.get("ENABLE_QUERY_API_KEY", "0").strip().lower() in {"1", "true", "yes", "on"}
        if allow_query and not provided:
            provided = request.args.get("key")
        if not expected or provided != expected:
            return jsonify({"message": "Forbidden"}), 403
        return view_func(*args, **kwargs)

    return _wrapped


@app.route("/healthz")
def healthz():
    try:
        with open("state.json", "r") as f:
            state = json.load(f)
        with open("config.json", "r") as f:
            cfg = json.load(f)
        settings = build_runtime_settings(cfg)
        return jsonify(health_status(state, settings.discord_webhook_url))
    except Exception as exc:
        return jsonify({"status": "degraded", "error": str(exc)}), 500


@app.route("/metrics")
def metrics():
    payload, content_type = render_metrics_payload()
    return payload, 200, {"Content-Type": content_type}


@app.route("/signals")
def signals():
    conn = init_db()
    cur = conn.cursor()
    cur.execute("SELECT ticker, brain, category, confidence, summary, payload, created_at FROM signals ORDER BY created_at DESC LIMIT 100")
    rows = cur.fetchall()
    parsed = []
    for row in rows:
        payload = {}
        try:
            payload = json.loads(row[5] or "{}")
        except Exception:
            payload = {}
        parsed.append({
            "ticker": row[0],
            "brain": row[1],
            "signal_type": row[2],
            "confidence": row[3],
            "summary": row[4],
            "action_bias": payload.get("action_bias", "WATCH"),
            "priority": payload.get("priority", "moderate"),
            "portfolio_note": payload.get("portfolio_note", ""),
            "confirmations": len(payload.get("confirmations", [])),
            "created_at": row[6],
        })

    suppressions = {}
    try:
        with open("state.json", "r") as f:
            state = json.load(f)
        suppressions = state.get("suppression_counts", {})
    except Exception:
        suppressions = {}

    return render_template("signals.html", signals=parsed, suppressions=suppressions)


@app.route("/outcomes")
def outcomes():
    conn = init_outcomes_db()
    cur = conn.cursor()
    cur.execute("SELECT alert_id, ticker, signal_time, action_bias, outcome, return_pct FROM outcomes ORDER BY signal_time DESC LIMIT 50")
    rows = cur.fetchall()
    # Calculate stats
    total_trades = len(rows)
    wins = sum(1 for r in rows if r[4] == 'win')
    win_rate = wins / total_trades if total_trades > 0 else 0
    avg_return = sum(r[5] for r in rows) / total_trades if total_trades > 0 else 0
    total_pnl = sum(r[5] for r in rows)
    return render_template("outcomes.html", outcomes=rows, total_trades=total_trades, win_rate=win_rate, avg_return=avg_return, total_pnl=total_pnl)


@app.route("/run_bot", methods=["POST"])
@require_dashboard_key
def run_bot():
    import subprocess
    import os
    try:
        # Run the bot script
        result = subprocess.run(["python3", "bot.py"], cwd=os.path.dirname(os.path.dirname(__file__)), capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            return jsonify({"message": "Bot run completed successfully."})
        else:
            return jsonify({"message": f"Bot run failed: {result.stderr}"})
    except subprocess.TimeoutExpired:
        return jsonify({"message": "Bot run timed out."})
    except Exception as e:
        return jsonify({"message": f"Error: {str(e)}"})


@app.route("/reports")
@require_dashboard_key
def reports():
    files = list_reports("reports")
    return render_template("reports.html", reports=[p.name for p in files])


@app.route("/reports/<path:report_name>")
@require_dashboard_key
def serve_report(report_name: str):
    return send_from_directory("reports", report_name)


@app.route("/config", methods=["GET", "POST"])
def config():
    thresholds = load_thresholds()
    features = load_features()
    error = None
    success = None
    if request.method == "POST":
        thresholds_text = request.form.get("thresholds", "")
        features_text = request.form.get("features", "")
        try:
            save_yaml("config/thresholds.yaml", yaml.safe_load(thresholds_text))
            save_yaml("config/features.yaml", yaml.safe_load(features_text))
            success = "Configuration saved successfully."
            thresholds = load_thresholds()
            features = load_features()
        except yaml.YAMLError as exc:
            error = f"YAML parse error: {exc}"
            return render_template(
                "config.html",
                thresholds=thresholds_text,
                features=features_text,
                error=error,
                success=None,
            ), 400
        except Exception as exc:
            error = f"Failed to save config: {exc}"
            return render_template(
                "config.html",
                thresholds=thresholds_text,
                features=features_text,
                error=error,
                success=None,
            ), 500

    return render_template(
        "config.html",
        thresholds=yaml.safe_dump(thresholds),
        features=yaml.safe_dump(features),
        error=error,
        success=success,
    )


if __name__ == "__main__":
    try:
        with open("config.json", "r") as f:
            cfg = json.load(f)
        port = build_runtime_settings(cfg).dashboard_port
    except Exception:
        port = 8000
    app.run(host="0.0.0.0", port=port, debug=False)
