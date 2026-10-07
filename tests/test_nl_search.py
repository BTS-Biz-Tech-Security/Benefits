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
