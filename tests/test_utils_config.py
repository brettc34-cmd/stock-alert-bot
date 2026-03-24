import pytest

from utils.config import _normalize_env_value, get_discord_bot_token


def test_normalize_env_value_strips_quotes_and_spaces():
    assert _normalize_env_value('  "abc"  ') == "abc"
    assert _normalize_env_value("  'abc'  ") == "abc"
    assert _normalize_env_value("  abc  ") == "abc"


def test_get_discord_bot_token_strips_bot_prefix(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "Bot aaa.bbb.ccc")
    assert get_discord_bot_token() == "aaa.bbb.ccc"


def test_get_discord_bot_token_rejects_bad_format(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "not-a-token")
    with pytest.raises(RuntimeError):
        get_discord_bot_token()
