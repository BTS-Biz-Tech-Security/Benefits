"""楽天トラベルの施設検索で、エリアごとの宿を目標の件数まで増やす（テスト用のデータを作るため）。

使い方: python -m prices.add_hotels [--per-area 3] [--apply]
- エリアごとに、エリアの検索語で楽天のキーワード検索APIを呼び、住所がエリア内の宿を集める
- 口コミが MIN_REVIEWS 件以上・評価 MIN_RATING 以上・最安料金 MIN_CHARGE 円以上（素泊まり中心の安宿を外す）の宿を、
  評価の高い順・口コミの多い順に選ぶ。すでに登録してある宿（同じ楽天のホテル番号か同じ名前）は選ばない
- --apply を付けたときだけ、施設（menus）と料金プラン3件（スタンダード・デラックス・素泊まり）を追加する。付けなければ候補を表示するだけ
- 施設の住所・紹介文・楽天のホテル番号・評価・口コミ件数は楽天の値。料金プランの金額は楽天の最安料金から作る仮の値
- 追加したあとは python -m prices.update で市場価格を取り、sql/010 で福利厚生価格をそろえる
"""
from __future__ import annotations

import argparse
import re
import time
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Optional

import requests

from prices.match_hotels import SEARCH_URL, base_name, to_count, to_rating
from prices.rakuten import TIMEOUT, Credentials, hotel_parts, request_headers

INTERVAL_SEC = 1.0  # 楽天への問い合わせの間隔（続けて呼ぶと一時的に止められるため）
PAGES = 2  # 検索語ごとに見るページ数（1ページ30件）
MIN_REVIEWS = 100
MIN_RATING = 4.0
MIN_CHARGE = 8000  # 1人あたりの最安料金がこれより安い宿は、ビジネスホテルや素泊まりの宿が多いので外す
PREFECTURE = re.compile(r"東京都|北海道|京都府|大阪府|.{2,3}県")
EXCLUDE_NAME = re.compile(r"カプセル|ホステル|ゲストハウス|東横イン|アパホテル|ルートイン|スーパーホテル|ドーミーイン|コンフォートホテル|マンスリー|民泊")

# エリアのコード → （検索語, 住所に含まれるべき語, 住所に含まれてはいけない語）。sql/007_areas.sql のエリアと同じ
AREA_QUERIES: dict[str, tuple[list[str], list[str], list[str]]] = {
    "furano": (["富良野", "旭川"], ["富良野市", "旭川市", "上川郡", "空知郡"], []),
    "sapporo": (["札幌"], ["札幌市"], []),
    "noboribetsu": (["登別"], ["登別市"], []),
    "hakodate": (["函館"], ["函館市"], []),
    "aomori": (["奥入瀬", "青森"], ["青森県"], []),
    "sendai": (["仙台", "秋保", "作並"], ["仙台市"], []),
    "zao": (["蔵王"], ["蔵王"], []),
    "aizu": (["会津", "磐梯"], ["会津", "耶麻郡"], []),
    "nasu": (["那須"], ["那須"], []),
    "nikko": (["日光", "鬼怒川"], ["日光市"], []),
    "kusatsu": (["草津温泉"], ["草津町"], []),
    "tokyo": (["東京"], ["東京都"], ["八丈", "大島町", "小笠原", "三宅", "新島", "神津島"]),
    "yokohama": (["横浜"], ["横浜市"], []),
    "hakone": (["箱根"], ["箱根町"], []),
    "atami": (["熱海"], ["熱海市"], []),
    "izu": (["伊豆", "伊東", "修善寺"], ["伊豆市", "伊東市", "伊豆の国市", "賀茂郡", "下田市"], []),
    "karuizawa": (["軽井沢"], ["軽井沢町"], []),
    "fujigoko": (["河口湖", "山中湖", "富士五湖"], ["南都留郡", "富士吉田市"], []),
    "kanazawa": (["金沢"], ["金沢市"], []),
    "takayama": (["飛騨高山", "高山"], ["高山市"], []),
    "gero": (["下呂"], ["下呂市"], []),
    "nagoya": (["名古屋"], ["名古屋市"], []),
    "kinosaki": (["城崎"], ["城崎町"], []),
    "kyoto": (["京都"], ["京都市"], []),
    "kobe": (["神戸", "有馬温泉"], ["神戸市"], []),
    "osaka": (["大阪"], ["大阪市"], []),
    "nara": (["奈良"], ["奈良市"], []),
    "ise": (["伊勢", "志摩", "鳥羽"], ["伊勢市", "志摩市", "鳥羽市"], []),
    "shirahama": (["南紀白浜", "白浜"], ["白浜町"], []),
    "matsue": (["松江", "玉造", "出雲"], ["松江市", "出雲市"], []),
    "hiroshima": (["広島", "宮島"], ["広島市", "廿日市市"], []),
    "dogo": (["道後", "松山"], ["松山市"], []),
    "beppu": (["別府"], ["別府市"], []),
    "nagasaki": (["長崎", "佐世保", "ハウステンボス"], ["長崎市", "佐世保市"], []),
    "okinawa": (["沖縄", "恩納"], ["沖縄県"], ["石垣市", "八重山郡", "宮古島市", "宮古郡"]),
    "ishigaki": (["石垣島"], ["石垣市", "八重山郡"], []),
}

