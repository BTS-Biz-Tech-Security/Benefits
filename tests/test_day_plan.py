"""day_plan.py のテスト。DB と AI は使わない。"""
from __future__ import annotations

from typing import Optional

import day_plan
from day_plan import FREE_TIME, DayPlan, Spot, build_day_plan, plan_area_id
from models import Area, Menu, Plan

HAKONE = "area-hakone"
ATAMI = "area-atami"


def menu(id: str, category: str, area: Optional[str] = HAKONE, price: Optional[int] = None,
         list_price: Optional[int] = None) -> Menu:
    """price は福利厚生価格、list_price は定価（省略すると price と同じ＝お得額0）。"""
    plans = [Plan(id=f"p-{id}", menu_id=id, name="plan", list_price=list_price or price, benefit_price=price)] if price else []
    return Menu(id=id, tenant_id="t", name=f"施設{id}", category=category, area_id=area, plans=plans)


def spot(id: str, kind: str) -> Spot:
    return Spot(id=id, kind=kind, name=f"スポット{id}")


def built(menus: list[Menu], spots: list[Spot], area_name: str = "箱根") -> DayPlan:
    plan = build_day_plan(menus, spots, area_name)
    assert plan is not None
    return plan


def summary(plan: DayPlan) -> list[tuple[str, str, str]]:
    return [(i.slot, i.name, i.kind) for i in plan.items]


def test_all_slots_filled_from_results():
    menus = [menu("s1", "stay", price=30000), menu("l1", "leisure", price=3000),
             menu("m1", "meal", price=2000), menu("l2", "leisure", price=1000)]
    plan = built(menus, [])
    assert summary(plan) == [("午前", "施設l1", "benefit"), ("昼", "施設m1", "benefit"),
                             ("午後", "施設l2", "benefit"), ("夜", "施設s1", "benefit")]
    assert plan.area_id == HAKONE
    assert plan.area_name == "箱根"
    assert plan.day_trip is False
    assert plan.total_price == 36000


def test_missing_slots_filled_with_spots():
    menus = [menu("s1", "stay", price=30000)]
    spots = [spot("sp1", "meal"), spot("sp2", "leisure"), spot("sp3", "leisure")]
    plan = built(menus, spots)
    assert summary(plan) == [("午前", "スポットsp2", "spot"), ("昼", "スポットsp1", "spot"),
                             ("午後", "スポットsp3", "spot"), ("夜", "施設s1", "benefit")]
    assert plan.total_price == 30000


def test_free_time_when_nothing_fits():
    plan = built([menu("s1", "stay")], [])
    assert summary(plan) == [("午前", FREE_TIME, "free"), ("昼", FREE_TIME, "free"),
                             ("午後", FREE_TIME, "free"), ("夜", "施設s1", "benefit")]
    assert plan.total_price is None


def test_day_trip_without_stay():
    plan = built([menu("l1", "leisure", price=3000)], [spot("sp1", "meal")])
    assert summary(plan) == [("午前", "施設l1", "benefit"), ("昼", "スポットsp1", "spot"),
                             ("午後", FREE_TIME, "free")]
    assert plan.day_trip is True
    assert plan.total_price == 3000


def test_uses_area_of_top_result_only():
    menus = [menu("s1", "stay", area=ATAMI), menu("s2", "stay"), menu("l1", "leisure")]
    plan = built(menus, [], "熱海")
    assert plan.area_id == ATAMI
    assert summary(plan) == [("午前", FREE_TIME, "free"), ("昼", FREE_TIME, "free"),
                             ("午後", FREE_TIME, "free"), ("夜", "施設s1", "benefit")]


def test_same_place_is_not_used_twice():
    plan = built([menu("l1", "leisure")], [spot("sp1", "leisure")])
    assert [i.name for i in plan.items if i.category == "leisure"] == ["施設l1", "スポットsp1"]


def test_skips_results_without_area():
    menus = [menu("x1", "stay", area=None), menu("s1", "stay")]
    assert plan_area_id(menus) == HAKONE


def test_no_plan_without_area():
    assert build_day_plan([], [], "箱根") is None
    assert build_day_plan([menu("x1", "stay", area=None)], [], "箱根") is None


def test_explain_by_rule_with_stay():
    plan = built([menu("s1", "stay"), menu("l1", "leisure"), menu("m1", "meal"), menu("l2", "leisure")], [])
    assert day_plan.explain_by_rule(plan) == "箱根で、午前は施設l1、昼は施設m1、午後は施設l2、夜は施設s1に泊まるプランです。"


def test_explain_by_rule_day_trip():
    plan = built([menu("l1", "leisure")], [spot("sp1", "meal")])
    assert day_plan.explain_by_rule(plan) == "箱根で、午前は施設l1、昼はスポットsp1、午後は自由時間を楽しむ日帰りのプランです。"


