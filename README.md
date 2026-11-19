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

## 기술 스택

Python · FastAPI · LangGraph · PostgreSQL + pgvector · Redis · Docker · GitHub Actions · AWS
