#!/usr/bin/env bash
# 6단계 검색 비교 실험. 중간에 멈춰도 다시 실행하면 이어서 한다.
#
#   caffeinate -i ./scripts/overnight.sh
#     caffeinate -i : 실행 중 맥이 잠들지 않게 한다 (덮개는 열어 둘 것)
#
# 이어하기
#   - 재인덱싱은 문서 100건마다 저장하고, 다시 실행하면 아직 안 된 문서부터 한다.
#   - 평가는 버전 하나가 끝날 때마다 저장하고, 다시 실행하면 끝난 버전은 건너뛴다.
#   - 완전히 처음부터: rm eval/results/experiments-checkpoint.json 후
#     docker compose exec -T postgres psql -U dart -d dart -c "DELETE FROM chunks_exp;"
#
# 순서 (재인덱싱이 필요 없는 재순위 실험을 먼저 해서, 중간에 꺼도 가장 궁금한 결과부터 남게)
#   1. A, A+R20, A+R    재순위 효과        약 30분
#   2. B 인덱싱 → B     머리말 없음         약 1시간
#   3. C 인덱싱 → C, C+R 표 열 이름 반복     약 1시간 20분
# LLM 비용 없음.
set -euo pipefail
cd "$(dirname "$0")/.."
LOG="data/logs/overnight-$(date +%Y%m%d-%H%M).log"
mkdir -p data/logs
export HF_HUB_OFFLINE=1   # 모델은 이미 받아 둠
exec > >(tee -a "$LOG") 2>&1

step() { echo; echo "== $(date '+%F %T') $*"; }

step "시작 (로그: $LOG)"
docker compose up -d --wait

step "1/3 재순위 비교: A, A+R20, A+R"
uv run python -m eval.experiments --variants A A+R20 A+R

step "2/3 B 인덱싱 (머리말 없음) → 평가"
uv run python -m app.rag.index --variant no_header --no-header
uv run python -m eval.experiments --variants B

step "3/3 C 인덱싱 (잘린 표에 열 이름 반복) → 평가"
uv run python -m app.rag.index --variant table_header --repeat-table-header
uv run python -m eval.experiments --variants C C+R

step "전체 비교표"
uv run python -m eval.experiments --variants A B C A+R20 A+R C+R

step "끝"
