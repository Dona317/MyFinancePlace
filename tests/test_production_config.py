"""Production configuration: secret key check, secure cookies, ProxyFix, logging (no database needed)."""
import logging

import pytest
from werkzeug.middleware.proxy_fix import ProxyFix

from app import create_app
from config import ProductionConfig


@pytest.fixture(autouse=True)
def restore_logging():
    """create_app("production") reconfigures the root logger; put pytest's handlers back afterwards."""
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


@pytest.fixture()
def strong_key(monkeypatch):
    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "a-long-random-test-key-0123456789")
    monkeypatch.delenv("BEHIND_PROXY", raising=False)


@pytest.mark.parametrize("key", ["", "change-me", "change-me-in-production"])
def test_refuses_default_secret_key(monkeypatch, key):
    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", key)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app("production")


def test_secure_cookies_and_https(strong_key):
    app = create_app("production")
    assert not app.debug
    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert app.config["PREFERRED_URL_SCHEME"] == "https"
    assert not isinstance(app.wsgi_app, ProxyFix)


def test_proxy_fix_when_behind_proxy(strong_key, monkeypatch):
    monkeypatch.setenv("BEHIND_PROXY", "1")
    app = create_app("production")
    assert isinstance(app.wsgi_app, ProxyFix)

    @app.get("/_scheme")
    def scheme():
        from flask import request
        return {"scheme": request.scheme, "remote": request.remote_addr}

    response = app.test_client().get(
        "/_scheme", headers={"X-Forwarded-Proto": "https", "X-Forwarded-For": "203.0.113.7"}
    )
    assert response.json == {"scheme": "https", "remote": "203.0.113.7"}


def test_logging_level_from_env(strong_key, monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "warning")
    app = create_app("production")
    assert logging.getLogger().level == logging.WARNING
    assert app.logger.level == logging.WARNING
    assert app.logger.propagate and not app.logger.handlers


def test_other_configs_untouched(monkeypatch):
    monkeypatch.setenv("BEHIND_PROXY", "1")
    app = create_app("testing")
    assert not isinstance(app.wsgi_app, ProxyFix)
    assert not app.config.get("SESSION_COOKIE_SECURE")
