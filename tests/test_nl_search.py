"""nl_search.py のテスト。AI は使わない（AI が返す形の dict を直接渡す）。

宿代の予算は「1泊・1人あたり」にそろえる（宿泊の料金プランを1人あたりの金額として扱うため）。
"""
from __future__ import annotations

import datetime

from nl_search import normalize_conditions, parse_with_rules

TODAY = datetime.date(2026, 10, 6)


def budget_of(**raw) -> object:
    return normalize_conditions(raw, TODAY)["budget"]


def test_budget_per_person_per_night():
    # 「1人1泊1万円、3人、2泊」→ そのまま 10,000円
    assert budget_of(people=3, budget_amount=10000, budget_per_person=True, budget_per_night=True, nights=2) == 10000


def test_budget_for_group_per_night():
    # 「2人で1泊2万円」→ 1人あたり 10,000円
    assert budget_of(people=2, budget_amount=20000, budget_per_person=False, budget_per_night=True) == 10000


def test_budget_for_group_whole_trip():
    # 「3人で2泊6万円」→ 1泊・1人あたり 10,000円
    assert budget_of(people=3, budget_amount=60000, budget_per_person=False, budget_per_night=False, nights=2) == 10000


def test_budget_per_person_for_whole_trip():
    # 「1人2万円、2泊」→ 1泊あたり 10,000円（人数は関係ない）
    assert budget_of(budget_amount=20000, budget_per_person=True, budget_per_night=False, nights=2) == 10000


def test_budget_without_nights_is_one_night():
    assert budget_of(people=2, budget_amount=30000, budget_per_person=False, budget_per_night=False) == 15000


def test_budget_per_person_without_people_is_known():
    # 1人あたりで書かれていれば、人数が分からなくても使える
    assert budget_of(budget_amount=12000, budget_per_person=True, budget_per_night=True) == 12000


def test_budget_for_group_without_people_is_unknown():
    # 全員分の金額で人数が分からなければ、1人あたりは決められないので「指定なし」
    assert budget_of(budget_amount=20000, budget_per_person=False, budget_per_night=True) is None


def test_budget_none_when_not_written():
    assert budget_of(people=2) is None


def test_rules_read_group_budget():
    # AI を使わない読み取りでも、同じ単位（1泊・1人あたり）にそろえる
    parsed = parse_with_rules("箱根に2人で1泊、予算は3万円")
    assert normalize_conditions(parsed["conditions"], TODAY)["budget"] == 15000


def test_rules_read_per_person_budget():
    parsed = parse_with_rules("熱海に4人で、1人あたり15,000円まで")
    assert normalize_conditions(parsed["conditions"], TODAY)["budget"] == 15000


def test_rules_do_not_mistake_people_count_for_per_person():
    # 「子ども1人」は人数の話で、「1人あたり」ではない
    parsed = parse_with_rules("大人2人と子ども1人の3人で1泊、予算は3万円")
    assert parsed["conditions"]["budget_per_person"] is False


def test_day_trip_is_read_and_drops_lodging_budget():
    # 日帰りなら宿代はかからないので、予算を読み取っていても「指定なし」にする
    conditions = normalize_conditions({"people": 4, "budget_amount": 3000, "budget_per_person": True,
                                       "budget_per_night": True, "day_trip": True}, TODAY)
    assert conditions["day_trip"] is True
    assert conditions["budget"] is None


def test_day_trip_is_false_unless_true():
    assert normalize_conditions({"people": 2}, TODAY)["day_trip"] is False
    assert normalize_conditions({"people": 2, "day_trip": "true"}, TODAY)["day_trip"] is False  # 文字列は使わない


def test_date_is_written():
    from nl_search import date_is_written
    assert date_is_written("1月3日に日帰りで箱根", datetime.date(2027, 1, 3))
    assert date_is_written("１２／２６に熱海", datetime.date(2026, 12, 26))  # 全角
    assert date_is_written("12 月 26 日", datetime.date(2026, 12, 26))
    # 月だけの書き方から、AI が日付を作っても使わない
    assert not date_is_written("12月に箱根の温泉旅館", datetime.date(2026, 12, 1))
    assert not date_is_written("12月26日から1泊", datetime.date(2026, 12, 6))
    assert not date_is_written("予算は1/2くらい", datetime.date(2026, 1, 20))


def test_parse_plan_drops_date_not_in_text(monkeypatch):
    import nl_search
    monkeypatch.setattr(nl_search, "llm_api_key", lambda: "key")
    monkeypatch.setattr(nl_search, "_parse_with_ai", lambda text, focus, key: {
        "summary": "", "keywords": [], "conditions": {"stay_date": "12-01", "people": 2}})
    assert nl_search.parse_plan("12月に2人で箱根", today=TODAY)["conditions"]["stay_date"] is None
    monkeypatch.setattr(nl_search, "_parse_with_ai", lambda text, focus, key: {
        "summary": "", "keywords": [], "conditions": {"stay_date": "01-03", "people": 4, "day_trip": True}})
    assert nl_search.parse_plan("1月3日に4人で日帰り", today=TODAY)["conditions"]["stay_date"] == datetime.date(2027, 1, 3)
