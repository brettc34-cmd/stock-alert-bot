"""Utility helpers for loading YAML/JSON configuration and required secrets."""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv
import yaml


load_dotenv()


def _load_yaml_file(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    with open(p, "r") as f:
        return yaml.safe_load(f) or {}


def load_thresholds(path: str = "config/thresholds.yaml") -> Dict[str, Any]:
    return _load_yaml_file(path)


def load_features(path: str = "config/features.yaml") -> Dict[str, Any]:
    return _load_yaml_file(path)


def save_yaml(path: str, data: Dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        yaml.safe_dump(data, f)


def load_json_file(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    with open(p, "r") as f:
        return json.load(f)


def save_json_file(path: str, data: Dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(data, f, indent=2)


def _normalize_env_value(value: str | None) -> str:
    if value is None:
        return ""
    normalized = value.strip()
    if (normalized.startswith('"') and normalized.endswith('"')) or (
        normalized.startswith("'") and normalized.endswith("'")
    ):
        normalized = normalized[1:-1].strip()
    return normalized


def get_required_env(name: str) -> str:
    value = _normalize_env_value(os.environ.get(name))
    if value:
        return value
    raise RuntimeError(f"Missing required environment variable: {name}")


def get_discord_webhook_url() -> str:
    return get_required_env("DISCORD_WEBHOOK_URL")


def get_discord_bot_token() -> str:
    token = get_required_env("DISCORD_BOT_TOKEN")
    if token.lower().startswith("bot "):
        token = token[4:].strip()

    parts = token.split(".")
    if len(parts) != 3 or not all(parts):
        raise RuntimeError(
            "Invalid DISCORD_BOT_TOKEN format: expected three dot-separated token segments."
        )

    if any(re.search(r"\s", part) for part in parts):
        raise RuntimeError("Invalid DISCORD_BOT_TOKEN format: token contains whitespace.")

    return token
