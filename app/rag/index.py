"""documents → chunks(+임베딩) 적재.

uv run python -m app.rag.index              # 아직 청크가 없는 문서만
uv run python -m app.rag.index --rebuild    # 전부 지우고 다시 (청킹 방식을 바꿨을 때)
"""

import argparse
import logging

from sqlalchemy import delete, select

from app.db import create_tables, session_scope
from app.models import Chunk, ChunkExp, Company, Document, Filing
from app.rag.chunker import DEFAULT_MAX_CHARS, ChunkMeta, chunk_document

log = logging.getLogger("index")

BATCH_DOCS = 100  # 이만큼마다 저장 (중간에 멈춰도 이어서 할 수 있게)


def build(
    rebuild: bool = False,
    max_chars: int = DEFAULT_MAX_CHARS,
    with_header: bool = True,
    repeat_table_header: bool = True,
    variant: str | None = None,
    limit_docs: int | None = None,
):
    """variant가 있으면 실험용 테이블(chunks_exp)의 그 버전에만 쓴다."""
    from app.rag.embedder import embed  # 무거운 import는 실제 실행 때만

    table = ChunkExp if variant else Chunk
    create_tables()
    with session_scope() as s:
        if rebuild:
            stmt = delete(table)
            if variant:
                stmt = stmt.where(ChunkExp.variant == variant)
            s.execute(stmt)
        done = select(table.rcept_no).distinct()
        if variant:
            done = done.where(ChunkExp.variant == variant)
        rows = s.execute(
            select(Document.rcept_no, Document.text, Filing, Company.corp_name)
            .join(Filing, Filing.rcept_no == Document.rcept_no)
            .join(Company, Company.corp_code == Filing.corp_code)
            .where(Document.rcept_no.not_in(done))
            .order_by(Document.rcept_no)
            .limit(limit_docs)
        ).all()

    def to_rows(batch) -> list[dict]:
        out = []
        for rcept_no, text, filing, corp_name in batch:
            meta = ChunkMeta(corp_name, filing.rcept_dt.isoformat(), filing.report_nm)
            for c in chunk_document(
                text,
                meta,
                max_chars=max_chars,
                with_header=with_header,
                repeat_table_header=repeat_table_header,
            ):
                out.append(
                    {
                        "rcept_no": rcept_no,
                        "chunk_index": c.index,
                        "corp_code": filing.corp_code,
                        "rcept_dt": filing.rcept_dt,
                        "category": filing.category,
                        "section": c.section[:300],
                        "text": c.text,
                        **({"variant": variant} if variant else {}),
                    }
                )
        return out

    # 문서 BATCH_DOCS건마다 임베딩하고 바로 저장한다. 중간에 끊겨도 저장된 문서는 남고,
    # 다시 실행하면 "아직 청크가 없는 문서"만 골라 이어서 한다.
    log.info("documents to index: %d (variant=%s)", len(rows), variant or "serving")
    total = 0
    for start in range(0, len(rows), BATCH_DOCS):
        batch = rows[start : start + BATCH_DOCS]
        pending = to_rows(batch)
        if not pending:
            continue
        vectors = embed([p["text"] for p in pending])
        for p, v in zip(pending, vectors, strict=True):
            p["embedding"] = v
        with session_scope() as s:
            s.execute(table.__table__.insert(), pending)
        total += len(pending)
        log.info(
            "saved %d/%d documents (%d chunks so far)",
            min(start + BATCH_DOCS, len(rows)),
            len(rows),
            total,
        )
    log.info("inserted %d chunks", total)


def main() -> None:
    p = argparse.ArgumentParser(description="청크 생성과 임베딩")
    p.add_argument("--rebuild", action="store_true")
    p.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    p.add_argument("--no-header", action="store_true", help="머리말 없이 (실험용)")
    p.add_argument(
        "--no-table-header",
        action="store_true",
        help="잘린 표에 열 이름을 반복하지 않음 (실험용. 기본은 반복, 6단계 실험 결과)",
    )
    p.add_argument("--variant", help="실험용 테이블(chunks_exp)에 이 이름으로 저장")
    p.add_argument("--limit-docs", type=int, help="문서 수 제한 (시험 실행용)")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    build(
        rebuild=args.rebuild,
        max_chars=args.max_chars,
        with_header=not args.no_header,
        repeat_table_header=not args.no_table_header,
        variant=args.variant,
        limit_docs=args.limit_docs,
    )


if __name__ == "__main__":
    main()
