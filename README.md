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
| 기업 | 코스피 시가총액 상위 40개 전체 + 4개 = 44개 ([data/companies.csv](data/companies.csv), 2026-11-18 종가 기준 고정, 보통주) |
| 기간 | 2024-01-01 ~ 현재 |
| 공시 목록 | 대상 기업의 전체 공시 메타데이터 |
| 공시 원문 | 자기주식 취득·처분, 유상·무상증자, 합병·분할, 타법인 주식 취득, 신규 시설 투자, 영업(잠정)실적, 배당, 주식 소각 |
| 구조화 데이터 | 주요사항보고서 핵심 필드 (숫자 검증의 정답지) |
| 재무 | 단일회사 주요계정 (분기·반기·연간) |

수집하면서 확인한 DART API의 특이점:
- `[첨부정정]` 공시는 본문 없이 첨부만 바뀐 것이라 원문(document.xml)이 없다 → 원문 수집에서 제외
- 요청이 몰리면 HTTP 200에 **빈 본문**을 보내는 경우가 있다 → 일시 오류로 보고 재시도
- 원문은 주요사항보고서는 DART 전용 XML, 거래소 공시는 HTML → lxml HTML 파서로 통일

## 검색 (RAG)

```bash
uv run python -m app.rag.index                                  # 청킹 + 임베딩 (bge-m3, 로컬)
uv run python -m app.rag.search "SK하이닉스 2026년 3분기 영업이익"   # 검색
```

- **청킹**: `##` 섹션 단위 → 길면 줄 단위로 약 1,000자씩. 표는 한 행이 한 줄이라 행 중간에서 잘리지 않는다.
- **머리말**: 각 청크 앞에 `[회사 | 날짜 | 공시명 | 섹션]`을 붙인다. 표 조각만으로는 어느 회사·어떤 공시의 숫자인지 알 수 없기 때문 (`--no-header`로 끄고 비교 실험 가능).
- **표지 제외**: 주소·전화번호만 있는 표지는 회사명 검색에 과하게 걸려 제외.
- **회사 필터**: 질문에서 회사명(별칭 포함)을 찾으면 `WHERE corp_code = ...`로 고정한 뒤 그 안에서 코사인 거리순 정렬. 벡터 검색은 '삼성전자'와 '삼성SDI'를 잘 구분하지 못한다.
- **인덱스**: pgvector HNSW (`vector_cosine_ops`).

## 기술 스택

Python · FastAPI · LangGraph · PostgreSQL + pgvector · Redis · Docker · GitHub Actions · AWS
