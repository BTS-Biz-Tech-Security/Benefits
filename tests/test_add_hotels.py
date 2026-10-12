from datetime import date

from prices import add_hotels as ah


def hotel(no="1", name="宿", address="神奈川県足柄下郡箱根町湯本1", rating=4.5, count=500, charge=15000, desc="露天風呂のある温泉宿"):
    return ah.Hotel(no, name, address, desc, rating, count, charge)


def test_parse_hotels_reads_basic_info():
    data = {"hotels": [{"hotel": [{"hotelBasicInfo": {"hotelNo": 84721, "hotelName": "天成園", "address1": "神奈川県",
                                                      "address2": "足柄下郡箱根町湯本682", "hotelSpecial": "庭園露天風呂",
                                                      "reviewAverage": 4.24, "reviewCount": 4525, "hotelMinCharge": 12000}}]}]}
    h = ah.parse_hotels(data)[0]
    assert (h.hotel_no, h.address, h.rating, h.review_count, h.min_charge) == ("84721", "神奈川県足柄下郡箱根町湯本682", 4.2, 4525, 12000)


def test_pick_filters_area_quality_and_known():
    include, exclude = ["箱根町"], []
    cands = [
        hotel("1", "良い宿", rating=4.6, count=800),
        hotel("2", "もっと良い宿", rating=4.8, count=300),
        hotel("3", "熱海の宿", address="静岡県熱海市"),                 # エリア外
        hotel("4", "口コミが少ない宿", count=20),                       # 口コミが少ない
        hotel("5", "安い宿", charge=5000),                             # 最安料金が安い
        hotel("6", "箱根カプセルホテル"),                               # 名前で除外
        hotel("7", "登録済みの宿"),                                     # 番号で登録済み
        hotel("8", "箱根 天成園"),                                      # 名前で登録済み
        hotel("2", "もっと良い宿", rating=4.8, count=300),              # 重複
    ]
    got = ah.pick(cands, include, exclude, {"7"}, {"箱根天成園"}, 3)
    assert [h.hotel_no for h in got] == ["2", "1"]


def test_okinawa_excludes_ishigaki():
    _, include, exclude = ah.AREA_QUERIES["okinawa"]
    assert ah.in_area("沖縄県国頭郡恩納村", include, exclude)
    assert not ah.in_area("沖縄県石垣市真栄里", include, exclude)


def test_every_area_in_sql_has_a_query():
    import re
    from pathlib import Path
    sql = (Path(__file__).resolve().parent.parent / "sql" / "007_areas.sql").read_text(encoding="utf-8")
    codes = set(re.findall(r"\('([a-z]+)', '[^']+', '[^']+', \d+\)", sql))
    assert codes == set(ah.AREA_QUERIES)


def test_menu_and_plan_rows():
    h = hotel("123", "海辺のリゾート", desc="★全室オーシャンビュー★\n海を望む露天風呂")
    row = ah.menu_row(h, "t", "a", date(2026, 10, 12))
    assert row["hotel_ref"] == "123" and row["matched"] is True and row["external_rating_source"] == "rakuten_api"
    assert "海" in row["tags"] and "露天" in row["tags"] and "リゾート" in row["tags"]
    assert "★" not in row["description"] and "\n" not in row["description"]
    plans = ah.plan_rows(h, "m")
    assert [p["name"] for p in plans] == ["スタンダード（2食付）", "デラックス（2食付）", "素泊まり"]
    assert all(p["benefit_price"] <= p["list_price"] for p in plans)
    assert plans[0]["list_price"] == 60000 and plans[1]["list_price"] > plans[0]["list_price"]


def test_collect_stops_paging_when_page_is_short():
    calls = []

    class R:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"hotels": []}

    def get(url, params, headers, timeout):
        calls.append((params["keyword"], params["page"]))
        return R()
    ah.collect("hakone", ah.Credentials("a", "k"), get, sleep=lambda s: None)
    assert calls == [("箱根", 1)]


def test_annex_and_sister_hotels_are_known():
    known = {"ラビスタ函館ベイ", "志摩観光ホテル"}
    assert ah.is_known("ラビスタ函館ベイＡＮＮＥＸ（共立リゾート）", known)
    assert ah.is_known("志摩観光ホテル　ザ　ベイスイート", known)
    assert not ah.is_known("センチュリーマリーナ函館", known)


def test_address_with_two_prefectures_is_out_of_area():
    _, include, exclude = ah.AREA_QUERIES["aomori"]
    assert not ah.in_area("青森県秋田県鹿角郡小坂町十和田湖休平37", include, exclude)
    assert ah.in_area("青森県十和田市奥瀬蔦野湯1", include, exclude)
