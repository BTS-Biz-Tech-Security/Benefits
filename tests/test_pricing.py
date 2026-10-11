from datetime import date, datetime

from models import MarketPrice, Plan
from pricing import best_plan_saving, normalize, plan_saving


def plan(**kw):
    base = dict(id="p1", menu_id="m1", name="基本", list_price=30000, benefit_price=18000, nights=1, adults=2)
    base.update(kw)
    return Plan(**base)


def market(**kw):
    base = dict(menu_id="m1", checkin=date(2026, 11, 22), nights=1, adults=2, price=26000, source="rakuten_api", fetched_at=datetime(2026, 9, 22, 9, 0))
    base.update(kw)
    return MarketPrice(**base)



def test_normalize_adults():
    price, ref = normalize(market(adults=1, price=13000), plan(adults=2))
    assert price == 26000 and ref


def test_normalize_nights():
    price, ref = normalize(market(nights=2, price=52000), plan(nights=1))
    assert price == 26000 and ref


def test_plan_saving_uses_market_price():
    s = plan_saving(plan(), market())  # 市場価格 26,000円・福利厚生 18,000円（2名分）
    assert (s.benefit_price, s.compared_price, s.compared_to, s.saving, s.saving_rate) == (9000, 13000, "市場価格", 4000, 31)


def test_plan_saving_falls_back_to_list_price():
    s = plan_saving(plan(), None)  # 定価 30,000円・福利厚生 18,000円（2名分）
    assert (s.benefit_price, s.compared_price, s.compared_to, s.saving, s.saving_rate) == (9000, 15000, "定価", 6000, 40)


def test_plan_saving_aligns_market_to_plan_people():
    s = plan_saving(plan(), market(adults=1, price=13000))  # 1名分の市場価格 → 2名分にそろえてから1人あたり
    assert s.compared_price == 13000 and s.compared_to == "市場価格"


def test_best_plan_saving_picks_max_saving():
    plans = [plan(id="a", benefit_price=20000), plan(id="b", benefit_price=15000)]
    markets = {"a": market(), "b": market()}
    s = best_plan_saving(plans, markets)  # 1人あたりのお得額は 3,000円と 5,500円
    assert s.benefit_price == 7500 and s.saving == 5500
    assert best_plan_saving([], markets) is None
    # 市場価格のないプランは定価と比べる
    assert best_plan_saving(plans, {}).compared_to == "定価"