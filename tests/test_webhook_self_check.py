from alerts.discord_formatter import validate_discord_webhook_url, self_check_discord_webhook


class _Resp:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


def test_validate_discord_webhook_url_rejects_placeholder() -> None:
    ok, msg = validate_discord_webhook_url("https://discord.com/api/webhooks/replace-me")
    assert not ok
    assert "replace-me" in msg.lower()


def test_validate_discord_webhook_url_accepts_expected_prefix() -> None:
    ok, _ = validate_discord_webhook_url("https://discord.com/api/webhooks/123/abc")
    assert ok


def test_self_check_discord_webhook_success(monkeypatch) -> None:
    monkeypatch.setattr("alerts.discord_formatter.requests.get", lambda *_args, **_kwargs: _Resp(200))
    ok, msg = self_check_discord_webhook("https://discord.com/api/webhooks/123/abc")
    assert ok
    assert "passed" in msg.lower()


def test_self_check_discord_webhook_405(monkeypatch) -> None:
    monkeypatch.setattr("alerts.discord_formatter.requests.get", lambda *_args, **_kwargs: _Resp(405, "Method Not Allowed"))
    ok, msg = self_check_discord_webhook("https://discord.com/api/webhooks/123/abc")
    assert not ok
    assert "405" in msg
