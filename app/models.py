"""DB 테이블 정의.

companies ─┬─< filings ──── documents ──< chunks   (공시 목록 / 원문 / 검색 단위+벡터)
           │      └───────< structured_events  (주요사항 핵심 필드 = 숫자 검증의 정답지)
           └─< financials                      (재무제표 주요 계정)
"""

from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

EMBEDDING_DIM = 1024  # bge-m3


class Company(Base):
    __tablename__ = "companies"

    corp_code: Mapped[str] = mapped_column(String(8), primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(6), unique=True)
    corp_name: Mapped[str] = mapped_column(String(100))


class Filing(Base):
    """공시 목록. 대상 기업의 모든 공시를 저장하고, 수집 대상 유형만 category가 붙는다."""

    __tablename__ = "filings"

    rcept_no: Mapped[str] = mapped_column(String(14), primary_key=True)  # 접수번호
    corp_code: Mapped[str] = mapped_column(ForeignKey("companies.corp_code"), index=True)
    report_nm: Mapped[str] = mapped_column(String(300))
    rcept_dt: Mapped[date] = mapped_column(Date, index=True)
    pblntf_ty: Mapped[str | None] = mapped_column(String(1))  # A 정기, B 주요사항 (알 수 있을 때만)
    category: Mapped[str | None] = mapped_column(String(40), index=True)
    is_correction: Mapped[bool] = mapped_column(Boolean, default=False)  # [기재정정] 등
    flr_nm: Mapped[str] = mapped_column(String(100))  # 공시 제출인
    rm: Mapped[str] = mapped_column(String(50), default="")  # 비고 (유: 유가증권 등)

    @property
    def url(self) -> str:
        return f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={self.rcept_no}"


class Document(Base):
    """공시 원문을 파싱한 텍스트. 원본 ZIP은 data/raw/documents/에 보관해 재파싱할 수 있다."""

    __tablename__ = "documents"

    rcept_no: Mapped[str] = mapped_column(ForeignKey("filings.rcept_no"), primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    text: Mapped[str] = mapped_column(Text)
    parsed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StructuredEvent(Base):
    """주요사항보고서 구조화 API 응답. API마다 필드가 달라 JSONB로 통째로 저장한다."""

    __tablename__ = "structured_events"

    rcept_no: Mapped[str] = mapped_column(String(14), primary_key=True)
    api: Mapped[str] = mapped_column(String(40), primary_key=True)  # 예: tsstkAqDecsn
    corp_code: Mapped[str] = mapped_column(ForeignKey("companies.corp_code"), index=True)
    payload: Mapped[dict] = mapped_column(JSONB)


class Chunk(Base):
    """검색 단위. 원문(documents)을 잘라 임베딩한 것.

    corp_code·rcept_dt·category는 filings와 중복이지만, 벡터 검색과 같은 테이블에서
    바로 필터하려고 함께 둔다(JOIN 없이 WHERE + ORDER BY embedding <=> ...).
    """

    __tablename__ = "chunks"
    __table_args__ = (
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    rcept_no: Mapped[str] = mapped_column(ForeignKey("documents.rcept_no"), index=True)
    chunk_index: Mapped[int]
    corp_code: Mapped[str] = mapped_column(String(8), index=True)
    rcept_dt: Mapped[date] = mapped_column(Date, index=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    section: Mapped[str] = mapped_column(String(300))
    text: Mapped[str] = mapped_column(Text)  # 임베딩한 텍스트 그대로 (머리말 포함 여부는 설정 따름)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))


class ChunkExp(Base):
    """청킹 실험용 청크(6단계). 운영 검색 테이블(chunks)을 건드리지 않고 버전별로 따로 둔다."""

    __tablename__ = "chunks_exp"
    __table_args__ = (
        Index(
            "ix_chunks_exp_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    variant: Mapped[str] = mapped_column(String(40), index=True)
    rcept_no: Mapped[str] = mapped_column(String(14), index=True)
    chunk_index: Mapped[int]
    corp_code: Mapped[str] = mapped_column(String(8), index=True)
    rcept_dt: Mapped[date] = mapped_column(Date, index=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    section: Mapped[str] = mapped_column(String(300))
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))


class Financial(Base):
    """단일회사 주요계정 (fnlttSinglAcnt). 금액은 원 단위 정수."""

    __tablename__ = "financials"

    corp_code: Mapped[str] = mapped_column(ForeignKey("companies.corp_code"), primary_key=True)
    bsns_year: Mapped[int] = mapped_column(primary_key=True)
    reprt_code: Mapped[str] = mapped_column(String(5), primary_key=True)  # 11013 1Q ... 11011 연간
    fs_div: Mapped[str] = mapped_column(String(3), primary_key=True)  # CFS 연결 / OFS 별도
    sj_div: Mapped[str] = mapped_column(String(3), primary_key=True)  # BS 재무상태표 / IS 손익
    account_nm: Mapped[str] = mapped_column(String(100), primary_key=True)
    rcept_no: Mapped[str] = mapped_column(String(14))
    thstrm_nm: Mapped[str] = mapped_column(String(30))  # 당기 이름 (예: 제 58 기 3분기말)
    thstrm_amount: Mapped[int | None] = mapped_column(BigInteger)
    frmtrm_amount: Mapped[int | None] = mapped_column(BigInteger)  # 전기
    payload: Mapped[dict] = mapped_column(JSONB)
