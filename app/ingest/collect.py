"""DART 수집 파이프라인.

    uv run python -m app.ingest.collect all          # 전체
    uv run python -m app.ingest.collect filings      # 단계별 실행도 가능
    uv run python -m app.ingest.collect documents --limit 20

모든 단계는 다시 실행해도 안전하다(upsert). 원문은 이미 받은 것은 건너뛴다.
"""

import argparse
import csv
import logging
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db import create_tables, session_scope
from app.ingest.categories import CATEGORIES, classify, is_correction
from app.ingest.dart_client import DartClient, DartError
from app.ingest.parser import parse_zip
from app.models import Company, Document, Filing, Financial, StructuredEvent

log = logging.getLogger("ingest")

ROOT = Path(__file__).resolve().parents[2]
COMPANIES_CSV = ROOT / "data" / "companies.csv"
RAW_DOCS = ROOT / "data" / "raw" / "documents"

START = date(2024, 1, 1)
# 정기보고서 코드: 1분기, 반기, 3분기, 사업보고서(연간)
REPORT_CODES = ("11013", "11012", "11014", "11011")


def _yyyymmdd(d: date) -> str:
    return d.strftime("%Y%m%d")


def _to_int(v: str | None) -> int | None:
    if v is None:
        return None
    v = v.replace(",", "").strip()
    if v in ("", "-"):
        return None
    try:
        return int(v)
    except ValueError:
        return None


def _upsert(session, model, rows: list[dict], keys: list[str]) -> None:
    if not rows:
        return
    stmt = insert(model).values(rows)
    update_cols = {c: stmt.excluded[c] for c in rows[0] if c not in keys}
    session.execute(stmt.on_conflict_do_update(index_elements=keys, set_=update_cols))


# ── 1. 기업 ────────────────────────────────────────────────────
def sync_companies() -> list[Company]:
    with COMPANIES_CSV.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    with session_scope() as s:
        _upsert(s, Company, rows, ["corp_code"])
    log.info("companies: %d", len(rows))
    with session_scope() as s:
        return list(s.scalars(select(Company).order_by(Company.stock_code)))


# ── 2. 공시 목록 ───────────────────────────────────────────────
def collect_filings(client: DartClient, companies: list[Company], end: date) -> None:
    for c in companies:
        items = client.list_filings(c.corp_code, _yyyymmdd(START), _yyyymmdd(end))
        rows = []
        for x in items:
            cat = classify(x["report_nm"])
            rows.append(
                {
                    "rcept_no": x["rcept_no"],
                    "corp_code": c.corp_code,
                    "report_nm": x["report_nm"].strip(),
                    "rcept_dt": datetime.strptime(x["rcept_dt"], "%Y%m%d").date(),
                    "pblntf_ty": _guess_type(x),
                    "category": cat.key if cat else None,
                    "is_correction": is_correction(x["report_nm"]),
                    "flr_nm": x.get("flr_nm", ""),
                    "rm": x.get("rm", ""),
                }
            )
        with session_scope() as s:
            for i in range(0, len(rows), 500):
                _upsert(s, Filing, rows[i : i + 500], ["rcept_no"])
        targets = sum(1 for r in rows if r["category"])
        log.info("filings %s: %d (target %d)", c.corp_name, len(rows), targets)


def _guess_type(x: dict) -> str | None:
    """list.json은 공시유형을 주지 않는다. 제목으로 확실히 알 수 있는 것만 표시한다."""
    nm = x["report_nm"]
    if "주요사항보고서" in nm:
        return "B"
    if any(k in nm for k in ("사업보고서", "반기보고서", "분기보고서")):
        return "A"
    return None


