"""documents → chunks(+임베딩) 적재.

uv run python -m app.rag.index              # 아직 청크가 없는 문서만
uv run python -m app.rag.index --rebuild    # 전부 지우고 다시 (청킹 방식을 바꿨을 때)
"""

import argparse
import logging

from sqlalchemy import delete, select

from app.db import create_tables, session_scope
from app.models import Chunk, Company, Document, Filing
from app.rag.chunker import DEFAULT_MAX_CHARS, ChunkMeta, chunk_document

log = logging.getLogger("index")


def build(rebuild: bool = False, max_chars: int = DEFAULT_MAX_CHARS, with_header: bool = True):
    from app.rag.embedder import embed  # 무거운 import는 실제 실행 때만

    create_tables()
    with session_scope() as s:
        if rebuild:
            s.execute(delete(Chunk))
        done = select(Chunk.rcept_no).distinct()
        rows = s.execute(
            select(Document.rcept_no, Document.text, Filing, Company.corp_name)
            .join(Filing, Filing.rcept_no == Document.rcept_no)
            .join(Company, Company.corp_code == Filing.corp_code)
            .where(Document.rcept_no.not_in(done))
        ).all()

    pending = []
    for rcept_no, text, filing, corp_name in rows:
        meta = ChunkMeta(corp_name, filing.rcept_dt.isoformat(), filing.report_nm)
        for c in chunk_document(text, meta, max_chars=max_chars, with_header=with_header):
            pending.append(
                {
                    "rcept_no": rcept_no,
                    "chunk_index": c.index,
                    "corp_code": filing.corp_code,
                    "rcept_dt": filing.rcept_dt,
                    "category": filing.category,
                    "section": c.section[:300],
                    "text": c.text,
                }
            )
    log.info("documents %d → chunks %d", len(rows), len(pending))
    if not pending:
        return

    vectors = embed([p["text"] for p in pending])
    for p, v in zip(pending, vectors, strict=True):
        p["embedding"] = v
    with session_scope() as s:
        for i in range(0, len(pending), 500):
            s.execute(Chunk.__table__.insert(), pending[i : i + 500])
    log.info("inserted %d chunks", len(pending))


def main() -> None:
    p = argparse.ArgumentParser(description="청크 생성과 임베딩")
    p.add_argument("--rebuild", action="store_true")
    p.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    p.add_argument("--no-header", action="store_true", help="머리말 없이 (실험용)")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    build(rebuild=args.rebuild, max_chars=args.max_chars, with_header=not args.no_header)


if __name__ == "__main__":
    main()