DEFAULTS = {"usage_limit": "年2回まで", "family_scope": "本人と2親等まで", "cancel_policy": "7日前まで無料"}

# 料金プラン（2名1泊）。金額は楽天の最安料金（1人あたり）× 倍率。福利厚生価格は定価の75%（sql/010 で市場価格に合わせて直す）
PLAN_TEMPLATES = [
    ("スタンダード（2食付）", "洋室", "2食付き", "standard", 2.0),
    ("デラックス（2食付）", "和洋室", "2食付き", "deluxe", 2.6),
    ("素泊まり", "洋室", "なし", "standard", 1.3),
]


@dataclass
class Hotel:
    """楽天の施設の候補。"""
    hotel_no: str
    name: str
    address: str
    description: str
    rating: Optional[float]
    review_count: Optional[int]
    min_charge: Optional[int]


def parse_hotels(data: dict[str, Any]) -> list[Hotel]:
    """キーワード検索の応答から、施設の候補を取り出す。"""
    out = []
    for part in hotel_parts(data):
        info = part.get("hotelBasicInfo")
        if not info or info.get("hotelNo") is None:
            continue
        out.append(Hotel(str(info["hotelNo"]), info.get("hotelName", ""),
                         f"{info.get('address1', '')}{info.get('address2', '')}", (info.get("hotelSpecial") or "").strip(),
                         to_rating(info.get("reviewAverage")), to_count(info.get("reviewCount")),
                         to_count(info.get("hotelMinCharge"))))
    return out


def in_area(address: str, include: list[str], exclude: list[str]) -> bool:
    """住所がエリア内か。含まれるべき語のどれかを含み、含まれてはいけない語をどれも含まない。

    県境の宿は「青森県秋田県…」のように都道府県が2つ書かれていることがあるので、そのような住所は外す。
    """
    if len(PREFECTURE.findall(address)) > 1:
        return False
    return any(w in address for w in include) and not any(w in address for w in exclude)


def is_known(name: str, known_names: set[str]) -> bool:
    """登録済みの宿と同じか、その別館・姉妹館か（括弧を除いた名前が、どちらかに含まれる）。

    「ラビスタ函館ベイ」に対する「ラビスタ函館ベイANNEX」のように、同じ名前の別館を並べないため。
    """
    key = base_name(name)
    return any(k and (k in key or key in k) for k in known_names)


def eligible(h: Hotel) -> bool:
    """テスト用のデータに入れてよい宿か（口コミ・評価・最安料金・名前で判断する）。"""
    return ((h.review_count or 0) >= MIN_REVIEWS and (h.rating or 0) >= MIN_RATING
            and (h.min_charge or 0) >= MIN_CHARGE and not EXCLUDE_NAME.search(h.name))


def pick(candidates: list[Hotel], include: list[str], exclude: list[str], known_refs: set[str],
         known_names: set[str], count: int) -> list[Hotel]:
    """候補から、エリア内で条件に合う未登録の宿を、評価の高い順・口コミの多い順に count 件選ぶ。

    known_names は登録済みの宿の名前（match_hotels.base_name で括弧と空白を除いたもの）。
    """
    seen: set[str] = set()
    ok = []
    for h in candidates:
        if h.hotel_no in seen or h.hotel_no in known_refs or is_known(h.name, known_names):
            continue
        seen.add(h.hotel_no)
        if in_area(h.address, include, exclude) and eligible(h):
            ok.append(h)
    ok.sort(key=lambda h: (-(h.rating or 0), -(h.review_count or 0)))
    return ok[:count]


def tags_of(h: Hotel) -> list[str]:
    """施設名と紹介文から、タグを選ぶ（語の決まりは prices/retag_hotels.py の TAG_RULES と同じ）。"""
    from prices.retag_hotels import tags_from
    return tags_from([{"hotelBasicInfo": {"hotelName": h.name, "hotelSpecial": h.description}}])


def short_description(text: str, limit: int = 80) -> str:
    """紹介文を一覧で読める長さにする。改行と記号の飾りを除き、limit 文字で切る。"""
    text = re.sub(r"[\r\n]+", " ", text)
    text = re.sub(r"[★☆◆◇■□●○◎※♪]+", "", text).strip()
    return text if len(text) <= limit else text[:limit - 1] + "…"


def menu_row(h: Hotel, tenant_id: str, area_id: str, today: date) -> dict[str, Any]:
    """追加する施設の行。"""
    row: dict[str, Any] = {
        "tenant_id": tenant_id, "area_id": area_id, "name": h.name, "category": "stay", "address": h.address,
        "description": short_description(h.description) or None, "hotel_ref": h.hotel_no, "matched": True,
        "content_updated_at": today.isoformat(), "tags": tags_of(h), **DEFAULTS,
    }
    if h.rating is not None:
        row.update({"external_rating": h.rating, "external_review_count": h.review_count or 0,
                    "external_rating_source": "rakuten_api"})
    return row


