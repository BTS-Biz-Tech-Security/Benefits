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


AREAS = [Area(id=HAKONE, code="hakone", name="箱根"), Area(id=ATAMI, code="atami", name="熱海"),
         Area(id="area-kyoto", code="kyoto", name="京都"), Area(id="area-okinawa", code="okinawa", name="沖縄")]


def test_plan_area_ids_in_result_order():
    menus = [menu("x1", "stay", area=None), menu("s1", "stay", area=ATAMI), menu("s2", "stay"),
             menu("s3", "stay", area=ATAMI), menu("s4", "stay", area="area-kyoto"), menu("s5", "stay", area="area-okinawa")]
    assert day_plan.plan_area_ids(menus) == [ATAMI, HAKONE, "area-kyoto"]
    assert day_plan.plan_area_ids(menus, limit=5) == [ATAMI, HAKONE, "area-kyoto", "area-okinawa"]


def test_build_day_plan_for_given_area():
    menus = [menu("s1", "stay", area=ATAMI), menu("s2", "stay")]
    plan = build_day_plan(menus, [], "箱根", area_id=HAKONE)
    assert plan is not None
    assert plan.area_id == HAKONE
    assert plan.items[-1].name == "施設s2"


def test_make_day_plans_one_per_area(monkeypatch):
    calls = []
    def load(tenant_id, area_id):
        calls.append((tenant_id, area_id))
        return [spot(f"sp-{area_id}", "meal")]
    monkeypatch.setattr(day_plan, "_load_spots", load)
    monkeypatch.setattr(day_plan, "list_areas", lambda tenant_id: AREAS)
    monkeypatch.setattr(day_plan, "llm_api_key", lambda: None)
    menus = [menu("s1", "stay", area=ATAMI), menu("s2", "stay"), menu("l1", "leisure", area=ATAMI)]
    plans = day_plan.make_day_plans("t", menus, "温泉")
    assert [(p.area_id, p.area_name) for p in plans] == [(ATAMI, "熱海"), (HAKONE, "箱根")]
    assert calls == [("t", ATAMI), ("t", HAKONE)]
    assert [i.name for i in plans[0].items] == ["施設l1", f"スポットsp-{ATAMI}", FREE_TIME, "施設s1"]
    assert [i.name for i in plans[1].items] == [FREE_TIME, f"スポットsp-{HAKONE}", FREE_TIME, "施設s2"]
    assert plans[1].explanation == f"箱根で、午前は自由時間、昼はスポットsp-{HAKONE}、午後は自由時間、夜は施設s2に泊まるプランです。"


def test_make_day_plans_at_most_three(monkeypatch):
    monkeypatch.setattr(day_plan, "_load_spots", lambda tenant_id, area_id: [])
    monkeypatch.setattr(day_plan, "list_areas", lambda tenant_id: AREAS)
    monkeypatch.setattr(day_plan, "llm_api_key", lambda: None)
    menus = [menu(a.id, "stay", area=a.id) for a in AREAS]
    plans = day_plan.make_day_plans("t", menus, "どこかに泊まりたい")
    assert [p.area_name for p in plans] == ["箱根", "熱海", "京都"]


def test_make_day_plans_survives_spot_load_failure(monkeypatch):
    def boom(tenant_id, area_id):
        raise RuntimeError("db down")
    monkeypatch.setattr(day_plan, "_load_spots", boom)
    monkeypatch.setattr(day_plan, "list_areas", lambda tenant_id: AREAS)
    monkeypatch.setattr(day_plan, "llm_api_key", lambda: None)
    plans = day_plan.make_day_plans("t", [menu("s1", "stay", price=30000)], "箱根で温泉")
    assert len(plans) == 1
    assert [i.kind for i in plans[0].items] == ["free", "free", "free", "benefit"]
    assert plans[0].explanation == "箱根で、午前は自由時間、昼は自由時間、午後は自由時間、夜は施設s1に泊まるプランです。"


def test_make_day_plans_empty_without_results():
    assert day_plan.make_day_plans("t", [], "箱根で温泉") == []


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


