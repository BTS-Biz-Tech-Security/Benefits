from datetime import date, datetime, timedelta, timezone

from models import Menu, Plan
from prices import refresh
from prices.rakuten import Credentials, Fetched

NOW = datetime(2026, 10, 10, 3, 0, tzinfo=timezone.utc)
CHECKIN = date(2026, 10, 17)
CREDS = Credentials("app", "key")


class FakeQuery:
    """market_prices への読み書きを記録する、Supabase のクエリの代わり。"""

    def __init__(self, db, name):
        self.db, self.name, self.op, self.payload, self.filters = db, name, "select", None, []

    def select(self, *_):
        return self

    def in_(self, col, values):
        self.filters.append((col, tuple(values)))
        return self

    def eq(self, col, value):
        self.filters.append((col, value))
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def upsert(self, payload, on_conflict=None):
        self.op, self.payload = "upsert", payload
        return self

    def execute(self):
        self.db.calls.append((self.op, self.payload, self.filters))
        return type("R", (), {"data": self.db.rows if self.op == "select" else []})()


class FakeDB:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def table(self, name):
        return FakeQuery(self, name)


def plan(id="p1", menu_id="m1", adults=2, nights=1, meal="2食付き"):
    return Plan(id=id, menu_id=menu_id, name="プラン", list_price=30000, benefit_price=18000, nights=nights, adults=adults, meal=meal)


def menu(id="m1", category="stay", hotel_ref="12345", plans=None):
    return Menu(id=id, tenant_id="t", name="宿", category=category, hotel_ref=hotel_ref, plans=plans if plans is not None else [plan(menu_id=id)])


def row(price=20000, fetched_at=NOW - timedelta(hours=7), source="rakuten_api", checkin=CHECKIN, plan_id="p1"):
    return {"plan_id": plan_id, "checkin": checkin.isoformat(), "price": price, "source": source, "fetched_at": fetched_at.isoformat()}


def run(db, menus, price=20000, fetch=None):
    fetch = fetch or (lambda *a, **k: Fetched(price, "rakuten_api", None))
    return refresh.refresh_market_prices(menus, table=db.table, creds=CREDS, dates=[CHECKIN], now=NOW, fetch=fetch)


def ops(db):
    return [c[0] for c in db.calls]


def test_overwrites_when_price_differs():
    db = FakeDB([row(price=20000)])
    assert run(db, [menu()], price=22000) == 1
    assert ops(db) == ["select", "update", "upsert"]  # 前の値の印を外して、新しい値を入れる
    saved = db.calls[2][1]
    assert saved["price"] == 22000 and saved["plan_id"] == "p1" and saved["meal"] == "2食付き" and saved["is_representative"] is True


def test_same_price_updates_only_fetched_at():
    db = FakeDB([row(price=20000)])
    assert run(db, [menu()], price=20000) == 0
    assert ops(db) == ["select", "update"]
    assert db.calls[1][1] == {"fetched_at": NOW.isoformat()}


def test_recent_value_is_not_fetched_again():
    db = FakeDB([row(fetched_at=NOW - timedelta(hours=1))])
    called = []
    assert run(db, [menu()], fetch=lambda *a, **k: called.append(a)) == 0
    assert called == [] and ops(db) == ["select"]


def test_dummy_value_is_replaced():
    db = FakeDB([row(source="dummy", fetched_at=NOW)])
    assert run(db, [menu()], price=20000) == 1


def test_fetch_uses_plan_conditions():
    calls = []

    def fake(hotel_ref, checkin, nights, adults, creds, meal=None):
        calls.append((hotel_ref, nights, adults, meal))
        return Fetched(40000, "rakuten_api", None)
    db = FakeDB([])
    assert run(db, [menu(plans=[plan(adults=3, nights=2, meal="素泊まり")])], fetch=fake) == 1
    assert calls == [("12345", 2, 3, "素泊まり")]


def test_no_credentials_does_nothing():
    db = FakeDB([])
    assert refresh.refresh_market_prices([menu()], table=db.table, creds=Credentials(), now=NOW) == 0
    assert db.calls == []


def test_only_stays_with_rakuten_number():
    db = FakeDB([])
    assert run(db, [menu(category="leisure"), menu(id="m2", hotel_ref="hotel_abc")]) == 0
    assert db.calls == []


def test_failure_keeps_db_value():
    def fail(*_a, **_k):
        raise ValueError("空室がありません")
    db = FakeDB([row()])
    assert run(db, [menu()], fetch=fail) == 0
    assert ops(db) == ["select"]


def test_limits_per_search():
    db = FakeDB([])
    plans = [plan(id=f"p{i}") for i in range(refresh.MAX_PER_SEARCH + 3)]
    assert run(db, [menu(plans=plans)], price=20000) == refresh.MAX_PER_SEARCH


def test_needs_refresh_when_checkin_differs():
    assert refresh.needs_refresh(row(fetched_at=NOW, checkin=date(2026, 10, 10)), [CHECKIN], NOW)


def test_compare_dates_are_saturdays_four_weeks_apart():
    # 2026/10/11（日）の4週間後は11/8（日）。その後の最初の土曜は11/14
    assert refresh.compare_dates(date(2026, 10, 11)) == [date(2026, 11, 14), date(2026, 12, 12), date(2027, 1, 9)]
    # 4週間後がちょうど土曜なら、その日から
    assert refresh.compare_dates(date(2026, 10, 17))[0] == date(2026, 11, 14)


def test_first_available_tries_next_date_when_not_available():
    from prices.rakuten import NotAvailable
    tried = []

    def call(d):
        tried.append(d)
        if d == date(2026, 11, 14):
            raise NotAvailable("空室がありません")
        return Fetched(30000, "rakuten_api", None)
    dates = [date(2026, 11, 14), date(2026, 12, 12), date(2027, 1, 9)]
    fetched, day = refresh.first_available(dates, call, sleep=lambda s: None)
    assert (fetched.price, day) == (30000, date(2026, 12, 12)) and tried == dates[:2]


def test_first_available_does_not_retry_on_communication_error():
    import pytest
    tried = []

    def call(d):
        tried.append(d)
        raise RuntimeError("500")
    with pytest.raises(RuntimeError):
        refresh.first_available([date(2026, 11, 14), date(2026, 12, 12)], call, sleep=lambda s: None)
    assert tried == [date(2026, 11, 14)]


def test_refresh_saves_the_date_that_was_found():
    from prices.rakuten import NotAvailable
    first, second = date(2026, 11, 14), date(2026, 12, 12)

    def fetch(hotel_ref, checkin, nights, adults, creds, meal=None):
        if checkin == first:
            raise NotAvailable("空室がありません")
        return Fetched(30000, "rakuten_api", None)
    db = FakeDB([])
    assert refresh.refresh_market_prices([menu()], table=db.table, creds=CREDS, dates=[first, second], now=NOW,
                                         fetch=fetch, sleep=lambda s: None) == 1
    assert db.calls[-1][1]["checkin"] == second.isoformat()
    # 2つ目の候補の日の値は、次の検索では取り直さない
    assert not refresh.needs_refresh(row(fetched_at=NOW, checkin=second), [first, second], NOW)