def plan_rows(h: Hotel, menu_id: str) -> list[dict[str, Any]]:
    """追加する料金プランの行（3件）。金額は楽天の最安料金から作る仮の値で、100円単位に丸める。"""
    base = h.min_charge or 10000
    rows = []
    for i, (name, room, meal, grade, rate) in enumerate(PLAN_TEMPLATES, start=1):
        list_price = int(round(base * 2 * rate / 100) * 100)
        rows.append({"menu_id": menu_id, "name": name, "room_type": room, "meal": meal, "grade": grade, "adults": 2,
                     "children": 0, "nights": 1, "list_price": list_price,
                     "benefit_price": int(round(list_price * 0.75 / 100) * 100),
                     "coupon_code": f"H-{h.hotel_no}-{i}", "member_url": f"https://example.com/member/h-{h.hotel_no}"})
    return rows


def search(keyword: str, page: int, creds: Credentials, get: Callable[..., Any] = requests.get) -> list[Hotel]:
    """キーワード検索（施設名・住所などすべての項目が対象）。見つからなければ空のリスト。"""
    params = {"applicationId": creds.application_id, "format": "json", "keyword": keyword, "searchField": 0,
              "hits": 30, "page": page, "responseType": "small"}
    r = get(SEARCH_URL, params=params, headers=request_headers(creds), timeout=TIMEOUT)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return parse_hotels(r.json())


def collect(code: str, creds: Credentials, get: Callable[..., Any] = requests.get,
            sleep: Callable[[float], None] = time.sleep) -> list[Hotel]:
    """エリアの検索語で候補を集める。"""
    keywords, _, _ = AREA_QUERIES[code]
    out: list[Hotel] = []
    for kw in keywords:
        for page in range(1, PAGES + 1):
            found = search(kw, page, creds, get)
            sleep(INTERVAL_SEC)
            out.extend(found)
            if len(found) < 30:
                break
    return out


def main() -> None:
    """エリアごとに宿を目標の件数まで増やす。--apply でなければ候補を表示するだけ。"""
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-area", type=int, default=3, help="エリアごとの宿の目標件数")
    ap.add_argument("--apply", action="store_true", help="施設と料金プランを追加する")
    args = ap.parse_args()

    # ① 接続情報を読む
    from supabase import create_client  # テストで main を使わないときに supabase を読み込まないよう、ここで読む
    from prices.update import load_config, with_db_retry
    cfg = load_config()
    creds: Credentials = cfg["creds"]
    if not creds.ready():
        print("楽天のアプリID・アクセスキーがないため、探せません（secrets.toml の [rakuten] に書く）")
        return
    c = create_client(cfg["url"], cfg["key"]).schema("bts_app")

    # ② テナント・エリア・登録済みの宿を読む
    tenant_id = c.table("tenants").select("id").eq("code", "sample").execute().data[0]["id"]
    areas = {a["code"]: a for a in c.table("areas").select("id,code,name").is_("tenant_id", "null").execute().data}
    stays = (c.table("menus").select("area_id,name,hotel_ref").eq("tenant_id", tenant_id).eq("category", "stay")
             .is_("deleted_at", "null").execute().data)
    known_refs = {s["hotel_ref"] for s in stays if s.get("hotel_ref")}
    known_names = {base_name(s["name"]) for s in stays}
    print(f"エリアごとに宿を{args.per_area}件にします" + ("" if args.apply else "（表示のみ。追加するときは --apply）"))

    # ③ エリアごとに、足りない数だけ選ぶ。--apply なら追加する
    added = 0
    for code, (_, include, exclude) in AREA_QUERIES.items():
        area = areas.get(code)
        if not area:
            print(f"  エリアがありません: {code}")
            continue
        need = args.per_area - sum(1 for s in stays if s["area_id"] == area["id"])
        if need <= 0:
            continue
        try:
            chosen = pick(collect(code, creds), include, exclude, known_refs, known_names, need)
        except Exception as e:  # 通信の失敗は、そのエリアだけ飛ばして続ける
            print(f"  失敗　{area['name']}: {e}")
            continue
        if len(chosen) < need:
            print(f"  {area['name']}: 条件に合う宿が{len(chosen)}件だけでした（あと{need}件ほしい）")
        for h in chosen:
            print(f"  {area['name']}　{h.name}（{h.hotel_no}）★{h.rating}（{h.review_count or 0:,}件）最安{h.min_charge or 0:,}円　{h.address}")
            known_refs.add(h.hotel_no)
            known_names.add(base_name(h.name))
            if args.apply:
                row = menu_row(h, tenant_id, area["id"], date.today())
                menu_id = with_db_retry(lambda: c.table("menus").insert(row).execute().data[0]["id"])
                with_db_retry(lambda: c.table("plans").insert(plan_rows(h, menu_id)).execute())
            added += 1
    print(f"完了: {added}件" + ("を追加しました" if args.apply else "の候補（表示のみ）"))


if __name__ == "__main__":
    main()