def test_explain_without_key_uses_rule(monkeypatch):
    monkeypatch.setattr(day_plan, "llm_api_key", lambda: None)
    plan = built([menu("s1", "stay")], [])
    assert day_plan.explain(plan, "温泉に行きたい") == day_plan.explain_by_rule(plan)


def test_explain_falls_back_when_ai_fails(monkeypatch):
    def boom(plan, request_text, api_key):
        raise RuntimeError("network error")
    monkeypatch.setattr(day_plan, "llm_api_key", lambda: "dummy")
    monkeypatch.setattr(day_plan, "_explain_with_ai", boom)
    plan = built([menu("s1", "stay")], [])
    assert day_plan.explain(plan, "温泉に行きたい") == day_plan.explain_by_rule(plan)


def test_explain_falls_back_when_ai_returns_empty(monkeypatch):
    monkeypatch.setattr(day_plan, "llm_api_key", lambda: "dummy")
    monkeypatch.setattr(day_plan, "_explain_with_ai", lambda plan, request_text, api_key: "")
    plan = built([menu("s1", "stay")], [])
    assert day_plan.explain(plan, "温泉に行きたい") == day_plan.explain_by_rule(plan)


def test_explain_uses_ai_text(monkeypatch):
    monkeypatch.setattr(day_plan, "llm_api_key", lambda: "dummy")
    monkeypatch.setattr(day_plan, "_explain_with_ai", lambda plan, request_text, api_key: "AIの説明です。")
    plan = built([menu("s1", "stay")], [])
    assert day_plan.explain(plan, "温泉に行きたい") == "AIの説明です。"


def test_make_day_plan_survives_spot_load_failure(monkeypatch):
    def boom(tenant_id, area_id):
        raise RuntimeError("db down")
    monkeypatch.setattr(day_plan, "_load_spots", boom)
    monkeypatch.setattr(day_plan, "list_areas", lambda tenant_id: [Area(id=HAKONE, code="hakone", name="箱根")])
    monkeypatch.setattr(day_plan, "llm_api_key", lambda: None)
    plan = day_plan.make_day_plan("t", [menu("s1", "stay", price=30000)], "箱根で温泉")
    assert plan is not None
    assert plan.area_name == "箱根"
    assert [i.kind for i in plan.items] == ["free", "free", "free", "benefit"]
    assert plan.explanation == "箱根で、午前は自由時間、昼は自由時間、午後は自由時間、夜は施設s1に泊まるプランです。"


def test_make_day_plan_uses_loaded_spots(monkeypatch):
    calls = []
    def load(tenant_id, area_id):
        calls.append((tenant_id, area_id))
        return [spot("sp1", "meal")]
    monkeypatch.setattr(day_plan, "_load_spots", load)
    monkeypatch.setattr(day_plan, "list_areas", lambda tenant_id: [Area(id=HAKONE, code="hakone", name="箱根")])
    monkeypatch.setattr(day_plan, "llm_api_key", lambda: None)
    plan = day_plan.make_day_plan("t", [menu("s1", "stay")], "箱根で温泉")
    assert plan is not None
    assert calls == [("t", HAKONE)]
    assert plan.items[1].name == "スポットsp1"


def test_make_day_plan_none_without_results():
    assert day_plan.make_day_plan("t", [], "箱根で温泉") is None


def test_picks_biggest_saving_per_slot():
    menus = [menu("l1", "leisure", price=2500, list_price=3000), menu("l2", "leisure", price=3000, list_price=5000),
             menu("l3", "leisure", price=3500, list_price=4000), menu("s1", "stay", price=20000, list_price=30000)]
    plan = built(menus, [])
    # 午前はお得額最大の l2（2,000円）。午後は 500円で同額の l1 と l3 のうち、検索結果で上位の l1
    assert [(i.slot, i.name, i.saving) for i in plan.items] == [
        ("午前", "施設l2", 2000), ("昼", FREE_TIME, None), ("午後", "施設l1", 500), ("夜", "施設s1", 10000)]
    assert plan.total_saving == 12500


def test_uses_plan_with_biggest_saving():
    m = menu("s1", "stay")
    m.plans = [Plan(id="a", menu_id="s1", name="スタンダード", list_price=18000, benefit_price=9900),
               Plan(id="b", menu_id="s1", name="デラックス", list_price=30000, benefit_price=21000)]
    night = built([m], []).items[-1]
    assert (night.plan_name, night.list_price, night.price, night.saving) == ("デラックス", 30000, 21000, 9000)


def test_saving_rate():
    item = built([menu("s1", "stay", price=9900, list_price=18000)], []).items[-1]
    assert item.saving_rate == 45


def test_explain_by_rule_mentions_total_saving():
    plan = built([menu("s1", "stay", price=21000, list_price=30000)], [])
    assert day_plan.explain_by_rule(plan).endswith("に泊まるプランです。合計で9,000円お得です。")
