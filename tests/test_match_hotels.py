from prices import match_hotels as mh
from prices.rakuten import Credentials

CREDS = Credentials("app", "key")


def response(*hotels):
    """キーワード検索の応答（formatVersion 1 の形）。hotels は (番号, 名前, 都道府県, 以降の住所)。"""
    return {"hotels": [{"hotel": [{"hotelBasicInfo": {"hotelNo": no, "hotelName": name, "address1": a1, "address2": a2}}]}
                       for no, name, a1, a2 in hotels]}


class FakeResponse:
    def __init__(self, status, data=None):
        self.status_code, self._data = status, data or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def json(self):
        return self._data


def fake_get(table):
    """キーワード → 応答 の表で、requests.get の代わりをする。表にない語は 404（該当なし）。"""
    calls = []

    def get(url, params, headers, timeout):
        calls.append(params["keyword"])
        data = table.get(params["keyword"])
        return FakeResponse(200, data) if data else FakeResponse(404)
    get.calls = calls
    return get


def test_area_key_handles_gun_city_and_ward():
    assert mh.area_key("神奈川県足柄下郡箱根町湯本682") == ("神奈川県", "足柄下郡箱根町")
    assert mh.area_key("北海道札幌市中央区北5条") == ("北海道", "札幌市")
    assert mh.area_key("新潟県南魚沼郡湯沢町湯沢地区") == ("新潟県", "南魚沼郡湯沢町")
    assert mh.area_key("静岡県熱海市") == ("静岡県", "熱海市")
    assert mh.area_key("東京都港区芝公園") == ("東京都", "港区")
    assert mh.area_key("") is None


def test_one_candidate_in_same_city_is_matched():
    get = fake_get({"箱根湯本温泉 天成園": response(("1234", "箱根湯本温泉 天成園", "神奈川県", "足柄下郡箱根町湯本682"),
                                                ("9999", "天成園 別館", "静岡県", "熱海市"))})
    res = mh.match_menu({"id": "m1", "name": "箱根湯本温泉 天成園", "address": "神奈川県足柄下郡箱根町湯本682"},
                        CREDS, get, sleep=lambda s: None)
    assert (res.status, res.hotel_no) == (mh.MATCHED, "1234")


def test_two_candidates_in_same_city_need_review():
    data = response(("1", "ホテルA", "静岡県", "熱海市東海岸町"), ("2", "ホテルA 別邸", "静岡県", "熱海市和田浜"))
    res = mh.match_menu({"id": "m1", "name": "ホテルA", "address": "静岡県熱海市"}, CREDS, fake_get({"ホテルA": data}),
                        sleep=lambda s: None)
    assert (res.status, res.hotel_no) == (mh.UNSURE, None)
    assert len(res.candidates) == 2


def test_falls_back_to_shorter_words():
    # 施設名そのものでは見つからず、語を短くすると見つかる
    get = fake_get({"天成園": response(("1234", "天成園", "神奈川県", "足柄下郡箱根町湯本"))})
    res = mh.match_menu({"id": "m1", "name": "箱根湯本温泉 天成園", "address": "神奈川県足柄下郡箱根町"}, CREDS, get,
                        sleep=lambda s: None)
    assert res.status == mh.MATCHED
    assert get.calls == ["箱根湯本温泉 天成園", "天成園"]


def test_not_found_when_no_candidates():
    res = mh.match_menu({"id": "m1", "name": "存在しない宿", "address": "静岡県熱海市"}, CREDS, fake_get({}),
                        sleep=lambda s: None)
    assert (res.status, res.hotel_no) == (mh.NOT_FOUND, None)


def test_targets_are_stays_without_rakuten_number():
    menus = [{"id": "1", "category": "stay", "hotel_ref": "H-TENSEI"}, {"id": "2", "category": "stay", "hotel_ref": "1234"},
             {"id": "3", "category": "leisure", "hotel_ref": None}, {"id": "4", "category": "stay", "hotel_ref": None}]
    assert [m["id"] for m in mh.targets(menus)] == ["1", "4"]


def test_search_sends_access_key_in_header():
    seen = {}

    def get(url, params, headers, timeout):
        seen.update(url=url, params=params, headers=headers)
        return FakeResponse(404)
    assert mh.search_hotels("天成園", CREDS, get) == []
    assert seen["url"].endswith("/Travel/KeywordHotelSearch/20260731")
    assert seen["headers"]["accessKey"] == "key" and "accessKey" not in seen["params"]
    assert seen["params"]["searchField"] == 1


def test_other_hotel_in_same_town_is_not_matched():
    # 同じ町の別の宿が1件だけ見つかっても、名前に「はなをり」がなければ一致にしない
    get = fake_get({"箱根 芦ノ湖 はなをり": response(("5", "芦ノ湖ホテル", "神奈川県", "足柄下郡箱根町元箱根"))})
    res = mh.match_menu({"id": "m1", "name": "箱根 芦ノ湖 はなをり", "address": "神奈川県足柄下郡箱根町元箱根桃源台160"},
                        CREDS, get, sleep=lambda s: None)
    assert res.status == mh.UNSURE


def test_name_check_ignores_width_and_spaces():
    data = response(("7", "ＪＲタワーホテル日航札幌", "北海道", "札幌市中央区北5条西2-5"))
    res = mh.match_menu({"id": "m1", "name": "JRタワーホテル日航札幌", "address": "北海道札幌市中央区"}, CREDS,
                        fake_get({"JRタワーホテル日航札幌": data}), sleep=lambda s: None)
    assert (res.status, res.hotel_no) == (mh.MATCHED, "7")
