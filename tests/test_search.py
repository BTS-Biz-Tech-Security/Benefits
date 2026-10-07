"""search.py のテスト（DB を使わない部分）。"""
from __future__ import annotations

from models import Menu, Plan
from search import filter_menus


def menu(id: str, category: str, price: int) -> Menu:
    plan = Plan(id=f"p-{id}", menu_id=id, name="plan", list_price=price, benefit_price=price)
    return Menu(id=id, tenant_id="t", name=f"施設{id}", category=category, plans=[plan])


def test_budget_filters_only_stays():
    # 予算は宿代の上限なので、宿泊施設だけを絞り込む。食事・レジャーは予算で外さない
    menus = [menu("s1", "stay", 30000), menu("s2", "stay", 15000), menu("m1", "meal", 25000), menu("l1", "leisure", 22000)]
    kept = filter_menus(menus, budget=20000)
    assert sorted(m.id for m in kept) == ["l1", "m1", "s2"]


def test_no_budget_keeps_all():
    menus = [menu("s1", "stay", 30000), menu("m1", "meal", 25000)]
    assert sorted(m.id for m in filter_menus(menus)) == ["m1", "s1"]


def test_budget_compares_stay_price_per_person():
    # 2名1室 18,000円は1人 9,000円なので、宿代の予算 1人1万円に収まる
    plan = Plan(id="p", menu_id="s1", name="2名1室", list_price=24000, benefit_price=18000, adults=2)
    stay = Menu(id="s1", tenant_id="t", name="施設s1", category="stay", plans=[plan])
    assert [m.id for m in filter_menus([stay], budget=10000)] == ["s1"]


def test_budget_for_chosen_category():
    # 「施設を検索」で食事を選んだときは、食事の料金と予算を比べる
    menus = [menu("m1", "meal", 6000), menu("m2", "meal", 3000), menu("s1", "stay", 30000)]
    kept = filter_menus(menus, budget=5000, budget_categories=["meal"])
    assert sorted(m.id for m in kept) == ["m2", "s1"]


def test_budget_for_all_categories():
    # 「すべて」のときは、どのカテゴリにも予算を当てはめる
    menus = [menu("m1", "meal", 6000), menu("l1", "leisure", 3000), menu("s1", "stay", 30000)]
    kept = filter_menus(menus, budget=5000, budget_categories=["stay", "meal", "leisure"])
    assert [m.id for m in kept] == ["l1"]
