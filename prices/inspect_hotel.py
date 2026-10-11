"""楽天の空室検索APIが、1つの宿についてどんな部屋・料金を返しているかを表示する（確認用。データベースには書かない）。

使い方: python -m prices.inspect_hotel 84721 [--checkin 2026-11-14] [--adults 2] [--nights 1]
- prices.update で「条件に合う料金が見つかりません」「空室がありません」が出たときに、原因を確かめるために使う
- prices.update と同じ条件（宿泊プランごとの一覧・安い順の1ページ目）で呼ぶ
- 部屋ごとに、プラン名・夕食と朝食の有無・合計料金を表示する。応答の件数の情報（pagingInfo）も表示する
"""
from __future__ import annotations

import argparse
from datetime import date
from typing import Any

import requests

from prices.rakuten import API_URL, TIMEOUT, hotel_parts, request_headers, vacant_params
from prices.refresh import next_saturday


def rooms(data: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """応答から（roomBasicInfo, dailyCharge）の組を並べる。"""
    out = []
    for part in hotel_parts(data):
        items = part.get("roomInfo") or []
        basic: dict[str, Any] = {}
        for item in items if isinstance(items, list) else [items]:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("roomBasicInfo"), dict):
                basic = item["roomBasicInfo"]
            if isinstance(item.get("dailyCharge"), dict):
                out.append((basic, item["dailyCharge"]))
    return out


def meal_label(basic: dict[str, Any]) -> str:
    """夕食・朝食の有無を「夕○ 朝×」の形にする。選べるプランは「選」。"""
    def mark(flag: str, select: str) -> str:
        if str(basic.get(select) or "0") == "1":
            return "選"
        return "○" if str(basic.get(flag) or "0") == "1" else "×"
    return f"夕{mark('withDinnerFlag', 'dinnerSelectFlag')} 朝{mark('withBreakfastFlag', 'breakfastSelectFlag')}"


def main() -> None:
    """1つの宿の空室検索の結果を表示する。"""
    ap = argparse.ArgumentParser()
    ap.add_argument("hotel_no")
    ap.add_argument("--checkin", type=date.fromisoformat, default=next_saturday())
    ap.add_argument("--adults", type=int, default=2)
    ap.add_argument("--nights", type=int, default=1)
    args = ap.parse_args()

    from prices.update import load_config
    creds = load_config()["creds"]
    if not creds.ready():
        print("楽天のアプリID・アクセスキーがありません（secrets.toml の [rakuten] に書く）")
        return
    params = vacant_params(args.hotel_no, args.checkin, args.nights, args.adults, creds)  # prices.update と同じ条件（1ページ目）
    r = requests.get(API_URL, params=params, headers=request_headers(creds), timeout=TIMEOUT)
    print(f"HTTP {r.status_code}　{args.hotel_no}　{args.checkin}〜{args.nights}泊　大人{args.adults}名")
    if r.status_code != 200:
        print(r.text[:500])
        return
    data = r.json()
    print(f"応答の項目: {list(data)}")
    if "pagingInfo" in data:
        print(f"件数の情報: {data['pagingInfo']}")
    found = rooms(data)
    print(f"部屋・プランの数: {len(found)}")
    for basic, charge in sorted(found, key=lambda x: int(x[1].get("total") or 0)):
        print(f"  {int(charge.get('total') or 0):>8,}円　{meal_label(basic)}　{basic.get('planName', '')}／{basic.get('roomName', '')}")


if __name__ == "__main__":
    main()
