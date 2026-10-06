"""検索結果の施設と周辺スポットから、1日プラン（午前・昼・午後・夜）を組み立てる。

組み立て（build_day_plan）は DB も AI も使わない純粋な関数。説明文は AI のキーがあれば AI、なければ決まった文の型。
画面は持たない（画面は ui/day_plan.py）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from models import Menu
from search import min_benefit_price

# (枠, 入れるカテゴリ)。この順に並べる
SLOTS = [("午前", "leisure"), ("昼", "meal"), ("午後", "leisure"), ("夜", "stay")]
NIGHT = "夜"
FREE_TIME = "自由時間"


@dataclass
class Spot:
    """周辺スポット（spots テーブルの1行）。"""
    id: str
    kind: str
    name: str
    description: Optional[str] = None
    url: Optional[str] = None

    @classmethod
    def from_row(cls, r: dict[str, Any]) -> "Spot":
        return cls(id=r["id"], kind=r["kind"], name=r["name"], description=r.get("description"), url=r.get("url"))


@dataclass
class PlanItem:
    slot: str
    kind: str  # "benefit"（福利厚生） / "spot"（周辺スポット） / "free"（自由時間）
    name: str
    category: str
    description: Optional[str] = None
    price: Optional[int] = None  # 福利厚生の最安価格。周辺スポットと自由時間は None
    url: Optional[str] = None


@dataclass
class DayPlan:
    area_id: str
    area_name: str
    items: list[PlanItem]
    day_trip: bool  # 宿泊がなく日帰りのとき True
    total_price: Optional[int]
    explanation: str = ""


def plan_area_id(menus: list[Menu]) -> Optional[str]:
    """プランのエリア。area_id がある最上位の施設のエリア。なければ None。"""
    return next((m.area_id for m in menus if m.area_id), None)


def build_day_plan(menus: list[Menu], spots: list[Spot], area_name: str) -> Optional[DayPlan]:
    """検索結果の施設（順位順）と周辺スポットから、午前・昼・午後・夜のプランを組む。"""
    area_id = plan_area_id(menus)
    if area_id is None:
        return None
    candidates = [m for m in menus if m.area_id == area_id]
    used: set[str] = set()
    items: list[PlanItem] = []
    for slot, category in SLOTS:
        menu = next((m for m in candidates if m.category == category and m.id not in used), None)
        if menu is not None:
            used.add(menu.id)
            items.append(PlanItem(slot, "benefit", menu.name, category, menu.description, min_benefit_price(menu)))
            continue
        if category == "stay":
            # 周辺スポットには宿泊がないので、夜の枠は出さない（日帰り）
            continue
        spot = next((s for s in spots if s.kind == category and s.id not in used), None)
        if spot is not None:
            used.add(spot.id)
            items.append(PlanItem(slot, "spot", spot.name, category, spot.description, url=spot.url))
            continue
        items.append(PlanItem(slot, "free", FREE_TIME, category))

    prices = [i.price for i in items if i.price is not None]
    return DayPlan(
        area_id=area_id, area_name=area_name, items=items,
        day_trip=not any(i.slot == NIGHT for i in items),
        total_price=sum(prices) if prices else None,
    )
