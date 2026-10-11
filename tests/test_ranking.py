from datetime import date, timedelta

from day_plan import DayPlan, PlanItem
from models import Menu, Plan
from posts import Summary
from ranking import (LOW_DEAL_PENALTY, SEARCH_WEIGHTS, FacilityScore, is_new, plan_score, plan_weights,
                     quality_score, rank_menus, rank_plans, score_menus)


def test_is_new():
    assert is_new(date.today().isoformat())
    assert is_new((date.today() - timedelta(days=14)).isoformat())
    assert not is_new((date.today() - timedelta(days=15)).isoformat())
    assert not is_new(None)


def _m(i, list_price, benefit_price, adults=1, hits=0, ext=None):
    m = Menu(id=str(i), tenant_id="t", name=f"施設{i}", category="stay", external_rating=ext)
    m.plans = [Plan(id=f"p{i}", menu_id=str(i), name="プラン", list_price=list_price, benefit_price=benefit_price, adults=adults)]
    m.keyword_hits = hits
    return m


def test_quality_uses_external_only_without_reviews():
    assert quality_score(4.0, None) == 80.0
    assert quality_score(None, None) == 60.0  # どちらもなければ星3.0


def test_quality_employee_weight_grows_with_count():
    few = Summary(count=1, average=2.0)
    many = Summary(count=10, average=2.0)
    # 1件: 従業員8%・外部92%、10件以上: 従業員80%・外部20%
    assert quality_score(5.0, few) == round((0.08 * 2.0 + 0.92 * 5.0) / 5 * 100, 1)
    assert quality_score(5.0, many) == round((0.8 * 2.0 + 0.2 * 5.0) / 5 * 100, 1)


def test_deal_uses_both_amount_and_rate():
    expensive = _m(1, 40000, 30000)  # 10,000円引き（25%）
    cheap = _m(2, 10000, 5000)       # 5,000円引き（50%）
    s = score_menus([expensive, cheap], {}, {}, 0)
    # 額は expensive が満点、率は cheap が満点。どちらも 50点＋α
    assert s["1"].deal == 75.0 and s["2"].deal == 75.0


def test_low_deal_satisfaction_is_penalized():
    a, b = _m(1, 10000, 7000), _m(2, 10000, 7000)
    stats = {"2": Summary(count=5, average=4.0, deal_satisfaction=0.2, deal_count=5)}
    s = score_menus([a, b], {}, stats, 0)
    assert s["2"].penalty == LOW_DEAL_PENALTY and s["2"].total < s["1"].total


def test_rank_menus_by_total():
    a, b = _m(1, 10000, 9000), _m(2, 10000, 5000)
    s = score_menus([a, b], {}, {}, 0)
    assert [m.id for m in rank_menus([a, b], s)] == ["2", "1"]


def test_plan_weights_follow_request_text():
    assert plan_weights("できるだけ安く泊まりたい")["deal"] > SEARCH_WEIGHTS["deal"]
    assert plan_weights("家族で楽しみたい")["quality"] > SEARCH_WEIGHTS["quality"]
    assert plan_weights("のんびりしたい") == SEARCH_WEIGHTS


def _plan(area, ids, saving_each=1000, alternative=False):
    items = [PlanItem(slot="昼", kind="benefit", name=i, category="meal", menu_id=i, saving=saving_each) for i in ids]
    return DayPlan(area_id=area, area_name=area, items=items, day_trip=True, total_price=None, alternative=alternative)


def test_plan_score_rewards_more_spots_and_keeps_requested_first():
    scores = {i: FacilityScore(50, 50, 50, 0, 50.0) for i in "abc"}
    one, three = _plan("A", ["a"]), _plan("B", ["a", "b", "c"])
    assert plan_score(three, scores) > plan_score(one, scores)
    alt = _plan("C", ["a", "b", "c"], alternative=True)
    assert [p.area_id for p in rank_plans([alt, one], scores)] == ["A", "C"]