#!/usr/bin/env bash
# 로컬 DB를 파일 하나로 내보낸다 (서버로 옮겨 db_restore.sh로 복원).
#
#   ./scripts/db_dump.sh            → data/dump/dart.dump
#
# 실험용 청크(chunks_exp)는 구조만 넣고 데이터는 뺀다 (서비스에 필요 없음, 용량 절반).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/dump
OUT=data/dump/dart.dump
docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-dart}" -d "${POSTGRES_DB:-dart}" \
  --format=custom --no-owner --exclude-table-data=chunks_exp > "$OUT"
echo "저장: $OUT ($(du -h "$OUT" | cut -f1))"
