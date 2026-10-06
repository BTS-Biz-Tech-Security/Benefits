"""施設（menus）の検索。エリア・カテゴリ・人数・予算・キーワードで絞り込む。

画面は持たない（画面は ui/search_page.py）。DBから読む部分（fetch_menus）と、読んだ施設を絞り込む部分（filter_menus）に分けている。
"""
from __future__ import annotations

from typing import Any, Iterable, Optional, cast

from db import table
from models import MENU_COLUMNS, Area, Menu, Plan


def rows_of(query: Any) -> list[dict[str, Any]]:
    """DBに問い合わせて、結果を「行（列名 → 値）の一覧」で返す。

    cast は「この結果は行の一覧です」と Pylance（型チェック）に伝えるためだけのもので、動作は変わらない。
    """
    return cast(list[dict[str, Any]], query.execute().data)


def list_areas(tenant_id: Optional[str] = None) -> list[Area]:
    """選べるエリア（共通エリアと、そのテナントのエリア）を並び順で返す。"""
    query = table("areas").select("id,code,name,sort").order("sort")
    if tenant_id:
        query = query.or_(f"tenant_id.is.null,tenant_id.eq.{tenant_id}")
    else:
        query = query.is_("tenant_id", "null")
    return [Area.from_row(r) for r in rows_of(query)]


def count_keyword_hits(menu: Menu, keywords: Iterable[str]) -> int:
    """施設名・所在地・紹介文・タグのどれかに含まれるキーワードの数。"""
    text = " ".join([menu.name, menu.address or "", menu.description or ""] + menu.tags)
    hits = 0
    for keyword in keywords:
        if keyword and keyword in text:
            hits += 1
    return hits


def min_benefit_price(menu: Menu) -> Optional[int]:
    """福利厚生価格の最安値。プランがなければ None。"""
    prices = [plan.benefit_price for plan in menu.plans]
    return min(prices) if prices else None


def filter_menus(menus: list[Menu], *, people: Optional[int] = None, budget: Optional[int] = None,
                 keywords: Iterable[str] = ()) -> list[Menu]:
    """人数・予算・キーワードで絞り込み、並べ替えて返す。

    - 人数: 定員（max_people）が人数以上、または定員が未設定の施設
    - 予算: 福利厚生価格が予算以下のプランがある施設（予算を指定したときは、プランのない施設は外す）
    - キーワード: 1つ以上含む施設。含む数の多い順、同数なら安い順
    """
    keywords = [k for k in keywords if k]
    result: list[Menu] = []
    for menu in menus:
        # ① 人数: 定員が足りない施設を外す
        if people and menu.max_people is not None and menu.max_people < people:
            continue
        # ② 予算: 予算内の料金プランが1つもない施設を外す
        if budget:
            prices = [plan.benefit_price for plan in menu.plans]
            if not prices or min(prices) > budget:
                continue
        # ③ キーワード: 1つも含まない施設を外す
        if keywords:
            menu.keyword_hits = count_keyword_hits(menu, keywords)
            if menu.keyword_hits == 0:
                continue
        result.append(menu)

    # TODO(ranking.py): ここから下の並べ替えは仮のもの。並び順は ranking.py（じゅんぺいさん担当）が決める役割なので、
    # ranking.py ができたら外し、絞り込んだ result をそのまま返す。
    # 並びが変わっても day_plan.py は受け取った順番に従うので、day_plan.py の変更は要らない。
    def sort_key(menu: Menu) -> tuple[int, bool, int, str]:
        # キーワードを多く含む順 → 価格のある施設が先 → 安い順 → 名前順
        price = min_benefit_price(menu)
        return (-menu.keyword_hits, price is None, price or 0, menu.name)

    return sorted(result, key=sort_key)


def fetch_menus(tenant_id: str, *, area_code: Optional[str] = None, category: Optional[str] = None) -> list[Menu]:
    """テナントの施設を、エリアとカテゴリで絞ってDBから読み、料金プランを付けて返す。"""
    # ① 施設を読む（エリアとカテゴリはDB側で絞る）
    query = table("menus").select(MENU_COLUMNS).eq("tenant_id", tenant_id).is_("deleted_at", "null")
    if area_code:
        area_ids = [area.id for area in list_areas(tenant_id) if area.code == area_code]
        if not area_ids:
            return []
        query = query.in_("area_id", area_ids)
    if category:
        query = query.eq("category", category)
    menus = [Menu.from_row(r) for r in rows_of(query)]
    if not menus:
        return []

    # ② その施設の料金プランをまとめて読み、施設ごとに分ける
    menu_ids = [menu.id for menu in menus]
    plans_by_menu: dict[str, list[Plan]] = {}
    for r in rows_of(table("plans").select("*").in_("menu_id", menu_ids).is_("deleted_at", "null")):
        plans_by_menu.setdefault(r["menu_id"], []).append(Plan.from_row(r))

    # ③ 施設に料金プランを付ける
    for menu in menus:
        menu.plans = plans_by_menu.get(menu.id, [])
    return menus


def search_menus(tenant_id: str, *, area_code: Optional[str] = None, category: Optional[str] = None,
                 people: Optional[int] = None, budget: Optional[int] = None,
                 keywords: Iterable[str] = ()) -> list[Menu]:
    """条件に合う施設を返す。指定しない条件（None・空）は絞り込みに使わない。

    area_code は areas.code（例: "hakone"）、category は models.CATEGORIES のキー（例: "stay"）。
    """
    menus = fetch_menus(tenant_id, area_code=area_code, category=category)
    return filter_menus(menus, people=people, budget=budget, keywords=keywords)
