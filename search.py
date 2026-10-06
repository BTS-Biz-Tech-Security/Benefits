"""施設（menus）の検索。エリア・カテゴリ・人数・予算・キーワードで絞り込む。

画面は持たない（画面は ui/search_page.py）。DBから読む部分と、読んだ施設を絞り込む純粋な関数に分けている。
"""
from __future__ import annotations

from typing import Any, Iterable, Optional, cast

from db import table
from models import MENU_COLUMNS, Area, Menu, Plan


def list_areas(tenant_id: Optional[str] = None) -> list[Area]:
    """選べるエリア（共通エリアと、そのテナントのエリア）を並び順で返す。"""
    query = table("areas").select("id,code,name,sort").order("sort")
    query = query.or_(f"tenant_id.is.null,tenant_id.eq.{tenant_id}") if tenant_id else query.is_("tenant_id", "null")
    return [Area.from_row(cast(dict[str, Any], r)) for r in query.execute().data]


def count_keyword_hits(menu: Menu, keywords: Iterable[str]) -> int:
    """施設名・所在地・紹介文・タグのどれかに含まれるキーワードの数。"""
    haystack = " ".join([menu.name, menu.address or "", menu.description or "", *menu.tags])
    return sum(1 for k in keywords if k and k in haystack)


def min_benefit_price(menu: Menu) -> Optional[int]:
    """福利厚生価格の最安値。プランがなければ None。"""
    return min((p.benefit_price for p in menu.plans), default=None)


def filter_menus(menus: list[Menu], *, people: Optional[int] = None, budget: Optional[int] = None,
                 keywords: Iterable[str] = ()) -> list[Menu]:
    """人数・予算・キーワードで絞り込み、並べ替えて返す。

    - 人数: 定員（max_people）が人数以上、または定員が未設定の施設
    - 予算: 福利厚生価格が予算以下のプランがある施設（予算を指定したときは、プランのない施設は外す）
    - キーワード: 1つ以上含む施設。含む数の多い順、同数なら安い順
    """
    keywords = [k for k in keywords if k]
    result = []
    for menu in menus:
        if people and menu.max_people is not None and menu.max_people < people:
            continue
        if budget and not any(p.benefit_price <= budget for p in menu.plans):
            continue
        if keywords:
            menu.keyword_hits = count_keyword_hits(menu, keywords)
            if menu.keyword_hits == 0:
                continue
        result.append(menu)

    def sort_key(m: Menu):
        price = min_benefit_price(m)
        return (-m.keyword_hits, price is None, price or 0, m.name)

    return sorted(result, key=sort_key)


def fetch_menus(tenant_id: str, *, area_code: Optional[str] = None, category: Optional[str] = None) -> list[Menu]:
    """テナントの施設を、エリアとカテゴリで絞ってDBから読み、プランを付けて返す。"""
    query = table("menus").select(MENU_COLUMNS).eq("tenant_id", tenant_id).is_("deleted_at", "null")
    if area_code:
        area_ids = [a.id for a in list_areas(tenant_id) if a.code == area_code]
        if not area_ids:
            return []
        query = query.in_("area_id", area_ids)
    if category:
        query = query.eq("category", category)
    menus = [Menu.from_row(cast(dict[str, Any], r)) for r in query.execute().data]
    if not menus:
        return []

    plans_by_menu: dict[str, list[Plan]] = {}
    rows = table("plans").select("*").in_("menu_id", [m.id for m in menus]).is_("deleted_at", "null").execute().data
    for row in rows:
        r = cast(dict[str, Any], row)
        plans_by_menu.setdefault(cast(str, r["menu_id"]), []).append(Plan.from_row(r))
    for m in menus:
        m.plans = plans_by_menu.get(m.id, [])
    return menus


def search_menus(tenant_id: str, *, area_code: Optional[str] = None, category: Optional[str] = None,
                 people: Optional[int] = None, budget: Optional[int] = None,
                 keywords: Iterable[str] = ()) -> list[Menu]:
    """条件に合う施設を、並べ替えて返す。指定しない条件（None・空）は絞り込みに使わない。

    area_code は areas.code（例: "hakone"）、category は models.CATEGORIES のキー（例: "stay"）。
    """
    menus = fetch_menus(tenant_id, area_code=area_code, category=category)
    return filter_menus(menus, people=people, budget=budget, keywords=keywords)
