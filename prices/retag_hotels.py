"""楽天トラベルの施設情報（紹介文・設備・お風呂など）から、宿のタグを付け直す。

使い方: python -m prices.retag_hotels [--since 2026-10-12] [--apply]
- 対象は、宿（category=stay）で hotel_ref が楽天のホテル番号のもののうち、内容の更新日（content_updated_at）が --since 以降のもの
  （既定は prices.add_hotels で追加した日。手で付けたタグのある元からの宿は対象にしない）
- 施設名で楽天のキーワード検索APIを呼び（responseType=large）、同じホテル番号の施設の文字をまとめて、TAG_RULES の語でタグを決める
- 住所・電話番号・URL は見ない（「北海道」の「海」などで誤ってタグが付かないようにするため）。アクセスは「駅近」の判定にだけ使う
- 今あるタグは残し、見つかったタグを足す。--apply を付けたときだけ書き込む。付けなければ結果を表示するだけ
"""
from __future__ import annotations

import argparse
import re
import time
from typing import Any, Callable, Iterable, Optional

import requests

from prices.match_hotels import SEARCH_URL, key_word
from prices.rakuten import TIMEOUT, Credentials, request_headers

INTERVAL_SEC = 1.0  # 楽天への問い合わせの間隔（続けて呼ぶと一時的に止められるため）
SKIP_KEYS = {"address1", "address2", "postalCode", "telephoneNo", "faxNo", "latitude", "longitude",
             "parkingInformation", "nearestStation", "access"}
ACCESS_KEYS = {"access", "nearestStation"}

# タグ → 当てはまる語（正規表現）。タグは見本データ（sql/003・007）と、検索の簡易な読み取り（nl_search.RULE_KEYWORDS）の語にそろえる
TAG_RULES: list[tuple[str, str]] = [
    ("温泉", r"温泉|源泉|かけ流し"),
    ("露天風呂", r"露天"),
    ("貸切風呂", r"貸切風呂|貸切露天|貸し切り風呂|家族風呂|プライベート風呂|客室露天"),
    ("大浴場", r"大浴場"),
    ("サウナ", r"サウナ"),
    ("旅館", r"旅館|和の宿|湯宿"),
    ("部屋食", r"部屋食|お部屋で(お)?食事|お部屋でのお食事"),
    ("個室", r"個室"),
    ("子ども", r"お子様|子供|子ども|キッズ|お子さま"),
    ("家族向け", r"ファミリー|家族|キッズ|お子様|三世代"),
    ("海", r"(?<![熱上北])海(が|を|の|辺|岸|沿い|一望|水浴)|オーシャン|ビーチ|太平洋|日本海|瀬戸内"),  # 熱海・上海・北海道の「海」は除く
    ("ビーチ", r"ビーチ|海水浴"),
    ("湖", r"湖"),
    ("絶景", r"絶景|一望|パノラマ"),
    ("夜景", r"夜景"),
    ("高原", r"高原"),
    ("自然", r"自然|森|渓谷|渓流|川のせせらぎ|山々|里山"),
    ("スキー", r"スキー|ゲレンデ"),
    ("プール", r"プール"),
    ("リゾート", r"リゾート"),
    ("庭園", r"庭園|日本庭園"),
    ("歴史", r"老舗|創業|歴史|文化財|明治|大正|昭和初期"),
    ("静か", r"隠れ家|静か|喧騒"),
    ("記念日", r"記念日|アニバーサリー|誕生日"),
    ("高級", r"スイート|ラグジュアリー|最高級|上質"),
    ("ペット", r"ペット|愛犬"),
]
STATION_RULE = r"駅前|駅直結|駅すぐ|駅から徒歩\s*[0-9０-９]分|駅より徒歩\s*[0-9０-９]分"


def strings_of(value: Any, skip: set[str], keep_only: Optional[set[str]] = None, key: str = "") -> list[str]:
    """応答の値から、文字の値をすべて集める。skip の項目は見ない。keep_only を渡すと、その項目だけを集める。"""
    if isinstance(value, dict):
        out: list[str] = []
        for k, v in value.items():
            if keep_only is None and k in skip:
                continue
            out.extend(strings_of(v, skip, keep_only, k))
        return out
    if isinstance(value, list):
        return [s for v in value for s in strings_of(v, skip, keep_only, key)]
    if isinstance(value, str) and (keep_only is None or key in keep_only):
        return [value]
    return []


