"""평가 지표 계산과 골드 파일 형식을 검증한다 (DB·모델 불필요)."""

from eval.retrieval import TEST, load_gold, score_one

VALID_TYPES = {"fact", "financial", "list", "compare", "summary", "trap", "refuse"}
VALID_ROUTES = {"search", "financial", "refuse"}


def test_first_hit_rank_and_mrr():
    s = score_one(["a", "b", "c"], ["c", "x"])
    assert s["first_rank"] == 3
    assert s["hit@1"] == 0 and s["hit@3"] == 1
    assert abs(s["rr"] - 1 / 3) < 1e-9
    assert s["cover@10"] == 0.5


def test_miss():
    s = score_one(["a", "b"], ["z"])
    assert s["first_rank"] is None and s["rr"] == 0.0 and s["hit@10"] == 0


def test_gold_file_is_well_formed():
    items = load_gold()
    assert len(items) == 53
    assert len({q["id"] for q in items}) == len(items)
    for q in items:
        assert q["type"] in VALID_TYPES, q["id"]
        assert q["route"] in VALID_ROUTES, q["id"]
        assert q["question"] and q["answer"], q["id"]
        assert all(len(r) == 14 and r.isdigit() for r in q["gold"]), q["id"]
        if q["route"] == "refuse":
            assert q["gold"] == [], q["id"]


def _check_items(items):
    for q in items:
        assert q["type"] in VALID_TYPES, q["id"]
        assert q["route"] in VALID_ROUTES, q["id"]
        assert q["question"] and q["answer"], q["id"]
        assert all(len(r) == 14 and r.isdigit() for r in q["gold"]), q["id"]
        if q["route"] == "refuse":
            assert q["gold"] == [], q["id"]


def test_test_set_is_well_formed_and_separate():
    dev, test = load_gold(), load_gold(TEST)
    assert len(test) == 20
    assert len({q["id"] for q in test}) == 20
    _check_items(test)
    # dev와 test는 질문이 겹치면 안 된다 (겹치면 '보지 않는 세트'가 아니다)
    assert not {q["question"] for q in dev} & {q["question"] for q in test}
    assert not {q["id"] for q in dev} & {q["id"] for q in test}
