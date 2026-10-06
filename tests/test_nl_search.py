"""nl_search.py のテスト。AI は使わない（AI が返す形の dict を直接渡す）。"""
from __future__ import annotations

import datetime

from nl_search import normalize_conditions

TODAY = datetime.date(2026, 10, 6)


def budget_of(**raw) -> object:
    return normalize_conditions(raw, TODAY)["budget"]


def test_budget_per_person_per_night():
    # 「1人1泊1万円、3人、2泊」→ 1泊・全員分で 30,000円（泊数は掛けない）
    assert budget_of(people=3, budget_amount=10000, budget_per_person=True, budget_per_night=True, nights=2) == 30000


def test_budget_for_whole_trip():
    # 「2泊で6万円」→ 1泊あたり 30,000円
    assert budget_of(budget_amount=60000, budget_per_person=False, budget_per_night=False, nights=2) == 30000


def test_budget_per_person_for_whole_trip():
    # 「1人2万円、3人、2泊」→ 全員で6万円 → 1泊あたり 30,000円
    assert budget_of(people=3, budget_amount=20000, budget_per_person=True, budget_per_night=False, nights=2) == 30000


def test_budget_per_night():
    # 「1泊3万円、2泊」→ 30,000円
    assert budget_of(budget_amount=30000, budget_per_person=False, budget_per_night=True, nights=2) == 30000


def test_budget_without_nights_is_one_night():
    assert budget_of(budget_amount=30000, budget_per_person=False, budget_per_night=False) == 30000


def test_budget_per_person_without_people_is_unknown():
    # 1人あたりの金額だけで人数が分からなければ、全員分は決められないので「指定なし」
    assert budget_of(budget_amount=10000, budget_per_person=True, budget_per_night=True) is None


def test_budget_old_form_still_works():
    # 以前の形（budget に合計金額）で返ってきても読める
    assert budget_of(budget=50000) == 50000


def test_budget_none_when_not_written():
    assert budget_of(people=2) is None
