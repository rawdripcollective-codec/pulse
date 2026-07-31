#!/usr/bin/env bash
# Initialize the Pulse database schema.
# Runs Alembic migrations against the configured database.

set -euo pipefail

cd "$(dirname "$0")/.."

echo "→ Running Alembic migrations against $DATABASE_URL"

cd backend
alembic upgrade head

echo "✓ Migrations complete"
