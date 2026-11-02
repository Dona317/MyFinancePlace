#!/bin/sh
# Live test of the whole app: fresh database, production server with login, fake Ollama, a real browser.
# Usage (from anywhere):  sh scripts/live/run.sh
# Environment: LIVE_DATABASE_URL (dropped and created again!), LIVE_ASSETS, LIVE_SHOTS, LIVE_CHROMIUM — see README.md
set -u
cd "$(dirname "$0")/../.."
LIVE=scripts/live
export LIVE_DATABASE_URL="${LIVE_DATABASE_URL:-postgresql://sa:Pa55w0rd@localhost:5432/mfp_live}"
export LIVE_OUT="${LIVE_OUT:-$LIVE/out}"
export LIVE_INSTANCE="$LIVE_OUT/instance"
NAME="${LIVE_DATABASE_URL##*/}"

rm -rf "$LIVE_OUT" && mkdir -p "$LIVE_INSTANCE"
psql "${LIVE_DATABASE_URL%/*}/postgres" -q -c "DROP DATABASE IF EXISTS $NAME" -c "CREATE DATABASE $NAME" || exit 1
DATABASE_URL="$LIVE_DATABASE_URL" flask --app run db upgrade >/dev/null 2>&1 || { echo "db upgrade failed"; exit 1; }

python "$LIVE/fake_ollama.py" & OLLAMA=$!
DATABASE_URL="$LIVE_DATABASE_URL" SECRET_KEY=live-test GUNICORN_BIND=127.0.0.1:5000 \
  gunicorn -c gunicorn.conf.py --pythonpath "$LIVE" live_wsgi:app >"$LIVE_OUT/server.log" 2>&1 & SERVER=$!
trap 'kill $SERVER $OLLAMA 2>/dev/null' EXIT INT TERM
for _ in 1 2 3 4 5 6 7 8 9 10; do curl -s -o /dev/null http://127.0.0.1:5000/auth/setup && break; sleep 1; done

STATUS=0
for script in login flows wealth features; do
  python "$LIVE/$script.py" >"$LIVE_OUT/$script.log" 2>&1 || STATUS=1
  grep -E "checks passed|^FAILED" "$LIVE_OUT/$script.log"
done
ERRORS=$(grep -c '" 50[0-9] ' "$LIVE_OUT/server.log")
echo "server errors (5xx): $ERRORS"
[ "$ERRORS" = 0 ] || STATUS=1
echo "logs in $LIVE_OUT/"
exit $STATUS
