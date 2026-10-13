"""Gunicorn settings, all overridable from the environment (see .env.example and docs/DEPLOY.md).

    gunicorn -c gunicorn.conf.py wsgi:app
"""
import os

bind = os.environ.get("GUNICORN_BIND") or f"0.0.0.0:{os.environ.get('PORT', '8000')}"

# One process with several threads by default: model-download progress (Impostazioni → Modelli AI) is kept
# in memory, so every request must reach the same process. Raise GUNICORN_WORKERS only if you accept that.
workers = int(os.environ.get("GUNICORN_WORKERS") or os.environ.get("WEB_CONCURRENCY") or 1)
worker_class = "gthread"
threads = int(os.environ.get("GUNICORN_THREADS") or 8)

# Reading a scanned statement with a local model can take minutes (LLM_TIMEOUT, default 600 s):
# the worker must outlive the model call, plus a margin for parsing and saving.
timeout = int(os.environ.get("GUNICORN_TIMEOUT") or int(os.environ.get("LLM_TIMEOUT") or 600) + 120)
graceful_timeout = 30
keepalive = 5

# Logs to stdout/stderr, collected by `docker compose logs` / journald.
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info").lower()
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s %(M)sms "%(a)s"'

# X-Forwarded-* are handled by werkzeug's ProxyFix (BEHIND_PROXY=1); gunicorn only needs to trust
# the proxy for its own access log / wsgi.url_scheme.
forwarded_allow_ips = os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1")
