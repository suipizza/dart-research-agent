"""질문 → 관련 공시 청크 검색.

    uv run python -m app.rag.search "SK하이닉스 2026년 3분기 영업이익"
    uv run python -m app.rag.search "자사주 소각" --since 2026-01-01 -k 10

질문에서 회사명을 찾으면 corp_code로 필터를 걸고, 그 안에서 의미가 가까운 순으로 정렬한다.
"""

import argparse
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select

from app.db import session_scope
from app.models import Chunk, Company, Filing
from app.rag.companies import build_lookup, find_companies


@dataclass
class Hit:
    distance: float
    corp_name: str
    rcept_dt: date
    report_nm: str
    rcept_no: str
    text: str
    chunk_index: int = 0  # 공시 안에서의 청크 순서

    @property
    def url(self) -> str:
        return f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={self.rcept_no}"


def search(
    query: str,
    top_k: int = 5,
    corp_codes: list[str] | None = None,
    since: date | None = None,
    until: date | None = None,
    categories: list[str] | None = None,
    detect_company: bool = True,
) -> tuple[list[Hit], list[str]]:
    """(검색 결과, 적용된 corp_code 필터)를 돌려준다."""
    from app.rag.embedder import embed_query

    with session_scope() as s:
        if corp_codes is None and detect_company:
            names = dict(s.execute(select(Company.corp_name, Company.corp_code)).all())
            corp_codes = find_companies(query, build_lookup(names)) or None

        vec = embed_query(query)
        distance = Chunk.embedding.cosine_distance(vec).label("distance")
        stmt = (
            select(distance, Company.corp_name, Filing.rcept_dt, Filing.report_nm, Chunk)
            .join(Filing, Filing.rcept_no == Chunk.rcept_no)
            .join(Company, Company.corp_code == Chunk.corp_code)
        )
        if corp_codes:
            stmt = stmt.where(Chunk.corp_code.in_(corp_codes))
        if since:
            stmt = stmt.where(Chunk.rcept_dt >= since)
        if until:
            stmt = stmt.where(Chunk.rcept_dt <= until)
        if categories:
            stmt = stmt.where(Chunk.category.in_(categories))
        rows = s.execute(stmt.order_by(distance).limit(top_k)).all()

    hits = [
        Hit(float(d), name, dt, nm, c.rcept_no, c.text, c.chunk_index)
        for d, name, dt, nm, c in rows
    ]
    return hits, corp_codes or []


def main() -> None:
    p = argparse.ArgumentParser(description="공시 검색")
    p.add_argument("query")
    p.add_argument("-k", type=int, default=5)
    p.add_argument("--since", type=date.fromisoformat)
    p.add_argument("--until", type=date.fromisoformat)
    p.add_argument("--chars", type=int, default=300, help="결과마다 보여줄 글자 수")
    args = p.parse_args()

    hits, codes = search(args.query, top_k=args.k, since=args.since, until=args.until)
    print(f"질문: {args.query}")
    print(f"회사 필터: {codes or '없음'}\n")
    for i, h in enumerate(hits, 1):
        print(f"#{i}  거리 {h.distance:.3f} | {h.corp_name} | {h.rcept_dt} | {h.report_nm}")
        print(f"    {h.url}")
        body = h.text.split("\n", 1)[-1]  # 머리말 줄은 위에 이미 출력
        print("    " + body[: args.chars].replace("\n", "\n    "))
        print()


if __name__ == "__main__":
    main()
