"""宿の市場価格（楽天トラベルの価格）を料金プランごとにまとめて取得し、market_prices と fetch_logs に保存する。

使い方: python -m prices.update [--checkin 2026-11-21] [--dry-run]
- 比べる日は、4週間後以降の最初の土曜。空室や条件に合う料金がなければ、さらに4週間後を試す（refresh.compare_dates）。--checkin を付けるとその日だけで取る
- 宿（category=stay）で hotel_ref のある施設の料金プランが対象。人数・泊数・食事の条件はプランに合わせる
- 楽天のアプリID・アクセスキーがなければ、全件を仮の価格（source='dummy'）で入れる
- 取得した価格は、そのプランの「比べる日」の価格として保存する（is_representative=true。前の値はフラグを外して残す）
- 通信の失敗が連続 STOP_AFTER 回続いたら止め、fetch_logs に stopped=true を残す（空室なし・条件に合う料金なしは楽天が応答しているので数えない）
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
from typing import Any, Callable, Optional

from models import Plan
from prices.rakuten import Credentials, Fetched, NotAvailable, fetch_price
from prices.refresh import compare_dates, plan_conditions, save_price

ROOT = Path(__file__).resolve().parent.parent
STOP_AFTER = 5
RETRY = 2
DB_RETRY = 2  # データベースへの書き込みを取り直す回数
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
    """1プラン分を取得する。通信の失敗は RETRY 回まで間をあけて取り直す。仮の価格の元にはプランの定価を使う。

    空室なし・条件に合う料金なし（NotAvailable）は、取り直しても変わらないので1回で失敗にする。
    """
    nights, adults, _ = plan_conditions(plan)
    last: Optional[Exception] = None
    for _ in range(RETRY + 1):
        try:
            return fetch_price(hotel_ref, checkin, nights, adults, creds, plan.list_price, meal=plan.meal), None
        except NotAvailable as e:
            return None, e
        except Exception as e:  # 通信の失敗は、取り直してだめなら失敗として数える
            last = e
            time.sleep(INTERVAL_SEC)
    return None, last


def with_db_retry(write: Callable[[], Any], tries: int = DB_RETRY + 1) -> Any:
    """データベースへの書き込みを、接続が切れたときは間をあけて取り直す。

    Supabase との接続は、長く動かしていると相手から切られることがある（Server disconnected）。
    書き込みは同じ値の上書きなので、繰り返しても結果は変わらない。
    """
    for i in range(tries):
        try:
            return write()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(INTERVAL_SEC * (i + 1))


def fetch_first_date(hotel_ref: str, plan: Plan, dates: list[date], creds: Credentials) -> tuple[Optional[Fetched], Optional[Exception], Optional[date]]:
    """比べる日の候補を順に試し、価格が取れた最初の日の（価格, None, 日）を返す。取れなければ（None, 失敗の理由, None）。

    空室なし・条件に合う料金なしなら次の日を試す。通信の失敗は次の日を試さない。
    """
    error: Optional[Exception] = None
    for i, d in enumerate(dates):
        if i:
            time.sleep(INTERVAL_SEC)
        fetched, error = fetch_with_retry(hotel_ref, plan, d, creds)
        if fetched is not None:
            return fetched, None, d
        if not isinstance(error, NotAvailable):
            break
    return None, error, None


def main() -> None:
    """宿の料金プランごとの市場価格を取得し、market_prices と fetch_logs に保存する。"""
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkin", type=date.fromisoformat, help="この日だけで取る（付けなければ compare_dates の候補を順に試す）")
    ap.add_argument("--dry-run", action="store_true", help="表示するだけで、データベースには書かない")
    args = ap.parse_args()

    # ① 接続情報を読む（secrets.toml か環境変数）
    from supabase import create_client  # テストで main を使わないときに supabase を読み込まないよう、ここで読む
    cfg = load_config()
    c = create_client(cfg["url"], cfg["key"]).schema("bts_app")
    creds: Credentials = cfg["creds"]
    print("楽天APIで取得します" if creds.ready() else "楽天のアプリID・アクセスキーがないため、仮の価格を入れます")
    dates = [args.checkin] if args.checkin else compare_dates()
    print("比べる日: " + " → ".join(f"{d:%m/%d}" for d in dates))

    # ② 対象（宿で hotel_ref のある施設の料金プラン）を読む
    menus = (c.table("menus").select("id,tenant_id,hotel_ref,name").eq("category", "stay")
             .not_.is_("hotel_ref", "null").is_("deleted_at", "null").execute().data)
    if not menus:
        print("対象の宿がありません")
        return
    by_menu = {m["id"]: m for m in menus}
    plans = [Plan.from_row(r) for r in c.table("plans").select("*").in_("menu_id", list(by_menu))
             .is_("deleted_at", "null").execute().data]
    plans.sort(key=lambda p: (by_menu[p.menu_id]["name"], p.name))  # 結果を読みやすいよう、宿名・プラン名の順に並べる
    log = None
    if not args.dry_run:
        log = c.table("fetch_logs").insert({"tenant_id": menus[0]["tenant_id"], "started_at": datetime.now(timezone.utc).isoformat(),
                                            "target_count": len(plans)}).execute().data[0]

    # ③ 1プランずつ取得する。通信の失敗が続いたら止める（楽天側の障害や一時的な利用制限のとき、呼び続けないため）
    ok = ng = streak = 0
    stopped = False
    # 部屋のグレードは区別しないので、同じ宿・人数・泊数・食事の条件なら結果は同じ。楽天への問い合わせを1回にまとめる
    cache: dict[tuple, tuple[Optional[Fetched], Optional[Exception], Optional[date]]] = {}
    for p in plans:
        m = by_menu[p.menu_id]
        key = (m["hotel_ref"], *plan_conditions(p), p.meal)
        fresh = key not in cache
        if fresh:
            cache[key] = fetch_first_date(m["hotel_ref"], p, dates, creds)
        fetched, error, checkin = cache[key]
        if fetched is None:
            ng += 1
            if not isinstance(error, NotAvailable):
                streak += 1
            print(f"  失敗 {m['name']}／{p.name}: {error}")
            if streak >= STOP_AFTER:
                stopped = True
                print("続けて失敗したため止めます")
                break
            continue
        streak = 0
        ok += 1
        print(f"  {m['name']}／{p.name}: {fetched.price:,}円（{fetched.source}・{checkin:%m/%d}）")
        # ④ 比べる日の印を付け替えて保存する（前の値は残す）
        if not args.dry_run:
            with_db_retry(lambda: save_price(c.table, p, m["hotel_ref"], checkin, fetched, datetime.now(timezone.utc)))
        if fresh and fetched.source == "rakuten_api":
            time.sleep(INTERVAL_SEC)

    # ⑤ 取得の記録を締める
    if log:
        with_db_retry(lambda: c.table("fetch_logs").update({"finished_at": datetime.now(timezone.utc).isoformat(), "success_count": ok,
                                                            "fail_count": ng, "stopped": stopped}).eq("id", log["id"]).execute())
    print(f"完了: 成功 {ok} / 失敗 {ng} / 停止 {'あり' if stopped else 'なし'}" + ("（表示のみ）" if args.dry_run else ""))


if __name__ == "__main__":
    main()
