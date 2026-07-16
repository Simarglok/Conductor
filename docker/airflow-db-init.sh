#!/bin/bash
# Create per-project Airflow databases in PostgreSQL
set -e
PGPASSWORD="${CONDUCTOR_DB_PASSWORD:-conductor}" psql \
  -h "${CONDUCTOR_DB_HOST:-postgres}" \
  -U "${CONDUCTOR_DB_USER:-conductor}" \
  -d postgres \
  -c "CREATE DATABASE airflow_dw;" 2>/dev/null || true
PGPASSWORD="${CONDUCTOR_DB_PASSWORD:-conductor}" psql \
  -h "${CONDUCTOR_DB_HOST:-postgres}" \
  -U "${CONDUCTOR_DB_USER:-conductor}" \
  -d postgres \
  -c "CREATE DATABASE airflow_mktg;" 2>/dev/null || true
echo "Airflow databases created (or already exist)"