"""宿（menus）を楽天トラベルの施設と照合し、hotel_ref に楽天のホテル番号を入れる。

使い方: python -m prices.match_hotels [--apply]
- 対象は、宿（category=stay）のうち hotel_ref が楽天のホテル番号（数字）でないもの
- 施設名で楽天のキーワード検索APIを呼び、住所（都道府県と市区町村）が同じで、名前に施設名の最後の語を含む候補を探す
- 条件に合う候補が1件だけなら「一致」、それ以外は「要確認」（候補を表示するだけで書き込まない）
- --apply を付けたときだけ、「一致」の宿の hotel_ref を書き換える。付けなければ結果を表示するだけ
- 楽天のアプリID・アクセスキーがなければ何もしない
- 照合したあとは python -m prices.update で、本物の市場価格を取り直す
"""
from __future__ import annotations

import argparse
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable, Optional

import requests

from prices.rakuten import TIMEOUT, Credentials, hotel_parts, is_rakuten_ref, request_headers

SEARCH_URL = "https://openapi.rakuten.co.jp/engine/api/Travel/KeywordHotelSearch/20260731"
INTERVAL_SEC = 1.0  # 楽天への問い合わせの間隔（続けて呼ぶと一時的に止められるため）
MATCHED = "一致"
UNSURE = "要確認"
NOT_FOUND = "見つからない"

# 住所の先頭の「都道府県」と「市区町村（郡は町村まで。政令市の区は見ない）」。番地の「〇〇地区」などを拾わないよう、いちばん短く取る
AREA_PATTERN = re.compile(r"^(東京都|北海道|京都府|大阪府|.{2,3}県)(.+?郡.+?[町村]|.+?[市区町村])")


@dataclass
class Candidate:
    """楽天の施設の候補。"""
    hotel_no: str
    name: str
    address: str


@dataclass
class MatchResult:
    """1つの宿の照合結果。"""
    menu_id: str
    menu_name: str
    status: str  # 一致 / 要確認 / 見つからない
    hotel_no: Optional[str]
    candidates: list[Candidate]


def area_key(address: Optional[str]) -> Optional[tuple[str, str]]:
    """住所から（都道府県, 市区町村）を取り出す。取り出せなければ None。"""
    m = AREA_PATTERN.match((address or "").replace(" ", "").replace("　", ""))
    return (m.group(1), m.group(2)) if m else None


def normalize(text: str) -> str:
    """全角・半角と空白の違いをなくす（「ＪＲ」と「JR」、「箱根 芦ノ湖」と「箱根芦ノ湖」を同じに扱う）。"""
    return re.sub(r"[\s・]", "", unicodedata.normalize("NFKC", text or ""))


def key_word(name: str) -> str:
    """施設名の最後の語。施設名は「地名 宿の名前」の順が多いので、宿を見分けるのに使う（「箱根 芦ノ湖 はなをり」なら「はなをり」）。"""
    words = [w for w in re.split(r"[ 　]+", name.strip()) if w]
    return words[-1] if words else name


def parse_candidates(data: dict[str, Any]) -> list[Candidate]:
    """キーワード検索の応答から、施設の候補（ホテル番号・名前・住所）を取り出す。"""
    out = []
    for part in hotel_parts(data):
        info = part.get("hotelBasicInfo")
        if not info or info.get("hotelNo") is None:
            continue
        out.append(Candidate(str(info["hotelNo"]), info.get("hotelName", ""),
                             f"{info.get('address1', '')}{info.get('address2', '')}"))
    return out


def search_keywords(name: str) -> list[str]:
    """検索に使う語の順番。まず施設名そのもの、見つからなければ最後の語（宿の名前）だけで探す（2文字以上）。"""
    tries = [name.strip()]
    last = key_word(name)
    if len(last) >= 2 and last not in tries:
        tries.append(last)
    return tries


def search_hotels(keyword: str, creds: Credentials, get: Callable[..., Any] = requests.get) -> list[Candidate]:
    """楽天のキーワード検索（施設名だけを対象）で、施設の候補を返す。見つからなければ空のリスト。"""
    params = {"applicationId": creds.application_id, "format": "json", "keyword": keyword,
              "searchField": 1, "hits": 10, "responseType": "small"}
    r = get(SEARCH_URL, params=params, headers=request_headers(creds), timeout=TIMEOUT)
    if r.status_code == 404:  # 該当なしは 404 が返る
        return []
    r.raise_for_status()
    return parse_candidates(r.json())


