#!/usr/bin/env bash
# 6단계 밤샘 실험: 청킹 버전 B·C를 실험용 테이블에 인덱싱한 뒤 A·B·C·재순위를 비교한다.
# 사용법 (프로젝트 루트에서):  caffeinate -i ./scripts/overnight.sh
#   caffeinate -i : 맥이 잠들지 않게 한다 (덮개를 닫으면 멈출 수 있으니 열어 둘 것)
# 예상 시간: 인덱싱 약 1시간 × 2 + 평가 약 40분. LLM 비용 없음.
set -euo pipefail
cd "$(dirname "$0")/.."
LOG="data/logs/overnight-$(date +%Y%m%d-%H%M).log"
mkdir -p data/logs
export HF_HUB_OFFLINE=1   # 모델은 이미 받아 둠
exec > >(tee -a "$LOG") 2>&1

echo "== $(date '+%F %T') 시작"
docker compose up -d --wait

echo "== $(date '+%F %T') B: 머리말 없음"
uv run python -m app.rag.index --variant no_header --no-header --rebuild

echo "== $(date '+%F %T') C: 머리말 + 잘린 표에 열 이름 반복"
uv run python -m app.rag.index --variant table_header --repeat-table-header --rebuild

echo "== $(date '+%F %T') 비교 평가"
uv run python -m eval.experiments

echo "== $(date '+%F %T') 끝. 로그: $LOG"
