#!/bin/bash
# Initialize PostgreSQL with both production and test databases
#
# This script runs when the PostgreSQL container starts for the first time.
# It creates the h_arcane_test database alongside the main h_arcane database.

set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE DATABASE h_arcane_test;
    GRANT ALL PRIVILEGES ON DATABASE h_arcane_test TO h_arcane;
EOSQL

echo "✅ Created h_arcane_test database"

