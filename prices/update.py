"""宿の市場価格（楽天トラベルの価格）を料金プランごとにまとめて取得し、market_prices と fetch_logs に保存する。

使い方: python -m prices.update [--checkin 2026-11-21] [--dry-run]
- 宿（category=stay）で hotel_ref のある施設の料金プランが対象。人数・泊数・食事の条件はプランに合わせる
- 楽天のアプリID・アクセスキーがなければ、全件を仮の価格（source='dummy'）で入れる
- 取得した価格は、そのプランの「比べる日」の価格として保存する（is_representative=true。前の値はフラグを外して残す）
- 連続 STOP_AFTER 回失敗したら止め、fetch_logs に stopped=true を残す
- --dry-run は取得した価格を表示するだけで、データベースには書かない
- 最初にまとめて入れるときや、仮の価格を入れ直すときに手で動かす。検索のたびの取り直しは prices/refresh.py が行う
- secrets.toml がない環境では、環境変数から接続情報を読む
"""
from __future__ import annotations

import argparse
import os
import time
import tomllib
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

from models import Plan
from prices.rakuten import Credentials, Fetched, fetch_price
from prices.refresh import next_saturday, plan_conditions, save_price

ROOT = Path(__file__).resolve().parent.parent
STOP_AFTER = 5
RETRY = 2
INTERVAL_SEC = 1.0  # 楽天への問い合わせの間隔（続けて呼ぶと一時的に止められるため）


def load_config() -> dict[str, Any]:
    """接続情報を読む。secrets.toml があればそれを、なければ環境変数を使う。"""
    # ① 手元で動かすときは secrets.toml
    path = ROOT / ".streamlit" / "secrets.toml"
    if path.exists():
        sec = tomllib.loads(path.read_text(encoding="utf-8"))
        rak = sec.get("rakuten", {})
        creds = Credentials(rak.get("application_id", ""), rak.get("access_key", ""), rak.get("referer", ""))
        return {"url": sec["supabase"]["url"], "key": sec["supabase"]["anon_key"], "creds": creds}
    # ② secrets.toml がなければ環境変数
    creds = Credentials(os.environ.get("RAKUTEN_APPLICATION_ID", ""), os.environ.get("RAKUTEN_ACCESS_KEY", ""),
                        os.environ.get("RAKUTEN_REFERER", ""))
    return {"url": os.environ["SUPABASE_URL"], "key": os.environ["SUPABASE_ANON_KEY"], "creds": creds}


def fetch_with_retry(hotel_ref: str, plan: Plan, checkin: date, creds: Credentials) -> tuple[Optional[Fetched], Optional[Exception]]:
    """1プラン分を取得する。失敗したら RETRY 回まで間をあけて取り直す。仮の価格の元にはプランの定価を使う。"""
    nights, adults, _ = plan_conditions(plan)
    last: Optional[Exception] = None
    for _ in range(RETRY + 1):
        try:
            return fetch_price(hotel_ref, checkin, nights, adults, creds, plan.list_price, meal=plan.meal), None
        except Exception as e:  # 通信の失敗も空室なしも、取り直してだめなら失敗として数える
            last = e
            time.sleep(INTERVAL_SEC)
    return None, last


def main() -> None:
    """宿の料金プランごとの市場価格を取得し、market_prices と fetch_logs に保存する。"""
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkin", type=date.fromisoformat, default=next_saturday())
    ap.add_argument("--dry-run", action="store_true", help="表示するだけで、データベースには書かない")
    args = ap.parse_args()

    # ① 接続情報を読む（secrets.toml か環境変数）
    from supabase import create_client  # テストで main を使わないときに supabase を読み込まないよう、ここで読む
    cfg = load_config()
    c = create_client(cfg["url"], cfg["key"]).schema("bts_app")
    creds: Credentials = cfg["creds"]
    print("楽天APIで取得します" if creds.ready() else "楽天のアプリID・アクセスキーがないため、仮の価格を入れます")

    # ② 対象（宿で hotel_ref のある施設の料金プラン）を読む
    menus = (c.table("menus").select("id,tenant_id,hotel_ref,name").eq("category", "stay")
             .not_.is_("hotel_ref", "null").is_("deleted_at", "null").execute().data)
    if not menus:
        print("対象の宿がありません")
        return
    by_menu = {m["id"]: m for m in menus}
    plans = [Plan.from_row(r) for r in c.table("plans").select("*").in_("menu_id", list(by_menu))
             .is_("deleted_at", "null").execute().data]
    log = None
    if not args.dry_run:
        log = c.table("fetch_logs").insert({"tenant_id": menus[0]["tenant_id"], "started_at": datetime.now(timezone.utc).isoformat(),
                                            "target_count": len(plans)}).execute().data[0]

    # ③ 1プランずつ取得する。連続で失敗したら止める
    ok = ng = streak = 0
    stopped = False
    for p in plans:
        m = by_menu[p.menu_id]
        fetched, error = fetch_with_retry(m["hotel_ref"], p, args.checkin, creds)
        if fetched is None:
            ng += 1
            streak += 1
            print(f"  失敗 {m['name']}／{p.name}: {error}")
            if streak >= STOP_AFTER:
                stopped = True
                print("続けて失敗したため止めます")
                break
            continue
        streak = 0
        ok += 1
        print(f"  {m['name']}／{p.name}: {fetched.price:,}円（{fetched.source}）")
        # ④ 比べる日の印を付け替えて保存する（前の値は残す）
        if not args.dry_run:
            save_price(c.table, p, m["hotel_ref"], args.checkin, fetched, datetime.now(timezone.utc))
        if fetched.source == "rakuten_api":
            time.sleep(INTERVAL_SEC)

    # ⑤ 取得の記録を締める
    if log:
        c.table("fetch_logs").update({"finished_at": datetime.now(timezone.utc).isoformat(), "success_count": ok,
                                      "fail_count": ng, "stopped": stopped}).eq("id", log["id"]).execute()
    print(f"完了: 成功 {ok} / 失敗 {ng} / 停止 {'あり' if stopped else 'なし'}" + ("（表示のみ）" if args.dry_run else ""))


if __name__ == "__main__":
    main()
