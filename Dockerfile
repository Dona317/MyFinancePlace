# MyFinancePlace — production image (gunicorn + wsgi.py). See docs/DEPLOY.md.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

# Every requirement ships a manylinux wheel with its native parts bundled (psycopg2-binary with libpq,
# pdfplumber's pypdfium2, Pillow, lxml for python-docx), so no apt packages, build tools or -dev headers
# are needed. The base image already ships tzdata: "today" and the current month follow TZ (override in .env).
ENV TZ=Europe/Rome

RUN groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --home-dir /app --shell /usr/sbin/nologin app

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Code is owned by root and read-only for the app user; only instance/ (documents, backups, uploads) is writable.
COPY . .
RUN mkdir -p /app/instance && chown app:app /app/instance

USER app

EXPOSE 8000
VOLUME ["/app/instance"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/dashboard', timeout=4)" || exit 1

ENTRYPOINT ["sh", "/app/docker/entrypoint.sh"]
CMD ["gunicorn", "-c", "gunicorn.conf.py", "wsgi:app"]
