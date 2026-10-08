"""宿の一般サイトの価格をまとめて取得し、market_prices と fetch_logs に保存する。

使い方: python -m prices.update [--checkin 2026-11-21] [--nights 1] [--adults 2] [--dry-run]
- 宿（category=stay）で hotel_ref のある施設が対象
- 楽天のアプリID・アクセスキーがなければ、全件を仮の価格（source='dummy'）で入れる
- 取得した価格は「比べる日」の価格として保存する（is_representative=true。前の値はフラグを外して残す）
- 連続 STOP_AFTER 回失敗したら止め、fetch_logs に stopped=true を残す
- --dry-run は取得した価格を表示するだけで、データベースには書かない
- GitHub Actions（.github/workflows/update_prices.yml）で1日1回自動で動かす。そのときは secrets.toml がないので、環境変数から読む
"""
from __future__ import annotations

import argparse
import os
import time
import tomllib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from prices.rakuten import Credentials, Fetched, fetch_price

ROOT = Path(__file__).resolve().parent.parent
STOP_AFTER = 5
RETRY = 2
INTERVAL_SEC = 1.0  # 楽天への問い合わせの間隔（続けて呼ぶと一時的に止められるため）


def next_saturday(today: Optional[date] = None) -> date:
    """次の土曜の日付（比べる日の既定）。今日が土曜なら翌週の土曜。"""
    d = today or date.today()
    return d + timedelta(days=(5 - d.weekday()) % 7 or 7)


def load_config() -> dict[str, Any]:
    """接続情報を読む。secrets.toml があればそれを、なければ環境変数（GitHub Actions 用）を使う。"""
    # ① 手元で動かすときは secrets.toml
    path = ROOT / ".streamlit" / "secrets.toml"
    if path.exists():
        sec = tomllib.loads(path.read_text(encoding="utf-8"))
        rak = sec.get("rakuten", {})
        creds = Credentials(rak.get("application_id", ""), rak.get("access_key", ""), rak.get("referer", ""))
        return {"url": sec["supabase"]["url"], "key": sec["supabase"]["anon_key"], "creds": creds}
    # ② 自動で動かすときは環境変数
    creds = Credentials(os.environ.get("RAKUTEN_APPLICATION_ID", ""), os.environ.get("RAKUTEN_ACCESS_KEY", ""),
                        os.environ.get("RAKUTEN_REFERER", ""))
    return {"url": os.environ["SUPABASE_URL"], "key": os.environ["SUPABASE_ANON_KEY"], "creds": creds}


def reference_prices(plans: list[dict[str, Any]], adults: int) -> dict[str, int]:
    """施設ごとの、仮の価格の元にする定価 {施設ID: 1泊あたりの定価}。

    同じ人数の料金プランのうち一番安い定価を使う。同じ人数のプランがなければ、人数で割り戻した定価を使う。
    """
    same: dict[str, int] = {}
    other: dict[str, int] = {}
    for p in plans:
        nights = int(p.get("nights") or 1)
        price = int(p["list_price"]) // nights
        plan_adults = int(p.get("adults") or 0)
        if plan_adults == adults:
            same[p["menu_id"]] = min(price, same.get(p["menu_id"], price))
        elif plan_adults:
            scaled = round(price / plan_adults * adults)
            other[p["menu_id"]] = min(scaled, other.get(p["menu_id"], scaled))
    return {**other, **same}


def fetch_with_retry(menu: dict[str, Any], checkin: date, nights: int, adults: int, creds: Credentials,
                     reference: Optional[int]) -> tuple[Optional[Fetched], Optional[Exception]]:
    """1件取得する。失敗したら RETRY 回まで間をあけて取り直す。"""
    last: Optional[Exception] = None
    for _ in range(RETRY + 1):
        try:
            return fetch_price(menu["hotel_ref"], checkin, nights, adults, creds, reference), None
        except Exception as e:  # 通信の失敗も空室なしも、取り直してだめなら失敗として数える
            last = e
            time.sleep(INTERVAL_SEC)
    return None, last


def main() -> None:
    """宿の一般サイトの価格を取得し、market_prices と fetch_logs に保存する。"""
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkin", type=date.fromisoformat, default=next_saturday())
    ap.add_argument("--nights", type=int, default=1)
    ap.add_argument("--adults", type=int, default=2)
    ap.add_argument("--dry-run", action="store_true", help="表示するだけで、データベースには書かない")
    args = ap.parse_args()

    # ① 接続情報を読む（secrets.toml か環境変数）
    from supabase import create_client  # テストで main を使わないときに supabase を読み込まないよう、ここで読む
    cfg = load_config()
    c = create_client(cfg["url"], cfg["key"]).schema("bts_app")
    creds: Credentials = cfg["creds"]
    print("楽天APIで取得します" if creds.ready() else "楽天のアプリID・アクセスキーがないため、仮の価格を入れます")

    # ② 対象（宿で hotel_ref のある施設）と、仮の価格の元にする定価を読む
    menus = (c.table("menus").select("id,tenant_id,hotel_ref,name").eq("category", "stay")
             .not_.is_("hotel_ref", "null").is_("deleted_at", "null").execute().data)
    if not menus:
        print("対象の宿がありません")
        return
    plans = (c.table("plans").select("menu_id,list_price,adults,nights").in_("menu_id", [m["id"] for m in menus])
             .is_("deleted_at", "null").execute().data)
    refs = reference_prices(plans, args.adults)
    log = None
    if not args.dry_run:
        log = c.table("fetch_logs").insert({"tenant_id": menus[0]["tenant_id"], "started_at": datetime.now(timezone.utc).isoformat(),
                                            "target_count": len(menus)}).execute().data[0]

    # ③ 1件ずつ取得する。連続で失敗したら止める
    ok = ng = streak = 0
    stopped = False
    for m in menus:
        fetched, error = fetch_with_retry(m, args.checkin, args.nights, args.adults, creds, refs.get(m["id"]))
        if fetched is None:
            ng += 1
            streak += 1
            print(f"  失敗 {m['name']}: {error}")
            if streak >= STOP_AFTER:
                stopped = True
                print("続けて失敗したため止めます")
                break
            continue
        streak = 0
        ok += 1
        print(f"  {m['name']}: {fetched.price:,}円（{fetched.source}）")
        # ④ 比べる日の印を付け替えて保存する（前の値は残す）
        if not args.dry_run:
            c.table("market_prices").update({"is_representative": False}).eq("menu_id", m["id"]).execute()
            c.table("market_prices").insert({
                "menu_id": m["id"], "hotel_ref": m["hotel_ref"], "checkin": args.checkin.isoformat(), "nights": args.nights,
                "adults": args.adults, "children": 0, "price": fetched.price, "source": fetched.source,
                "source_url": fetched.source_url, "fetched_at": datetime.now(timezone.utc).isoformat(), "is_representative": True,
            }).execute()
        if fetched.source == "rakuten_api":
            time.sleep(INTERVAL_SEC)

    # ⑤ 取得の記録を締める
    if log:
        c.table("fetch_logs").update({"finished_at": datetime.now(timezone.utc).isoformat(), "success_count": ok,
                                      "fail_count": ng, "stopped": stopped}).eq("id", log["id"]).execute()
    print(f"完了: 成功 {ok} / 失敗 {ng} / 停止 {'あり' if stopped else 'なし'}" + ("（表示のみ）" if args.dry_run else ""))


if __name__ == "__main__":
    main()
