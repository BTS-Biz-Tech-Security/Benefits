"""施設（menus）の検索。エリア・カテゴリ・人数・予算・キーワードで絞り込む。

画面は持たない（画面は ui/search_page.py）。DBから読む部分（fetch_menus）と、読んだ施設を絞り込む部分（filter_menus）に分けている。
"""
from __future__ import annotations

from typing import Any, Iterable, Optional, cast

from db import table
from models import MENU_COLUMNS, Area, Menu, Plan
from prices.refresh import refresh_market_prices


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


def count_keyword_hits(menu: Menu, keywords: Iterable[str], area_names: Optional[dict[str, str]] = None) -> int:
    """施設名・所在地・紹介文・タグ・エリア名のどれかに含まれるキーワードの数。

    area_names（エリアの id → エリア名）を渡すと、施設のエリア名も照合に使う。
    「出雲」で、所在地に「出雲」と書かれていない松江・出雲の施設（例: 島根県安来市の足立美術館）にも当たるようにするため。
    """
    area_name = (area_names or {}).get(menu.area_id or "", "")
    text = " ".join([menu.name, menu.address or "", menu.description or "", area_name] + menu.tags)
    hits = 0
    for keyword in keywords:
        if keyword and keyword in text:
            hits += 1
    return hits


def per_person(amount: int, plan: Plan) -> int:
    """料金プランの金額を1人あたりにする。料金は plan.adults 人分（宿は2名1室など）なので、その人数で割る。

    人数が入っていない料金プランは、1人分とみなす。部屋数は考えない（1人あたりの金額で比べるだけ）。
    """
    people = plan.adults or 1
    return round(amount / people)


def min_benefit_price(menu: Menu) -> Optional[int]:
    """福利厚生価格の最安値。プランがなければ None。"""
    prices = [plan.benefit_price for plan in menu.plans]
    return min(prices) if prices else None


def filter_menus(menus: list[Menu], *, people: Optional[int] = None, budget: Optional[int] = None,
                 keywords: Iterable[str] = (), budget_categories: Iterable[str] = ("stay",),
                 area_names: Optional[dict[str, str]] = None, budget_allowance: float = 1.0) -> list[Menu]:
    """人数・予算・キーワードで絞り込み、並べ替えて返す。

    - 人数: 定員（max_people）が人数以上、または定員が未設定の施設
    - 予算: 1人あたりの上限。budget_categories のカテゴリの施設だけに当てはめ、1人あたりの金額が予算以下のプランがない施設は外す。
      既定は宿だけ（1日プラン提案の「宿代の予算」）。施設を検索タブでは、選んだカテゴリ（「すべて」なら全カテゴリ）を渡す。
      budget_allowance は、予算の何倍まで残すか。既定は1倍（予算ちょうどまで）。1日プラン提案では、予算を超えてもお得な宿を
      見せるために 1.5倍まで残す（超える額は「予算＋〇〇円」のバッジで示す）
    - キーワード: 1つ以上含む施設。含む数の多い順、同数なら安い順。area_names を渡すと、エリア名も照合に使う
    """
    keywords = [k for k in keywords if k]
    result: list[Menu] = []
    for menu in menus:
        # ① 人数: 定員が足りない施設を外す
        if people and menu.max_people is not None and menu.max_people < people:
            continue
        # ② 予算（1人あたり）: 予算を当てはめるカテゴリで、予算（の budget_allowance 倍）以内の料金プランが1つもない施設を外す
        if budget and menu.category in budget_categories:
            prices = [per_person(plan.benefit_price, plan) for plan in menu.plans]
            if not prices or min(prices) > budget * budget_allowance:
                continue
        # ③ キーワード: 1つも含まない施設を外す
        if keywords:
            menu.keyword_hits = count_keyword_hits(menu, keywords, area_names)
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
                 keywords: Iterable[str] = (), budget_categories: Iterable[str] = ("stay",),
                 budget_allowance: float = 1.0) -> list[Menu]:
    """条件に合う施設を返す。指定しない条件（None・空）は絞り込みに使わない。

    area_code は areas.code（例: "hakone"）、category は models.CATEGORIES のキー（例: "stay"）。
    budget_categories は予算を当てはめるカテゴリ（既定は宿だけ）。budget_allowance は予算の何倍まで残すか（既定は1倍）。
    キーワードがあるときは、エリア名も照合に使う（「出雲」で松江・出雲の施設に当たるように）。
    """
    menus = fetch_menus(tenant_id, area_code=area_code, category=category)
    keywords = [k for k in keywords if k]
    area_names = None
    if keywords:
        area_names = {area.id: area.name for area in list_areas(tenant_id)}
    found = filter_menus(menus, people=people, budget=budget, keywords=keywords,
                         budget_categories=list(budget_categories), area_names=area_names,
                         budget_allowance=budget_allowance)
    # 宿の市場価格を楽天から取り直し、DBの値と違えば上書きしてから後の計算に渡す
    refresh_market_prices(found)
    return found


def get_menu(menu_id: str, tenant_id: Optional[str] = None) -> Optional[Menu]:
    """施設1件と、その料金プラン（福利厚生価格の安い順）。詳細画面で使う。見つからなければ None。

    tenant_id を渡すと、そのテナントの施設だけを探す（他社の施設を開けないようにするため）。
    """
    # ① 施設を読む
    query = table("menus").select(MENU_COLUMNS).eq("id", menu_id).is_("deleted_at", "null")
    if tenant_id:
        query = query.eq("tenant_id", tenant_id)
    rows = rows_of(query.limit(1))
    if not rows:
        return None
    menu = Menu.from_row(rows[0])

    # ② 料金プランを、福利厚生価格の安い順に付ける
    plan_query = table("plans").select("*").eq("menu_id", menu_id).is_("deleted_at", "null").order("benefit_price")
    menu.plans = [Plan.from_row(r) for r in rows_of(plan_query)]
    return menu
