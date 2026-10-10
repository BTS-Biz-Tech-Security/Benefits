"""検索の実行時に、宿の市場価格を楽天トラベルから取り直し、DBの値と違えば上書きする。

- 市場価格は料金プランごとに持つ（人数・泊数・食事の条件をプランに合わせて取る）
- 楽天のアプリID・アクセスキーがなければ何もしない（DBに入っている値をそのまま使う）
- 取得してから REFRESH_AFTER 以上たったプランだけを取り直す（検索のたびに楽天を呼びすぎないため）
- 1回の検索で取り直すのは MAX_PER_SEARCH 件・MAX_SECONDS 秒まで。取れなかったプランはDBの値のまま
- 比べる日は、prices.update と同じく次の土曜
"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional

from models import Menu, Plan
from prices.rakuten import Credentials, Fetched, fetch_price, is_rakuten_ref

REFRESH_AFTER = timedelta(hours=6)
MAX_PER_SEARCH = 5
MAX_SECONDS = 8.0
DEFAULT_ADULTS = 2

TableFn = Callable[[str], Any]


def next_saturday(today: Optional[date] = None) -> date:
    """次の土曜の日付（比べる日）。今日が土曜なら翌週の土曜。"""
    d = today or date.today()
    return d + timedelta(days=(5 - d.weekday()) % 7 or 7)


def load_credentials() -> Credentials:
    """secrets.toml の [rakuten] から接続情報を読む。なければ空の接続情報を返す。"""
    try:
        import streamlit as st
        rak = st.secrets.get("rakuten", {})
    except Exception:  # secrets.toml がない環境（テストなど）でも検索は止めない
        return Credentials()
    return Credentials(rak.get("application_id", ""), rak.get("access_key", ""), rak.get("referer", ""))


def needs_refresh(row: Optional[dict[str, Any]], checkin: date, now: datetime) -> bool:
    """DBの値を取り直すべきか。値がない・比べる日が違う・楽天以外の値・古い、のどれかなら取り直す。"""
    if row is None:
        return True
    if str(row.get("checkin")) != checkin.isoformat() or row.get("source") != "rakuten_api":
        return True
    fetched_at = datetime.fromisoformat(str(row["fetched_at"]).replace("Z", "+00:00"))
    return now - fetched_at >= REFRESH_AFTER


def plan_conditions(plan: Plan) -> tuple[int, int, int]:
    """料金プランの（泊数, 大人, 子ども）。人数がないプランは大人2名とする。"""
    return int(plan.nights or 1), int(plan.adults or DEFAULT_ADULTS), int(plan.children or 0)


def save_price(table: TableFn, plan: Plan, hotel_ref: str, checkin: date, fetched: Fetched, now: datetime) -> None:
    """取得した価格を、そのプランの比べる日の価格として保存する。前の値は印を外して残す。

    同じプラン・同じ条件・同じ取得元の行があれば上書きする（sql/009 の一意の索引）。
    """
    nights, adults, children = plan_conditions(plan)
    table("market_prices").update({"is_representative": False}).eq("plan_id", plan.id).execute()
    table("market_prices").upsert({
        "menu_id": plan.menu_id, "plan_id": plan.id, "hotel_ref": hotel_ref, "checkin": checkin.isoformat(),
        "nights": nights, "adults": adults, "children": children, "meal": plan.meal, "price": fetched.price,
        "source": fetched.source, "source_url": fetched.source_url, "fetched_at": now.isoformat(), "is_representative": True,
    }, on_conflict="plan_id,checkin,nights,adults,children,source").execute()


def stay_plans(menus: list[Menu]) -> list[tuple[Menu, Plan]]:
    """楽天のホテル番号がある宿の料金プラン。"""
    return [(m, p) for m in menus if m.category == "stay" and is_rakuten_ref(m.hotel_ref) for p in m.plans]


def refresh_market_prices(menus: list[Menu], *, table: Optional[TableFn] = None, creds: Optional[Credentials] = None,
                          checkin: Optional[date] = None, now: Optional[datetime] = None,
                          fetch: Callable[..., Fetched] = fetch_price) -> int:
    """検索結果の宿の料金プランの市場価格を取り直し、DBの値と違えば上書きする。上書きした件数を返す。

    同じ値だったときは取得した日時だけを更新する（次の検索で取り直さないため）。
    """
    creds = creds if creds is not None else load_credentials()
    if not creds.ready():
        return 0
    targets = stay_plans(menus)
    if not targets:
        return 0
    if table is None:
        from db import table as db_table  # テストで Supabase に接続しないよう、使うときに読む
        table = db_table
    checkin = checkin or next_saturday()
    now = now or datetime.now(timezone.utc)

    # ① いまDBに入っている比べる日の値を読み、取り直すプランを決める
    rows = (table("market_prices").select("plan_id,checkin,price,source,fetched_at")
            .in_("plan_id", [p.id for _, p in targets]).eq("is_representative", True).execute().data)
    current = {r["plan_id"]: r for r in rows}
    stale = [(m, p) for m, p in targets if needs_refresh(current.get(p.id), checkin, now)][:MAX_PER_SEARCH]

    # ② 1件ずつ取り直す。時間がかかりすぎたら残りはDBの値のまま使う
    started = time.monotonic()
    updated = 0
    for m, p in stale:
        if time.monotonic() - started > MAX_SECONDS:
            break
        nights, adults, _ = plan_conditions(p)
        try:
            fetched = fetch(m.hotel_ref, checkin, nights, adults, creds, meal=p.meal)
        except Exception:  # 空室なし・条件に合う部屋なし・通信の失敗は、DBの値で検索を続ける
            continue
        row = current.get(p.id)
        # ③ 値が違えば上書き、同じなら取得した日時だけ更新する
        if row is None or str(row.get("checkin")) != checkin.isoformat() or int(row["price"]) != fetched.price \
                or row.get("source") != fetched.source:
            save_price(table, p, m.hotel_ref, checkin, fetched, now)
            updated += 1
        else:
            (table("market_prices").update({"fetched_at": now.isoformat()})
             .eq("plan_id", p.id).eq("is_representative", True).execute())
    return updated