def test_marks_items_over_budget():
    menus = [menu("s1", "stay", price=28800, list_price=48000), menu("m1", "meal", price=2400, list_price=3000)]
    plan = build_day_plan(menus, [], "箱根", budget=20000)
    assert plan is not None
    assert plan.budget == 20000
    assert [(i.name, i.over_budget) for i in plan.items if i.kind == "benefit"] == [("施設m1", None), ("施設s1", 8800)]


def test_no_over_budget_without_budget():
    plan = built([menu("s1", "stay", price=28800, list_price=48000)], [])
    assert plan.items[-1].over_budget is None


def test_explain_by_rule_mentions_over_budget():
    plan = build_day_plan([menu("s1", "stay", price=28800, list_price=48000)], [], "箱根", budget=20000)
    assert plan is not None
    assert day_plan.explain_by_rule(plan) == (
        "箱根で、午前は自由時間、昼は自由時間、午後は自由時間、夜は施設s1に泊まるプランです。合計で19,200円お得です。"
        "夜の施設s1は宿代の予算を8,800円超えますが、定価より19,200円お得です。")


def test_explain_by_rule_alternative_prefix():
    plan = built([menu("s1", "stay")], [])
    plan.alternative = True
    assert day_plan.explain_by_rule(plan).startswith("ご希望のエリア以外からの代替案です。箱根で、")


def test_make_day_plans_requested_areas_first(monkeypatch):
    monkeypatch.setattr(day_plan, "_load_spots", lambda tenant_id, area_id: [])
    monkeypatch.setattr(day_plan, "list_areas", lambda tenant_id: AREAS)
    monkeypatch.setattr(day_plan, "llm_api_key", lambda: None)
    menus = [menu("s1", "stay", area="area-okinawa"), menu("s2", "stay"), menu("s3", "stay", area=ATAMI)]
    plans = day_plan.make_day_plans("t", menus, "箱根か熱海", requested_area_names=["箱根", "熱海"])
    assert [(p.area_name, p.alternative) for p in plans] == [("箱根", False), ("熱海", False), ("沖縄", True)]


def test_make_day_plans_without_requested_areas_has_no_alternative(monkeypatch):
    monkeypatch.setattr(day_plan, "_load_spots", lambda tenant_id, area_id: [])
    monkeypatch.setattr(day_plan, "list_areas", lambda tenant_id: AREAS)
    monkeypatch.setattr(day_plan, "llm_api_key", lambda: None)
    menus = [menu("s1", "stay", area="area-okinawa"), menu("s2", "stay")]
    plans = day_plan.make_day_plans("t", menus, "海に行きたい")
    assert [(p.area_name, p.alternative) for p in plans] == [("沖縄", False), ("箱根", False)]


def test_make_day_plans_passes_budget(monkeypatch):
    monkeypatch.setattr(day_plan, "_load_spots", lambda tenant_id, area_id: [])
    monkeypatch.setattr(day_plan, "list_areas", lambda tenant_id: AREAS)
    monkeypatch.setattr(day_plan, "llm_api_key", lambda: None)
    plans = day_plan.make_day_plans("t", [menu("s1", "stay", price=28800, list_price=48000)], "箱根", budget=20000)
    assert plans[0].items[-1].over_budget == 8800


def test_benefit_items_remember_menu_id():
    # 施設名から詳細画面へ移れるよう、福利厚生の枠は施設の id を持つ。周辺スポットと自由時間は持たない
    plan = built([menu("s1", "stay"), menu("l1", "leisure")], [spot("sp1", "meal")])
    assert [(i.name, i.menu_id) for i in plan.items] == [
        ("施設l1", "l1"), ("スポットsp1", None), (FREE_TIME, None), ("施設s1", "s1")]


def test_over_budget_only_for_stay():
    # 予算は宿代の上限なので、食事・レジャーには当てはめない
    menus = [menu("s1", "stay", price=28800, list_price=48000), menu("m1", "meal", price=25000, list_price=30000),
             menu("l1", "leisure", price=22000, list_price=26000)]
    plan = build_day_plan(menus, [], "箱根", budget=20000)
    assert plan is not None
    assert [(i.name, i.over_budget) for i in plan.items if i.kind == "benefit"] == [
        ("施設l1", None), ("施設m1", None), ("施設s1", 8800)]
