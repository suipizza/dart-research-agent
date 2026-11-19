import pytest

from app.ingest.categories import classify, is_correction


@pytest.mark.parametrize(
    ("report_nm", "expected"),
    [
        ("주요사항보고서(자기주식취득결정)", "treasury_acquire"),
        ("[기재정정]주요사항보고서(자기주식취득결정)", "treasury_acquire"),
        ("주요사항보고서(자기주식처분결정)", "treasury_dispose"),
        ("주요사항보고서(유상증자결정)", "rights_issue"),
        ("주요사항보고서(유무상증자결정)", "rights_bonus_issue"),  # '유상증자'보다 먼저 매칭
        ("주요사항보고서(무상증자결정)", "bonus_issue"),
        ("주요사항보고서(회사분할합병결정)", "split_merger"),
        ("연결재무제표기준영업(잠정)실적(공정공시)", "earnings_prelim"),
        ("현금ㆍ현물배당결정", "dividend"),
        ("현금·현물배당결정", "dividend"),
        ("신규시설투자등", "facility_investment"),
        ("타법인주식및출자증권취득결정", "equity_acquire"),
        ("최대주주등소유주식변동신고서", None),
        ("분기보고서 (2026.09)", None),
    ],
)
def test_classify(report_nm, expected):
    cat = classify(report_nm)
    assert (cat.key if cat else None) == expected


def test_is_correction():
    assert is_correction("[기재정정]주요사항보고서(자기주식취득결정)")
    assert not is_correction("주요사항보고서(자기주식취득결정)")
