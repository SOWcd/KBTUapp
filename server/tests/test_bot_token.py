"""Telegram authentication requires a configured bot credential."""
import pytest

from kbtu import auth, config


@pytest.mark.parametrize("token", ["", "  ", "invalid", "123:", "123:short", "abc:" + "x" * 35])
def test_invalid_bot_token_stops_startup(monkeypatch, token):
    monkeypatch.setenv("TOKEN_KEY", "A" * 43 + "=")
    monkeypatch.setenv("BOT_TOKEN", token)
    with pytest.raises(SystemExit, match="BOT_TOKEN"):
        config.load()


def test_missing_secret_rejected_before_authentication(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("signature verification requires a bot secret")

    monkeypatch.setattr(auth.hmac, "new", unexpected)
    assert auth.check_init_data("", "") is None
