"""ui/results_page.py の並べ替え（sort_key）のテスト。DB と画面は使わない。"""
from __future__ import annotations

from typing import Optional

from day_plan import PlanItem
from models import Menu
from ui.results_page import sort_key


def card(order: int, menu_id: str, price: Optional[int], saving: Optional[int]) -> tuple[int, Menu, PlanItem]:
    """一覧のカード1枚分（受け取った順・施設・カードに出す料金プラン）。料金プランがない施設は price・saving が None。"""
    menu = Menu(id=menu_id, tenant_id="t", name=f"施設{menu_id}", category="stay")
    item = PlanItem(slot="", kind="benefit", name=menu.name, category="stay", menu_id=menu_id, price=price, saving=saving)
    return order, menu, item


# 受け取った順（ranking の共通スコアの順）は a → b → c → d
CARDS = [card(0, "a", 13000, 2000), card(1, "b", None, None), card(2, "c", 9000, 5000), card(3, "d", 20000, -1000)]


def sorted_ids(mode: str, ratings: Optional[dict] = None) -> list[str]:
    return [m.id for _, m, _ in sorted(CARDS, key=lambda it: sort_key(it, mode, ratings or {}))]


def test_ranked_keeps_given_order():
    assert sorted_ids("ranked") == ["a", "b", "c", "d"]


def test_price_sorts_by_card_price_and_puts_no_plan_last():
    # カードに出している金額（1人あたり）の安い順。料金プランのない b は末尾
    assert sorted_ids("price") == ["c", "a", "d", "b"]


def test_price_uses_card_price_not_cheapest_plan():
    # 宿A はカードに 2食付き 15,000円（お得額が最大）を出す。素泊まり 8,000円があっても、カードの金額で並べる
    stay_a = card(0, "A", 15000, 6000)
    stay_b = card(1, "B", 12000, 3000)
    assert [m.id for _, m, _ in sorted([stay_a, stay_b], key=lambda it: sort_key(it, "price", {}))] == ["B", "A"]


def test_diff_sorts_by_saving_and_puts_no_plan_last():
    # お得額の大きい順。お得額がマイナス（市場価格の方が安い）の d も、料金プランのない b より前
    assert sorted_ids("diff") == ["c", "a", "d", "b"]


def test_rating_sorts_by_employee_rating():
    # 社員の評価（平均）の高い順。口コミのない施設は後ろ
    assert sorted_ids("rating", {"c": (3, 4.5), "d": (1, 3.0)})[:2] == ["c", "d"]
