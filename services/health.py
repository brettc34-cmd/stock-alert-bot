"""Health service adapters for dashboard and bot runtime."""

from typing import Any, Dict

from safety.health_checks import health_status


def build_health(state: Dict[str, Any], settings: Any) -> Dict[str, Any]:
    return health_status(state=state, discord_webhook=settings.discord_webhook_url)
