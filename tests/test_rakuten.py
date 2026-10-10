from datetime import date

import pytest

from prices import rakuten
from prices.rakuten import Credentials, dummy_price, fetch_price, hotel_url, is_rakuten_ref, meal_flags, room_totals

CREDS = Credentials("app", "key")
# 楽天の空室検索API（format=json）の応答の形。宿の情報と部屋ごとの料金が、部品に分かれて入っている
RESPONSE = {"hotels": [{"hotel": [
    {"hotelBasicInfo": {"hotelNo": 123, "hotelInformationUrl": "https://travel.rakuten.co.jp/HOTEL/123/"}},
    {"roomInfo": [{"roomBasicInfo": {"planName": "素泊まり", "withDinnerFlag": 0, "withBreakfastFlag": 0}}, {"dailyCharge": {"total": 24000, "chargeFlag": 1}}]},
    {"roomInfo": [{"roomBasicInfo": {"planName": "2食付き", "withDinnerFlag": 1, "withBreakfastFlag": 1}}, {"dailyCharge": {"total": 31000, "chargeFlag": 1}}]},
]}]}


class FakeResponse:
    def __init__(self, status, body):
        self.status_code = status
        self.body = body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def json(self):
        return self.body


def test_dummy_is_deterministic():
    a = dummy_price("H-TENSEI", date(2026, 11, 20), 1, 2)
    b = dummy_price("H-TENSEI", date(2026, 11, 20), 1, 2)
    assert a.price == b.price and a.source == "dummy"


def test_dummy_saturday_is_higher():
    fri = dummy_price("H-TENSEI", date(2026, 11, 20), 1, 2).price
    sat = dummy_price("H-TENSEI", date(2026, 11, 21), 1, 2).price
    assert sat > fri


def test_dummy_uses_reference_price():
    price = dummy_price("H-TENSEI", date(2026, 11, 20), 1, 2, reference_price=26000).price
    assert 26000 * 0.8 - 100 <= price <= 26000 * 0.98 + 100


def test_fetch_falls_back_to_dummy_without_keys():
    assert fetch_price("12345", date(2026, 11, 20), 1, 2).source == "dummy"
    assert fetch_price("12345", date(2026, 11, 20), 1, 2, Credentials("app", "")).source == "dummy"
    assert fetch_price("H-TENSEI", date(2026, 11, 20), 1, 2, CREDS).source == "dummy"


def test_is_rakuten_ref():
    assert is_rakuten_ref("12345") and not is_rakuten_ref("H-TENSEI") and not is_rakuten_ref(None)


def test_room_totals_and_url():
    assert room_totals(RESPONSE) == [24000, 31000]
    assert hotel_url(RESPONSE) == "https://travel.rakuten.co.jp/HOTEL/123/"


def test_fetch_price_calls_new_api(monkeypatch):
    calls = {}

    def fake_get(url, params, headers, timeout):
        calls.update(url=url, params=params, headers=headers)
        return FakeResponse(200, RESPONSE)

    monkeypatch.setattr(rakuten.requests, "get", fake_get)
    got = fetch_price("123", date(2026, 11, 21), 2, 2, Credentials("app", "key", "https://example.com/"))
    assert got.price == 48000 and got.source == "rakuten_api"  # 1泊目の最安 × 2泊
    assert calls["url"].startswith("https://openapi.rakuten.co.jp/")
    assert calls["headers"]["accessKey"] == "key" and "accessKey" not in calls["params"]
    assert calls["headers"]["Referer"] == "https://example.com/"
    assert calls["params"]["checkoutDate"] == "2026-11-23"


def test_fetch_price_no_vacancy(monkeypatch):
    monkeypatch.setattr(rakuten.requests, "get", lambda *a, **k: FakeResponse(404, {}))
    with pytest.raises(ValueError):
        fetch_price("123", date(2026, 11, 21), 1, 2, CREDS)


def test_room_totals_filters_by_meal():
    assert room_totals(RESPONSE, meal_flags("2食付き")) == [31000]
    assert room_totals(RESPONSE, meal_flags("素泊まり")) == [24000]
    assert room_totals(RESPONSE, meal_flags(None)) == [24000, 31000]  # 条件なしは絞らない
    assert room_totals(RESPONSE, meal_flags("朝食付き")) == []  # 合う部屋がない
