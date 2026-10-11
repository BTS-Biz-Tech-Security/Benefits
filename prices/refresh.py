"""検索の実行時に、宿の市場価格を楽天トラベルから取り直し、DBの値と違えば上書きする。

- 市場価格は料金プランごとに持つ（人数・泊数・食事の条件をプランに合わせて取る）
- 楽天のアプリID・アクセスキーがなければ何もしない（DBに入っている値をそのまま使う）
- 取得してから REFRESH_AFTER 以上たったプランだけを取り直す（検索のたびに楽天を呼びすぎないため）
- 1回の検索で取り直すのは MAX_PER_SEARCH 件・MAX_SECONDS 秒まで。取れなかったプランはDBの値のまま
- 比べる日は、prices.update と同じく compare_dates の候補（4週間後以降の最初の土曜。空室や条件に合う料金がなければ、さらに4週間後を試す）
"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional

from models import Menu, Plan
from prices.rakuten import Credentials, Fetched, NotAvailable, fetch_price, is_rakuten_ref

REFRESH_AFTER = timedelta(hours=6)
MAX_PER_SEARCH = 5
MAX_SECONDS = 8.0
DEFAULT_ADULTS = 2
WEEKS_AHEAD = 4  # 比べる日は4週間後以降の最初の土曜（直前だと満室で取れない宿が多いため）
MAX_TRIES = 3  # 空室や条件に合う料金がなければ、さらに4週間後を試す。試す日の数
INTERVAL_SEC = 1.0  # 次の日を試すときの間隔（続けて呼ぶと一時的に止められるため）

TableFn = Callable[[str], Any]


def compare_dates(today: Optional[date] = None) -> list[date]:
    """比べる日の候補。4週間後以降で最初の土曜（休前日）から、4週間おきに MAX_TRIES 日。

    福利厚生価格は休前日の料金とみなすので、土曜で比べる。祝前日の判定はしない。
    """
    d = (today or date.today()) + timedelta(weeks=WEEKS_AHEAD)
    first = d + timedelta(days=(5 - d.weekday()) % 7)
    return [first + timedelta(weeks=WEEKS_AHEAD * i) for i in range(MAX_TRIES)]


def first_available(dates: list[date], call: Callable[[date], Fetched],
                    sleep: Callable[[float], None] = time.sleep) -> tuple[Fetched, date]:
    """候補の日を順に試し、価格が取れた最初の日の（価格, 日）を返す。

    空室なし・条件に合う料金なし（NotAvailable）なら次の日を試す。どの日もなければ最後の NotAvailable を投げる。
    通信の失敗は次の日を試してもよくならないので、そのまま投げる。
    """
    last: Optional[NotAvailable] = None
    for i, d in enumerate(dates):
        if i:
            sleep(INTERVAL_SEC)
        try:
            return call(d), d
        except NotAvailable as e:
            last = e
    raise last or NotAvailable("比べる日がありません")


def load_credentials() -> Credentials:
    """secrets.toml の [rakuten] から接続情報を読む。なければ空の接続情報を返す。"""
    try:
        import streamlit as st
        rak = st.secrets.get("rakuten", {})
    except Exception:  # secrets.toml がない環境（テストなど）でも検索は止めない
        return Credentials()
    return Credentials(rak.get("application_id", ""), rak.get("access_key", ""), rak.get("referer", ""))


def needs_refresh(row: Optional[dict[str, Any]], dates: list[date], now: datetime) -> bool:
    """DBの値を取り直すべきか。値がない・比べる日が候補にない・楽天以外の値・古い、のどれかなら取り直す。"""
    if row is None:
        return True
    if str(row.get("checkin")) not in {d.isoformat() for d in dates} or row.get("source") != "rakuten_api":
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
                          dates: Optional[list[date]] = None, now: Optional[datetime] = None,
                          fetch: Callable[..., Fetched] = fetch_price, sleep: Callable[[float], None] = time.sleep) -> int:
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
    dates = dates or compare_dates()
    now = now or datetime.now(timezone.utc)

    # ① いまDBに入っている比べる日の値を読み、取り直すプランを決める
    rows = (table("market_prices").select("plan_id,checkin,price,source,fetched_at")
            .in_("plan_id", [p.id for _, p in targets]).eq("is_representative", True).execute().data)
    current = {r["plan_id"]: r for r in rows}
    stale = [(m, p) for m, p in targets if needs_refresh(current.get(p.id), dates, now)][:MAX_PER_SEARCH]

    # ② 1件ずつ取り直す。時間がかかりすぎたら残りはDBの値のまま使う
    started = time.monotonic()
    updated = 0
    for m, p in stale:
        if time.monotonic() - started > MAX_SECONDS:
            break
        nights, adults, _ = plan_conditions(p)
        try:
            fetched, checkin = first_available(
                dates, lambda d: fetch(m.hotel_ref, d, nights, adults, creds, meal=p.meal), sleep)
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