# ── 3. 원문 ────────────────────────────────────────────────────
def collect_documents(client: DartClient, limit: int | None = None) -> None:
    RAW_DOCS.mkdir(parents=True, exist_ok=True)
    with session_scope() as s:
        todo = list(
            s.scalars(
                select(Filing.rcept_no)
                .outerjoin(Document, Document.rcept_no == Filing.rcept_no)
                .where(
                    Filing.category.is_not(None),
                    Document.rcept_no.is_(None),
                    # 첨부만 정정한 공시는 본문 파일이 없다 (DART 014)
                    ~Filing.report_nm.startswith("[첨부정정]"),
                )
                .order_by(Filing.rcept_dt.desc())
            )
        )
    if limit:
        todo = todo[:limit]
    log.info("documents to fetch: %d", len(todo))
    failed = 0
    for i, rcept_no in enumerate(todo, 1):
        path = RAW_DOCS / f"{rcept_no}.zip"
        try:
            if not path.exists():
                path.write_bytes(client.document_zip(rcept_no))
            parsed = parse_zip(path.read_bytes())
        except (DartError, ValueError, OSError) as e:
            failed += 1
            log.warning("document %s failed: %s", rcept_no, e)
            continue
        with session_scope() as s:
            _upsert(
                s,
                Document,
                [{"rcept_no": rcept_no, "title": parsed.title, "text": parsed.text}],
                ["rcept_no"],
            )
        if i % 25 == 0:
            log.info("documents: %d/%d", i, len(todo))
    log.info("documents done (failed %d)", failed)


# ── 4. 구조화 데이터 (주요사항 핵심 필드) ──────────────────────
def collect_structured(client: DartClient, companies: list[Company], end: date) -> None:
    apis = [c.structured_api for c in CATEGORIES if c.structured_api]
    for c in companies:
        n = 0
        for api in apis:
            items = client.structured(api, c.corp_code, _yyyymmdd(START), _yyyymmdd(end))
            rows = [
                {"rcept_no": x["rcept_no"], "api": api, "corp_code": c.corp_code, "payload": x}
                for x in items
            ]
            with session_scope() as s:
                _upsert(s, StructuredEvent, rows, ["rcept_no", "api"])
            n += len(rows)
        log.info("structured %s: %d", c.corp_name, n)


# ── 5. 재무 ────────────────────────────────────────────────────
def collect_financials(client: DartClient, companies: list[Company], end: date) -> None:
    keys = ["corp_code", "bsns_year", "reprt_code", "fs_div", "sj_div", "account_nm"]
    for c in companies:
        n = 0
        for year in range(START.year, end.year + 1):
            for code in REPORT_CODES:
                items = client.financial_accounts(c.corp_code, year, code)
                rows = {}
                for x in items:
                    row = {
                        "corp_code": c.corp_code,
                        "bsns_year": year,
                        "reprt_code": code,
                        "fs_div": x["fs_div"],
                        "sj_div": x["sj_div"],
                        "account_nm": x["account_nm"],
                        "rcept_no": x["rcept_no"],
                        "thstrm_nm": x.get("thstrm_nm", ""),
                        "thstrm_amount": _to_int(x.get("thstrm_amount")),
                        "frmtrm_amount": _to_int(x.get("frmtrm_amount")),
                        "payload": x,
                    }
                    rows[tuple(row[k] for k in keys)] = row  # 같은 키 중복 방지
                with session_scope() as s:
                    _upsert(s, Financial, list(rows.values()), keys)
                n += len(rows)
        log.info("financials %s: %d", c.corp_name, n)


# ── CLI ───────────────────────────────────────────────────────
def main() -> None:
    p = argparse.ArgumentParser(description="DART 수집")
    p.add_argument("step", choices=["all", "filings", "documents", "structured", "financials"])
    p.add_argument("--limit", type=int, help="documents 단계에서 받을 최대 건수")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # httpx는 INFO 레벨에서 요청 URL 전체(= crtfc_key 포함)를 찍는다. 키 노출 방지.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    create_tables()
    companies = sync_companies()
    end = date.today()
    with DartClient() as client:
        if args.step in ("all", "filings"):
            collect_filings(client, companies, end)
        if args.step in ("all", "documents"):
            collect_documents(client, args.limit)
        if args.step in ("all", "structured"):
            collect_structured(client, companies, end)
        if args.step in ("all", "financials"):
            collect_financials(client, companies, end)


if __name__ == "__main__":
    main()
