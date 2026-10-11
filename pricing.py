"""価格の比較の計算。DBから読むのは、市場価格を取る representative_prices だけ。

比較価格は、市場価格（楽天トラベルの価格。料金プランごとに1件）があればそれ、なければ定価。金額はすべて1人あたり。
条件（人数・泊数）が揃わない場合は reference=True（目安）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from db import table
from models import MarketPrice, Plan
from search import per_person

COMPARED_TO_MARKET, COMPARED_TO_LIST = "市場価格", "定価"



@dataclass
class PlanSaving:
    """プランの価格の比較（1人あたり）。比較価格は、市場価格があればそれ、なければ定価。"""
    benefit_price: int  # 福利厚生価格
    compared_price: int  # 比較価格
    compared_to: str  # 比較対象の種別。"市場価格" か "定価"
    saving: int  # お得額（比較価格 − 福利厚生価格）。マイナスなら比較価格の方が安い
    saving_rate: int  # 割引率（お得額 ÷ 比較価格、%）


def normalize(market: MarketPrice, plan: Plan) -> tuple[int, bool]:
    """市場価格をプランの条件（人数・泊数）に揃える。揃えられれば (価格, False)、揃わなければ (価格, True)。

    人数が違う場合は1人あたり単価×プランの人数で換算し、目安扱いにする。泊数はプランに合わせて比例換算。
    """
    # ① 市場価格をそのまま起点にする
    price = market.price
    reference = False
    plan_adults = plan.adults or market.adults
    # ② 人数が違えば1人あたり単価×プランの人数に換算し、目安にする
    if market.adults and plan_adults and market.adults != plan_adults:
        price = round(price / market.adults * plan_adults)
        reference = True
    # ③ 泊数が違えば1泊あたりに換算し、目安にする
    if market.nights and plan.nights and market.nights != plan.nights:
        price = round(price / market.nights * plan.nights)
        reference = True
    return price, reference


def diff(benefit_price: int, market_price: int) -> int:
    """差額 = 比較価格 − 福利厚生価格。正ならお得。plan_saving の中で使う。"""
    return market_price - benefit_price



def plan_saving(plan: Plan, market: Optional[MarketPrice]) -> PlanSaving:
    """プランの福利厚生価格・比較価格・比較対象の種別・お得額・割引率を、1人あたりで返す。"""
    benefit_price = per_person(plan.benefit_price, plan)
    # ① 市場価格があれば、プランの人数・泊数にそろえてから比べる
    if market is not None:
        market_price, _ = normalize(market, plan)
        compared_price, compared_to = per_person(market_price, plan), COMPARED_TO_MARKET
    # ② なければ定価と比べる（レジャー・食事や、市場価格を取れていない宿）
    else:
        compared_price, compared_to = per_person(plan.list_price, plan), COMPARED_TO_LIST
    # ③ お得額と割引率
    saving = diff(benefit_price, compared_price)
    saving_rate = round(saving * 100 / compared_price) if compared_price else 0
    return PlanSaving(benefit_price, compared_price, compared_to, saving, saving_rate)


def best_plan_saving(menu_plans: list[Plan], markets: dict[str, MarketPrice]) -> Optional[PlanSaving]:
    """施設の料金プランのうち、お得額（1人あたり）が最大のものの結果。料金プランがなければ None。ランキングで使う。

    markets は {料金プランID: 市場価格}（representative_prices の結果）。市場価格のないプランは定価と比べる。
    """
    if not menu_plans:
        return None
    return max((plan_saving(p, markets.get(p.id)) for p in menu_plans), key=lambda s: s.saving)


def representative_prices(menu_ids: list[str]) -> dict[str, MarketPrice]:
    """施設の料金プランごとの、比べる日の市場価格 {料金プランID: 価格}。取れていないプランは含まれない。

    市場価格は料金プランごとに持つ（人数・泊数・食事の条件をプランに合わせて取ったもの。sql/009）。
    """
    if not menu_ids:
        return {}
    rows = (table("market_prices").select("*").in_("menu_id", menu_ids).eq("is_representative", True)
            .not_.is_("plan_id", "null").execute().data)
    return {r["plan_id"]: MarketPrice.from_row(r) for r in rows}