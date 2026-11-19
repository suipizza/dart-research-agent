# DART 공시 리서치 에이전트

상장사 공시에 대해 물으면 **공시 원문 근거**와 **정확한 수치**로 답하고, 답변의 숫자가 원문과 맞는지 스스로 검증하는 LangGraph 기반 RAG 에이전트입니다.

> 개발 중입니다. 구조도, 실험 결과, 데모 링크는 진행하면서 채웁니다.

## 로컬 실행

```bash
cp .env.example .env          # DART_API_KEY 입력
docker compose up -d          # Postgres + pgvector
uv sync                       # 의존성 설치
uv run pytest                 # 테스트
```

## 데이터 수집

```bash
uv run python -m app.ingest.collect all          # 전체 (다시 실행해도 안전)
uv run python -m app.ingest.collect documents    # 단계별 실행: filings / documents / structured / financials
```

| 수집 대상 | 범위 |
|---|---|
| 기업 | 코스피 대형주 30개 ([data/companies.csv](data/companies.csv), 2026-11 기준 고정) |
| 기간 | 2024-01-01 ~ 현재 |
| 공시 목록 | 대상 기업의 전체 공시 메타데이터 |
| 공시 원문 | 자기주식 취득·처분, 유상·무상증자, 합병·분할, 타법인 주식 취득, 신규 시설 투자, 영업(잠정)실적, 배당, 주식 소각 |
| 구조화 데이터 | 주요사항보고서 핵심 필드 (숫자 검증의 정답지) |
| 재무 | 단일회사 주요계정 (분기·반기·연간) |

수집하면서 확인한 DART API의 특이점:
- `[첨부정정]` 공시는 본문 없이 첨부만 바뀐 것이라 원문(document.xml)이 없다 → 원문 수집에서 제외
- 요청이 몰리면 HTTP 200에 **빈 본문**을 보내는 경우가 있다 → 일시 오류로 보고 재시도
- 원문은 주요사항보고서는 DART 전용 XML, 거래소 공시는 HTML → lxml HTML 파서로 통일

## 기술 스택

Python · FastAPI · LangGraph · PostgreSQL + pgvector · Redis · Docker · GitHub Actions · AWS
