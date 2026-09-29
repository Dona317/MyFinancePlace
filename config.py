import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

# Placeholder keys that must never sign sessions in production (the fallback below and old .env.example's).
INSECURE_SECRET_KEYS = {"", "change-me", "change-me-in-production"}


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "change-me-in-production"
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or "postgresql://sa:Pa55w0rd@localhost:5332/myfinanceplace"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = None  # no limit on uploaded statements

    # AI reading of scanned/photographed/non-standard statements (app/services/ai_extraction.py)
    # LLM_PROVIDER: "ollama" (local, private) | "anthropic" (Claude API) | empty = disabled
    LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "")
    LLM_MODEL = os.environ.get("LLM_MODEL", "")          # empty = provider default
    OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT") or 600)  # seconds
    AI_JOBS_SYNC = False  # True: the AI reading of a statement runs inside the request (no background thread)
    DEBUG = False

    @classmethod
    def init_app(cls, app):
        """Hook run by create_app once the config is loaded; nothing to do outside production."""


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    # Cookies only over HTTPS. Set SESSION_COOKIE_SECURE=0 only for plain-HTTP use on a trusted LAN.
    SESSION_COOKIE_SECURE = _env_flag("SESSION_COOKIE_SECURE", True)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    REMEMBER_COOKIE_HTTPONLY = True
    PREFERRED_URL_SCHEME = "https"

    @classmethod
    def init_app(cls, app):
        # Refuse to run with a known key: anyone could forge the session cookie.
        if (app.config.get("SECRET_KEY") or "") in INSECURE_SECRET_KEYS:
            raise RuntimeError(
                "SECRET_KEY is not set or is the default placeholder: refusing to start in production. "
                "Set a long random value, e.g. python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )

        # Behind nginx/Caddy/Traefik: trust PROXY_HOPS hops of X-Forwarded-For/-Proto/-Host/-Port/-Prefix,
        # so url_for builds https:// links and request.remote_addr is the client's address.
        if _env_flag("BEHIND_PROXY", False):
            from werkzeug.middleware.proxy_fix import ProxyFix

            hops = int(os.environ.get("PROXY_HOPS") or 1)
            app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=hops, x_host=hops, x_port=hops, x_prefix=hops)

        configure_logging(app)


def configure_logging(app):
    """One line per record on stdout, level from LOG_LEVEL (default INFO)."""
    level = os.environ.get("LOG_LEVEL", "INFO").strip().upper() or "INFO"
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s [%(process)d] %(name)s: %(message)s", "%Y-%m-%dT%H:%M:%S%z"
    ))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # Flask adds its own stderr handler to app.logger; drop it so records go once, through the root handler.
    app.logger.handlers.clear()
    app.logger.setLevel(level)
    app.logger.propagate = True


class TestingConfig(Config):
    TESTING = True
    LLM_PROVIDER = ""  # tests enable it explicitly
    AI_JOBS_SYNC = True  # tests of the background thread turn it off explicitly
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL") or "postgresql://sa:Pa55w0rd@localhost:5332/myfinanceplace_test"
    WTF_CSRF_ENABLED = False


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
