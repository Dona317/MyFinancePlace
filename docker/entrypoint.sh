#!/bin/sh
# Container entry point: make sure there is a SECRET_KEY, bring the database schema up to date, then run CMD.
set -e

INSTANCE_DIR="${INSTANCE_DIR:-/app/instance}"
mkdir -p "$INSTANCE_DIR"

# No SECRET_KEY given: generate one once and keep it in the instance volume, so sessions survive restarts.
# (A placeholder such as "change-me" is still refused by the production config.)
if [ -z "$SECRET_KEY" ]; then
    KEY_FILE="$INSTANCE_DIR/.secret_key"
    if [ ! -s "$KEY_FILE" ]; then
        (umask 077 && python -c "import secrets; print(secrets.token_urlsafe(48))" > "$KEY_FILE")
        echo "entrypoint: SECRET_KEY not set, generated one in $KEY_FILE"
    fi
    SECRET_KEY="$(cat "$KEY_FILE")"
    export SECRET_KEY
fi

# Fail fast on configuration errors (e.g. a placeholder SECRET_KEY) instead of retrying the migrations.
python -c "import wsgi"

# Apply pending migrations (RUN_MIGRATIONS=0 to skip). Retry while the database is still starting.
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    attempt=1
    until flask --app wsgi db upgrade; do
        if [ "$attempt" -ge "${DB_WAIT_ATTEMPTS:-30}" ]; then
            echo "entrypoint: database migrations failed after $attempt attempts" >&2
            exit 1
        fi
        echo "entrypoint: database not ready (attempt $attempt), retrying in 2 s..." >&2
        attempt=$((attempt + 1))
        sleep 2
    done
    flask --app wsgi clients migrate  # every client's own database (F11)
fi

exec "$@"
