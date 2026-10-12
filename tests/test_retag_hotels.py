from prices import retag_hotels as rt
from prices.rakuten import Credentials


def response(*hotels):
    """キーワード検索（responseType=large）の応答の形。hotels は (番号, 名前, 紹介文, 住所, アクセス, お風呂の情報)。"""
    return {"hotels": [{"hotel": [
        {"hotelBasicInfo": {"hotelNo": no, "hotelName": name, "hotelSpecial": special, "address1": "北海道",
                            "address2": addr, "access": access}},
        {"hotelFacilitiesInfo": {"aboutBath": [{"bathType": bath}]}},
    ]} for no, name, special, addr, access, bath in hotels]}


def test_tags_from_text_and_facilities():
    data = response(("1", "海辺の宿", "全室から海を一望。お子様連れ歓迎", "函館市", "函館駅から徒歩5分", "露天風呂・貸切風呂"))
    tags = rt.tags_from(rt.find_hotel(data, "1"))
    for t in ["海", "絶景", "子ども", "家族向け", "露天風呂", "貸切風呂", "駅近"]:
        assert t in tags


def test_address_does_not_make_tags():
    # 住所の「北海道」の「海」や、熱海の「海」ではタグを付けない
    data = response(("2", "熱海の宿", "落ち着いた客室", "熱海市", "", ""))
    assert "海" not in rt.tags_from(rt.find_hotel(data, "2"))


def test_find_hotel_picks_same_number():
    data = response(("1", "A", "", "", "", ""), ("2", "B", "露天風呂", "", "", ""))
    assert rt.tags_from(rt.find_hotel(data, "2")) == ["露天風呂"]
    assert rt.find_hotel(data, "9") is None


def test_ignores_leisure_policy_and_misleading_words():
    parts = [
        {"hotelBasicInfo": {"hotelNo": "3", "hotelName": "山の宿", "hotelSpecial": "海の幸を使った料理とウイスキーのバー",
                            "userReview": "子供と行きました"}},
        {"hotelFacilitiesInfo": {"leisureFacilities": [{"item": "スキー場"}, {"item": "ビーチ"}]}},
        {"hotelPolicyInfo": {"note": "お子様の料金は大人の70%"}},
    ]
    assert rt.tags_from(parts) == []


def test_fetch_falls_back_to_last_word():
    calls = []

    class R:
        def __init__(self, status, data=None):
            self.status_code, self._data = status, data or {}

        def raise_for_status(self):
            pass

        def json(self):
            return self._data

    def get(url, params, headers, timeout):
        calls.append(params["keyword"])
        if params["keyword"] == "天成園":
            return R(200, response(("84721", "箱根湯本温泉 天成園", "庭園露天風呂", "", "", "")))
        return R(404)
    parts = rt.fetch_hotel("箱根湯本温泉 天成園", "84721", Credentials("a", "k"), get, sleep=lambda s: None)
    assert parts is not None and calls == ["箱根湯本温泉 天成園", "天成園"]
    assert calls  # 応答の responseType は large


def test_add_hotels_uses_same_rules():
    from prices import add_hotels as ah
    h = ah.Hotel("1", "森の宿", "", "源泉かけ流しの露天風呂。キッズスペースあり", 4.5, 300, 15000)
    tags = ah.tags_of(h)
    assert "温泉" in tags and "露天風呂" in tags and "子ども" in tags and "自然" in tags


def test_scenery_tags_come_only_from_name_and_description():
    parts = [
        {"hotelBasicInfo": {"hotelNo": "4", "hotelName": "道後の宿", "hotelSpecial": "露天風呂のある宿"}},
        {"hotelFacilitiesInfo": {"hotelFacilities": [{"item": "ビーチ"}, {"item": "スキー"}, {"item": "サウナ"}]}},
    ]
    assert rt.tags_from(parts) == ["露天風呂", "サウナ"]


def test_merge_keeps_hand_tags():
    assert rt.merge_tags(["温泉", "家族向け"], ["温泉", "露天風呂"]) == ["温泉", "家族向け", "露天風呂"]
