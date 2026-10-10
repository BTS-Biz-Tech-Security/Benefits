from datetime import date, datetime, timedelta, timezone

from models import Menu
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

    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self

    def execute(self):
        self.db.calls.append((self.op, self.payload, self.filters))
        return type("R", (), {"data": self.db.rows if self.op == "select" else []})()


class FakeDB:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def table(self, name):
        return FakeQuery(self, name)


def menu(id="m1", category="stay", hotel_ref="12345"):
    return Menu(id=id, tenant_id="t", name="宿", category=category, hotel_ref=hotel_ref)


def row(price=20000, fetched_at=NOW - timedelta(hours=7), source="rakuten_api", checkin=CHECKIN, menu_id="m1"):
    return {"menu_id": menu_id, "checkin": checkin.isoformat(), "price": price, "source": source,
            "fetched_at": fetched_at.isoformat()}


def run(db, menus, price=20000, fetch=None):
    fetch = fetch or (lambda *a, **k: Fetched(price, "rakuten_api", None))
    return refresh.refresh_market_prices(menus, table=db.table, creds=CREDS, checkin=CHECKIN, now=NOW, fetch=fetch)


def ops(db):
    return [c[0] for c in db.calls]


def test_overwrites_when_price_differs():
    db = FakeDB([row(price=20000)])
    assert run(db, [menu()], price=22000) == 1
    assert ops(db) == ["select", "update", "insert"]  # 前の値の印を外して、新しい値を入れる
    assert db.calls[2][1]["price"] == 22000 and db.calls[2][1]["is_representative"] is True


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
    menus = [menu(id=f"m{i}") for i in range(refresh.MAX_PER_SEARCH + 3)]
    assert run(db, menus, price=20000) == refresh.MAX_PER_SEARCH


def test_needs_refresh_when_checkin_differs():
    assert refresh.needs_refresh(row(fetched_at=NOW, checkin=date(2026, 10, 10)), CHECKIN, NOW)
