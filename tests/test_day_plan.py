"""day_plan.py と、その表示（ui/day_plan.py の金額の文字列）のテスト。DB と AI は使わない。"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import day_plan
from day_plan import FREE_TIME, DayPlan, Spot, build_day_plan, plan_area_id
from models import Area, MarketPrice, Menu, Plan
from ui.day_plan import item_price_text, price_text

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
    assert day_plan.explain_by_rule(plan).endswith("に泊まるプランです。1人あたり合計で9,000円お得です。")


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
        "箱根で、午前は自由時間、昼は自由時間、午後は自由時間、夜は施設s1に泊まるプランです。1人あたり合計で19,200円お得です。"
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


def test_make_day_plans_requested_area_matches_part_of_name(monkeypatch):
    areas = AREAS + [Area(id="area-matsue", code="matsue", name="松江・出雲")]
    monkeypatch.setattr(day_plan, "_load_spots", lambda tenant_id, area_id: [])
    monkeypatch.setattr(day_plan, "list_areas", lambda tenant_id: areas)
    monkeypatch.setattr(day_plan, "llm_api_key", lambda: None)
    menus = [menu("s1", "stay"), menu("s2", "stay", area="area-matsue")]
    plans = day_plan.make_day_plans("t", menus, "出雲に行きたい", requested_area_names=["出雲", "島"])
    assert [(p.area_name, p.alternative) for p in plans] == [("松江・出雲", False), ("箱根", True)]


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


def stay_for_two(id: str, benefit_price: int, list_price: int, area: Optional[str] = HAKONE) -> Menu:
    """2名1室の料金プランを持つ宿（料金は2人分）。"""
    plan = Plan(id=f"p-{id}", menu_id=id, name="2名1室", list_price=list_price, benefit_price=benefit_price, adults=2)
    return Menu(id=id, tenant_id="t", name=f"施設{id}", category="stay", area_id=area, plans=[plan])


def test_stay_price_is_divided_by_people_in_plan():
    # 2名1室 21,000円（定価30,000円）→ 1人あたり 10,500円・お得額 4,500円
    night = built([stay_for_two("s1", 21000, 30000)], []).items[-1]
    assert (night.price, night.list_price, night.saving) == (10500, 15000, 4500)
    assert (night.plan_price, night.plan_people) == (21000, 2)


def test_over_budget_uses_price_per_person():
    # 宿代の予算 1人1万円: 1人あたり 10,500円なので、超えるのは 500円
    plan = build_day_plan([stay_for_two("s1", 21000, 30000)], [], "箱根", budget=10000)
    assert plan is not None
    assert plan.items[-1].over_budget == 500


def test_total_is_per_person():
    menus = [stay_for_two("s1", 21000, 30000), menu("m1", "meal", price=2400, list_price=3000)]
    plan = built(menus, [])
    assert plan.total_price == 10500 + 2400
    assert plan.total_saving == 4500 + 600


def test_best_saving_plan_compares_per_person():
    # 2名1室で 8,000円お得（1人 4,000円）と、1名で 5,000円お得なら、1人あたりで大きい後者を選ぶ
    m = Menu(id="s1", tenant_id="t", name="施設s1", category="stay", area_id=HAKONE, plans=[
        Plan(id="a", menu_id="s1", name="2名1室", list_price=28000, benefit_price=20000, adults=2),
        Plan(id="b", menu_id="s1", name="1名1室", list_price=20000, benefit_price=15000, adults=1)])
    best = day_plan.best_saving_plan(m)
    assert best is not None and best.name == "1名1室"


def test_benefit_item_budget_for_chosen_categories():
    # 「施設を検索」タブでは、選んだカテゴリにも予算超えを付けられる
    meal = menu("m1", "meal", price=6000, list_price=8000)
    assert day_plan.benefit_item("", meal, 5000).over_budget is None  # 既定は宿だけ
    assert day_plan.benefit_item("", meal, 5000, budget_categories=["meal"]).over_budget == 1000


def test_best_saving_plan_within_price_limit():
    # 上限（1人1.5万円）を渡すと、上限以内のプランの中でお得額が最大のものを選ぶ。デラックス（1人2万450円）は選ばない
    standard = Plan(id="p1", menu_id="s1", name="スタンダード", list_price=40000, benefit_price=26000, adults=2)
    deluxe = Plan(id="p2", menu_id="s1", name="デラックス", list_price=56000, benefit_price=40900, adults=2)
    m = Menu(id="s1", tenant_id="t", name="宿", category="stay", plans=[standard, deluxe])
    assert day_plan.best_saving_plan(m).name == "デラックス"
    assert day_plan.best_saving_plan(m, max_price=15000).name == "スタンダード"
    # 上限以内のプランがなければ、すべてのプランから選ぶ
    assert day_plan.best_saving_plan(m, max_price=5000).name == "デラックス"


def test_benefit_item_with_allowance_shows_plan_within_limit():
    standard = Plan(id="p1", menu_id="s1", name="スタンダード", list_price=40000, benefit_price=26000, adults=2)
    deluxe = Plan(id="p2", menu_id="s1", name="デラックス", list_price=56000, benefit_price=40900, adults=2)
    m = Menu(id="s1", tenant_id="t", name="宿", category="stay", plans=[standard, deluxe])
    item = day_plan.benefit_item("夜", m, 10000, budget_allowance=1.5)
    assert (item.plan_name, item.price, item.over_budget, item.saving) == ("スタンダード", 13000, 3000, 7000)
    # 倍率を渡さなければ（施設を検索タブ）、これまでどおりお得額が最大のプラン
    assert day_plan.benefit_item("夜", m, 10000).plan_name == "デラックス"


# --- plan_saving（pricing.plan_saving ができるまでの仮の関数）と、市場価格との比較 ---
# plan_saving の3つのテストは、tests/test_pricing.py に入る予定のもの（じゅんぺいさん作成）と同じ値にしてある


def plan_for_two(**kw) -> Plan:
    base = dict(id="p1", menu_id="m1", name="基本", list_price=30000, benefit_price=18000, nights=1, adults=2)
    base.update(kw)
    return Plan(**base)


def market_price(**kw) -> MarketPrice:
    base = dict(menu_id="m1", checkin=date(2026, 11, 22), nights=1, adults=2, price=26000, source="rakuten_api",
                fetched_at=datetime(2026, 9, 22, 9, 0))
    base.update(kw)
    return MarketPrice(**base)


def test_plan_saving_uses_market_price():
    c = day_plan.plan_saving(plan_for_two(), market_price())  # 市場価格 26,000円・福利厚生 18,000円（2名分）
    assert (c.benefit_price, c.compared_price, c.compared_to) == (9000, 13000, "市場価格")
    assert c.saving == 4000 and c.saving_rate == 31


def test_plan_saving_falls_back_to_list_price():
    c = day_plan.plan_saving(plan_for_two(), None)  # 定価 30,000円・福利厚生 18,000円（2名分）
    assert (c.benefit_price, c.compared_price, c.compared_to) == (9000, 15000, "定価")
    assert c.saving == 6000 and c.saving_rate == 40


def test_plan_saving_aligns_market_to_plan_people():
    c = day_plan.plan_saving(plan_for_two(), market_price(adults=1, price=13000))  # 1名分の価格 → 2名分にそろえてから1人あたり
    assert c.compared_price == 13000 and c.compared_to == "市場価格"


def test_benefit_item_compares_with_market_price():
    stay = Menu(id="m1", tenant_id="t", name="宿", category="stay", plans=[plan_for_two()])
    item = day_plan.benefit_item("夜", stay, None, markets={"p1": market_price()})
    assert (item.compared_to, item.compared_price, item.price, item.saving, item.saving_rate) == ("市場価格", 13000, 9000, 4000, 31)
    # 市場価格を渡さなければ、これまでどおり定価と比べる
    item = day_plan.benefit_item("夜", stay, None)
    assert (item.compared_to, item.compared_price, item.saving) == ("定価", 15000, 6000)


def test_build_day_plan_uses_market_price_only_for_that_plan():
    # 市場価格が取れた宿のプランは市場価格と、取れなかった食事は定価と比べる。2種類が1つのプランに混ざる
    stay = Menu(id="m1", tenant_id="t", name="宿", category="stay", area_id=HAKONE, plans=[plan_for_two()])
    meal = menu("m2", "meal", price=2400, list_price=3000)
    plan = build_day_plan([stay, meal], [], "箱根", markets={"p1": market_price()})
    items = {i.slot: i for i in plan.items}
    assert (items["夜"].compared_to, items["夜"].saving) == ("市場価格", 4000)
    assert (items["昼"].compared_to, items["昼"].saving) == ("定価", 600)
    assert plan.total_saving == 4600


def test_pick_menu_puts_menu_without_plans_last():
    # 料金プランのない施設は、市場価格の方が安い施設（お得額がマイナス）よりも後ろ。検索結果で上にあっても選ばない
    no_plan = menu("n1", "stay")
    stay = Menu(id="m1", tenant_id="t", name="宿", category="stay", area_id=HAKONE, plans=[plan_for_two()])
    markets = {"p1": market_price(price=16000)}  # 市場価格 1人8,000円・福利厚生 1人9,000円 → 1,000円のマイナス
    assert day_plan._pick_menu([no_plan, stay], "stay", set(), markets=markets) is stay


def test_total_saving_skips_facilities_cheaper_on_market():
    # 市場価格の方が安い宿（お得額がマイナス）は、合計のお得額に入れない
    stay = Menu(id="m1", tenant_id="t", name="宿", category="stay", area_id=HAKONE, plans=[plan_for_two()])
    meal = menu("m2", "meal", price=2400, list_price=3000)
    plan = build_day_plan([stay, meal], [], "箱根", markets={"p1": market_price(price=16000)})  # 市場価格 1人8,000円
    night = [i for i in plan.items if i.slot == "夜"][0]
    assert night.saving == -1000
    assert plan.total_saving == 600


def test_price_text_with_list_price_is_unchanged():
    # 定価と比べるときの表示は、これまでと同じ文字列
    assert price_text(14400, 24000, 9600, 40, "定価", plan_price=28800, plan_people=2) == (
        ":gray[1人あたり] :gray[~~定価 24,000円~~ →] **14,400円**　:green[**9,600円お得**（40%）]　:gray[（2名で28,800円）]")


def test_price_text_with_market_price():
    assert price_text(9000, 13000, 4000, 31, "市場価格") == (
        ":gray[~~市場価格 13,000円~~ →] **9,000円**　:green[**4,000円お得**（31%）]")
    # 市場価格の方が安いときは、お得とは出さず、そう添える
    assert price_text(9000, 8000, -1000, -12, "市場価格") == "福利厚生 9,000円　:gray[市場価格の方が1,000円安い]"
    # 定価以下のときは、これまでどおり福利厚生価格だけ
    assert price_text(5000, 5000, 0, 0, "定価") == "福利厚生 5,000円"


def test_item_price_text_matches_benefit_item():
    stay = Menu(id="m1", tenant_id="t", name="宿", category="stay", plans=[plan_for_two()])
    item = day_plan.benefit_item("夜", stay, 8000, markets={"p1": market_price()})
    assert item_price_text(item) == (":gray[1人あたり] :gray[~~市場価格 13,000円~~ →] **9,000円**　"
                                     ":green[**4,000円お得**（31%）]　:gray[（2名で18,000円）]　:orange-badge[予算＋1,000円]")


def test_best_saving_plan_mixes_market_and_list_price_per_plan():
    # 市場価格が取れたプランはそれと、取れなかったプランは定価と比べたお得額で選ぶ
    # 素泊まり: 市場価格 1人8,000円 − 福利厚生 6,000円 = 2,000円お得（定価と比べれば 4,000円だが、市場価格を使う）
    # 2食付き: 市場価格なし → 定価 1人15,000円 − 福利厚生 12,000円 = 3,000円お得
    room_only = Plan(id="p-room", menu_id="s1", name="素泊まり", list_price=20000, benefit_price=12000, nights=1, adults=2)
    two_meals = Plan(id="p-meals", menu_id="s1", name="2食付き", list_price=30000, benefit_price=24000, nights=1, adults=2)
    stay = Menu(id="s1", tenant_id="t", name="宿", category="stay", plans=[room_only, two_meals])
    markets = {"p-room": market_price(menu_id="s1", price=16000)}
    assert day_plan.best_saving_plan(stay, markets=markets).name == "2食付き"
    item = day_plan.benefit_item("夜", stay, None, markets=markets)
    assert (item.plan_name, item.compared_to, item.saving) == ("2食付き", "定価", 3000)
    # 市場価格がなければ、定価と比べて素泊まり（4,000円お得）
    assert day_plan.best_saving_plan(stay).name == "素泊まり"


def market_row(plan_id: str, menu_id: str = "s1", price: int = 26000) -> dict:
    """market_prices の1行（DB から読んだ形）。"""
    return {"menu_id": menu_id, "plan_id": plan_id, "checkin": "2026-10-10", "nights": 1, "adults": 2, "children": 0,
            "meal": None, "price": price, "source": "dummy", "source_url": None, "fetched_at": "2026-10-10T09:00:00+00:00"}


def test_load_market_prices_uses_plan_linked_prices(monkeypatch):
    # 料金プランにひも付いた価格だけを、プランの id で返す。宿泊施設の料金プランだけを読みに行く
    room_only = Plan(id="p-room", menu_id="s1", name="素泊まり", list_price=20000, benefit_price=12000)
    two_meals = Plan(id="p-meals", menu_id="s1", name="2食付き", list_price=30000, benefit_price=24000)
    stay = Menu(id="s1", tenant_id="t", name="宿", category="stay", plans=[room_only, two_meals])
    meal = menu("m1", "meal", price=2400, list_price=3000)
    asked: list[list[str]] = []

    def fake_rows(plan_ids):
        asked.append(plan_ids)
        return [market_row("p-room", price=16000)]  # 2食付きは取れなかった

    monkeypatch.setattr(day_plan, "_read_plan_market_rows", fake_rows)
    markets = day_plan.load_market_prices([stay, meal])
    assert asked == [["p-room", "p-meals"]]
    assert list(markets) == ["p-room"] and markets["p-room"].price == 16000


def test_load_market_prices_is_empty_when_reading_fails(monkeypatch):
    # plan_id の列がまだないときなど、読めなければ空（すべて定価と比べる）
    def broken(plan_ids):
        raise RuntimeError("column market_prices.plan_id does not exist")

    monkeypatch.setattr(day_plan, "_read_plan_market_rows", broken)
    assert day_plan.load_market_prices([menu("s1", "stay", price=10000)]) == {}
