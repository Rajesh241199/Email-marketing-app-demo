#!/usr/bin/env bash
# One-shot local dev setup for the backend: Python venv, dependencies, .env,
# PostgreSQL (macOS/Homebrew best-effort), and database migrations.
#
# Safe to re-run - every step checks whether it's already done before acting.
#
# Usage:
#   cd backend && ./setup.sh

set -euo pipefail
cd "$(dirname "$0")"

echo "==> Python virtual environment"
if [ ! -d .venv ]; then
    python3 -m venv .venv
    echo "    created .venv"
else
    echo "    .venv already exists"
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Installing dependencies"
pip install --quiet --upgrade pip
pip install --quiet -e ".[dev]"

echo "==> .env"
if [ ! -f .env ]; then
    cp .env.example .env
    echo "    created .env from .env.example (edit JWT_SECRET before using this anywhere real)"
else
    echo "    .env already exists"
fi
set -a
# shellcheck disable=SC1091
source .env
set +a

echo "==> PostgreSQL"
if command -v psql >/dev/null 2>&1; then
    PSQL_BIN=psql
    CREATEDB_BIN=createdb
    CREATEUSER_BIN=createuser
elif command -v brew >/dev/null 2>&1 && brew --prefix postgresql@16 >/dev/null 2>&1; then
    PG_BIN_DIR="$(brew --prefix postgresql@16)/bin"
    PSQL_BIN="$PG_BIN_DIR/psql"
    CREATEDB_BIN="$PG_BIN_DIR/createdb"
    CREATEUSER_BIN="$PG_BIN_DIR/createuser"
elif [[ "$(uname)" == "Darwin" ]] && command -v brew >/dev/null 2>&1; then
    echo "    installing postgresql@16 via Homebrew (one-time)"
    brew install postgresql@16
    PG_BIN_DIR="$(brew --prefix postgresql@16)/bin"
    PSQL_BIN="$PG_BIN_DIR/psql"
    CREATEDB_BIN="$PG_BIN_DIR/createdb"
    CREATEUSER_BIN="$PG_BIN_DIR/createuser"
else
    echo "    no local PostgreSQL found and this isn't a Homebrew-capable macOS shell."
    echo "    Either install PostgreSQL 16 yourself, or run 'docker compose up -d postgres'"
    echo "    from the repo root, then re-run this script."
    exit 1
fi

if [[ "$(uname)" == "Darwin" ]] && command -v brew >/dev/null 2>&1; then
    brew services start postgresql@16 >/dev/null 2>&1 || true
fi

if ! "$PSQL_BIN" -h localhost -U postgres -d postgres -c '\q' >/dev/null 2>&1; then
    echo "    creating 'postgres' role (matches DATABASE_URL in .env.example)"
    "$CREATEUSER_BIN" -h localhost -s postgres 2>/dev/null || true
    "$PSQL_BIN" -h localhost -U "$(whoami)" -d postgres \
        -c "ALTER USER postgres WITH PASSWORD 'postgres';" >/dev/null
fi

for db in email_marketing email_marketing_test; do
    exists=$("$PSQL_BIN" -h localhost -U postgres -d postgres -tAc \
        "SELECT 1 FROM pg_database WHERE datname = '$db'")
    if [ "$exists" != "1" ]; then
        echo "    creating database $db"
        "$CREATEDB_BIN" -h localhost -U postgres "$db"
    fi
    "$PSQL_BIN" -h localhost -U postgres -d "$db" \
        -c "CREATE EXTENSION IF NOT EXISTS citext; CREATE EXTENSION IF NOT EXISTS pgcrypto;" >/dev/null
done

echo "==> Running migrations"
alembic upgrade head
DATABASE_URL="$TEST_DATABASE_URL" alembic upgrade head

echo ""
echo "Setup complete. Start the API with:"
echo ""
echo "    cd backend && source .venv/bin/activate && uvicorn app.main:app --reload"
echo ""
echo "Then open http://127.0.0.1:8000/docs - see docs/getting-started.md for a feature tour"
echo "and docs/api/testing.md for a full endpoint-by-endpoint walkthrough."