def choose(name: str, address: Optional[str], candidates: list[Candidate]) -> tuple[str, Optional[str]]:
    """候補から施設を決める。住所の（都道府県, 市区町村）が同じで、名前に施設名の最後の語を含む候補が1件だけなら一致。

    語を短くして探し直したときに、同じ町の別の宿を取り違えないよう、名前も確かめる。それ以外は要確認。
    """
    if not candidates:
        return NOT_FOUND, None
    key = area_key(address)
    word = normalize(key_word(name))
    same = [c for c in candidates if key is not None and area_key(c.address) == key and word in normalize(c.name)]
    if len(same) == 1:
        return MATCHED, same[0].hotel_no
    return UNSURE, None


def match_menu(menu: dict[str, Any], creds: Credentials, get: Callable[..., Any] = requests.get,
               sleep: Callable[[float], None] = time.sleep) -> MatchResult:
    """1つの宿を照合する。施設名で見つからなければ、語を短くして探し直す。"""
    # 探し直しで見つかった候補も足していく（要確認のとき、どの検索の候補もまとめて見せるため）
    candidates: list[Candidate] = []
    for keyword in search_keywords(menu["name"]):
        for c in search_hotels(keyword, creds, get):
            if all(c.hotel_no != x.hotel_no for x in candidates):
                candidates.append(c)
        sleep(INTERVAL_SEC)
        status, hotel_no = choose(menu["name"], menu.get("address"), candidates)
        if status == MATCHED:
            return MatchResult(menu["id"], menu["name"], status, hotel_no, candidates)
    status, hotel_no = choose(menu["name"], menu.get("address"), candidates)
    return MatchResult(menu["id"], menu["name"], status, hotel_no, candidates)


def targets(menus: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """照合の対象。宿で、hotel_ref が楽天のホテル番号でないもの。"""
    return [m for m in menus if m.get("category") == "stay" and not is_rakuten_ref(m.get("hotel_ref"))]


def main() -> None:
    """宿を楽天の施設と照合し、結果を表示する。--apply なら一致した宿の hotel_ref を書き換える。"""
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="一致した宿の hotel_ref を書き換える")
    args = ap.parse_args()

    # ① 接続情報を読む（secrets.toml か環境変数）
    from supabase import create_client  # テストで main を使わないときに supabase を読み込まないよう、ここで読む
    from prices.update import load_config
    cfg = load_config()
    creds: Credentials = cfg["creds"]
    if not creds.ready():
        print("楽天のアプリID・アクセスキーがないため、照合できません（secrets.toml の [rakuten] に書く）")
        return
    c = create_client(cfg["url"], cfg["key"]).schema("bts_app")

    # ② 対象の宿を読む
    menus = (c.table("menus").select("id,name,address,category,hotel_ref").eq("category", "stay")
             .is_("deleted_at", "null").execute().data)
    todo = targets(menus)
    print(f"照合する宿: {len(todo)}件" + ("" if args.apply else "（表示のみ。書き込むときは --apply）"))

    # ③ 1件ずつ照合し、結果を表示する。一致したものだけ書き換える
    counts = {MATCHED: 0, UNSURE: 0, NOT_FOUND: 0}
    for m in todo:
        try:
            res = match_menu(m, creds)
        except Exception as e:  # 通信の失敗は、その宿だけ飛ばして続ける
            print(f"  失敗　{m['name']}: {e}")
            continue
        counts[res.status] += 1
        if res.status == MATCHED:
            hit = next(x for x in res.candidates if x.hotel_no == res.hotel_no)
            print(f"  {res.status}　{res.menu_name} → {hit.name}（{res.hotel_no}・{hit.address}）")
            if args.apply:
                c.table("menus").update({"hotel_ref": res.hotel_no, "matched": True}).eq("id", res.menu_id).execute()
        else:
            print(f"  {res.status}　{res.menu_name}（{m.get('address') or '住所なし'}）")
            for x in res.candidates[:5]:
                print(f"      候補: {x.name}（{x.hotel_no}・{x.address}）")
    print(f"完了: 一致 {counts[MATCHED]} / 要確認 {counts[UNSURE]} / 見つからない {counts[NOT_FOUND]}"
          + ("（書き込み済み）" if args.apply else "（表示のみ）"))


if __name__ == "__main__":
    main()
