from datetime import date, datetime

from models import MarketPrice, Plan
from pricing import GOOD, NO_DATA, NOT_GOOD, best_result, evaluate, normalize


def plan(**kw):
    base = dict(id="p1", menu_id="m1", name="基本", list_price=30000, benefit_price=18000, nights=1, adults=2)
    base.update(kw)
    return Plan(**base)


def market(**kw):
    base = dict(menu_id="m1", checkin=date(2026, 11, 22), nights=1, adults=2, price=26000, source="rakuten_api", fetched_at=datetime(2026, 9, 22, 9, 0))
    base.update(kw)
    return MarketPrice(**base)


def test_good():
    r = evaluate(plan(), market())
    assert r.judgement == GOOD and r.diff == 8000 and not r.reference


def test_not_good():
    r = evaluate(plan(benefit_price=27000), market())
    assert r.judgement == NOT_GOOD and r.diff == -1000


def test_no_data():
    r = evaluate(plan(), None)
    assert r.judgement == NO_DATA and r.market_price is None and r.diff is None


def test_normalize_adults():
    price, ref = normalize(market(adults=1, price=13000), plan(adults=2))
    assert price == 26000 and ref


def test_normalize_nights():
    price, ref = normalize(market(nights=2, price=52000), plan(nights=1))
    assert price == 26000 and ref


def test_best_result_picks_max_diff():
    plans = [plan(id="a", benefit_price=20000), plan(id="b", benefit_price=15000)]
    r = best_result(plans, market())
    assert r.benefit_price == 15000 and r.diff == 11000


def test_label():
    assert evaluate(plan(), market()).label == "お得"
    assert evaluate(plan(), market(adults=1, price=13000)).label == "お得（目安）"