def hotel_groups(data: dict[str, Any]) -> list[list[dict[str, Any]]]:
    """応答の hotels を、宿ごとの部品のまとまりにする（hotelBasicInfo・hotelFacilitiesInfo などが宿ごとに並ぶ）。"""
    groups = []
    for item in data.get("hotels", []):
        hotel = item.get("hotel", item) if isinstance(item, dict) else item
        parts = hotel if isinstance(hotel, list) else [hotel]
        groups.append([p for p in parts if isinstance(p, dict)])
    return groups


def find_hotel(data: dict[str, Any], hotel_no: str) -> Optional[list[dict[str, Any]]]:
    """応答から、ホテル番号が同じ宿の部品を返す。なければ None。"""
    for parts in hotel_groups(data):
        for p in parts:
            info = p.get("hotelBasicInfo")
            if isinstance(info, dict) and str(info.get("hotelNo")) == str(hotel_no):
                return parts
    return None


def tags_from(parts: list[dict[str, Any]]) -> list[str]:
    """宿の部品の文字から、タグを決める。"""
    text = " ".join(strings_of(parts, SKIP_KEYS))
    tags = [tag for tag, pattern in TAG_RULES if re.search(pattern, text)]
    access = " ".join(strings_of(parts, set(), ACCESS_KEYS))
    if re.search(STATION_RULE, text + " " + access):
        tags.append("駅近")
    return tags


def merge_tags(current: Iterable[str], found: Iterable[str]) -> list[str]:
    """今あるタグを残し、見つかったタグを後ろに足す（重複なし）。"""
    out = list(dict.fromkeys(current))
    out.extend(t for t in found if t not in out)
    return out


def fetch_hotel(name: str, hotel_no: str, creds: Credentials, get: Callable[..., Any] = requests.get,
                sleep: Callable[[float], None] = time.sleep) -> Optional[list[dict[str, Any]]]:
    """施設名（見つからなければ最後の語）で検索し、ホテル番号が同じ宿の部品を返す。"""
    for keyword in dict.fromkeys([name.strip(), key_word(name)]):
        if len(keyword) < 2:
            continue
        params = {"applicationId": creds.application_id, "format": "json", "keyword": keyword, "searchField": 1,
                  "hits": 30, "responseType": "large"}
        r = get(SEARCH_URL, params=params, headers=request_headers(creds), timeout=TIMEOUT)
        sleep(INTERVAL_SEC)
        if r.status_code == 404:
            continue
        r.raise_for_status()
        parts = find_hotel(r.json(), hotel_no)
        if parts:
            return parts
    return None


def main() -> None:
    """宿のタグを付け直す。--apply でなければ結果を表示するだけ。"""
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-10-12", help="内容の更新日がこの日以降の宿を対象にする（YYYY-MM-DD）")
    ap.add_argument("--apply", action="store_true", help="タグを書き込む")
    args = ap.parse_args()

    from supabase import create_client  # テストで main を使わないときに supabase を読み込まないよう、ここで読む
    from prices.rakuten import is_rakuten_ref
    from prices.update import load_config, with_db_retry
    cfg = load_config()
    creds: Credentials = cfg["creds"]
    if not creds.ready():
        print("楽天のアプリID・アクセスキーがないため、付け直せません（secrets.toml の [rakuten] に書く）")
        return
    c = create_client(cfg["url"], cfg["key"]).schema("bts_app")
    menus = (c.table("menus").select("id,name,hotel_ref,tags").eq("category", "stay").gte("content_updated_at", args.since)
             .is_("deleted_at", "null").order("name").execute().data)
    menus = [m for m in menus if is_rakuten_ref(m.get("hotel_ref"))]
    print(f"対象の宿: {len(menus)}件" + ("" if args.apply else "（表示のみ。書き込むときは --apply）"))

    changed = 0
    for m in menus:
        try:
            parts = fetch_hotel(m["name"], m["hotel_ref"], creds)
        except Exception as e:  # 通信の失敗は、その宿だけ飛ばして続ける
            print(f"  失敗　{m['name']}: {e}")
            continue
        if parts is None:
            print(f"  見つからない　{m['name']}（{m['hotel_ref']}）")
            continue
        before = list(m.get("tags") or [])
        after = merge_tags(before, tags_from(parts))
        added = [t for t in after if t not in before]
        print(f"  {m['name']}: {'、'.join(after) or 'なし'}" + (f"　（追加: {'、'.join(added)}）" if added else ""))
        if added:
            changed += 1
            if args.apply:
                with_db_retry(lambda: c.table("menus").update({"tags": after}).eq("id", m["id"]).execute())
    print(f"完了: {changed}件のタグを" + ("書き換えました" if args.apply else "書き換えます（表示のみ）"))


if __name__ == "__main__":
    main()
