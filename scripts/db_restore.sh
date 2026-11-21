#!/usr/bin/env bash
# db_dump.sh로 만든 파일을 DB에 복원한다. 기존 테이블은 지우고 다시 만든다.
#
#   ./scripts/db_restore.sh                     # data/dump/dart.dump
#   ./scripts/db_restore.sh path/to/dart.dump
set -euo pipefail
cd "$(dirname "$0")/.."
IN="${1:-data/dump/dart.dump}"
docker compose up -d --wait postgres
docker compose exec -T postgres pg_restore -U "${POSTGRES_USER:-dart}" -d "${POSTGRES_DB:-dart}" \
  --clean --if-exists --no-owner < "$IN"
docker compose exec -T postgres psql -U "${POSTGRES_USER:-dart}" -d "${POSTGRES_DB:-dart}" -c \
  "SELECT (SELECT count(*) FROM companies) companies, (SELECT count(*) FROM filings) filings,
          (SELECT count(*) FROM documents) documents, (SELECT count(*) FROM chunks) chunks,
          (SELECT count(*) FROM financials) financials;"
