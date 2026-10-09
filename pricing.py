"""差額と判定の計算。DBから読むのは、一般サイトの価格を取る representative_prices だけ。

判定の意味:
  good      … 一般サイトの価格より福利厚生価格のほうが安い
  not_good  … 一般サイトの価格のほうが安いか同額（一般サイトの方が安い）
  no_data   … 一般サイトの価格が取れていない（調べられない）
条件（人数・泊数）が揃わない場合は reference=True（目安）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from db import table
from models import MarketPrice, Plan

GOOD, NOT_GOOD, NO_DATA = "good", "not_good", "no_data"
LABELS = {GOOD: "お得", NOT_GOOD: "一般サイトの方が安い", NO_DATA: "調べられない"}


@dataclass
class PriceResult:
    list_price: int
    benefit_price: int
    market_price: Optional[int]
    diff: Optional[int]
    judgement: str
    reference: bool = False
    source: Optional[str] = None
    fetched_at: Optional[str] = None
    formula: str = ""

    @property
    def label(self) -> str:
        return LABELS[self.judgement] + ("（目安）" if self.reference else "")


def normalize(market: MarketPrice, plan: Plan) -> tuple[int, bool]:
    """一般サイトの価格をプランの条件（人数・泊数）に揃える。揃えられれば (価格, False)、揃わなければ (価格, True)。

    人数が違う場合は1人あたり単価×プランの人数で換算し、目安扱いにする。泊数はプランに合わせて比例換算。
    """
    # ① 一般サイトの価格をそのまま起点にする
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
    """差額 = 一般サイトの価格 − 福利厚生価格。正ならお得。"""
    return market_price - benefit_price


def judge(benefit_price: int, market_price: Optional[int]) -> str:
    """判定。一般サイトの価格がなければ調べられない、一般サイトの価格＞福利厚生ならお得、それ以外は一般サイトの方が安い。"""
    # ① 一般サイトの価格がなければ調べられない
    if market_price is None:
        return NO_DATA
    # ② 一般サイトの価格が福利厚生価格より高ければお得、それ以外は一般サイトの方が安い
    return GOOD if market_price > benefit_price else NOT_GOOD


def evaluate(plan: Plan, market: Optional[MarketPrice]) -> PriceResult:
    """プランと一般サイトの価格から価格・差額・判定・根拠をまとめて返す。"""
    # ① 一般サイトの価格がなければ「調べられない」の結果を返す
    if market is None:
        return PriceResult(plan.list_price, plan.benefit_price, None, None, NO_DATA, formula="一般サイトの価格を調べられなかったため比べられません")
    # ② 一般サイトの価格をプランの条件（人数・泊数）に揃える
    market_price, reference = normalize(market, plan)
    # ③ 差額と判定
    d = diff(plan.benefit_price, market_price)
    j = judge(plan.benefit_price, market_price)
    # ④ 根拠の文を作る。目安なら注記を足す
    formula = f"差額 = 一般サイトの価格 {market_price:,}円 − 福利厚生価格 {plan.benefit_price:,}円 = {d:,}円"
    if reference:
        formula += "（人数・泊数をプランに合わせて換算した目安）"
    # ⑤ まとめて返す
    return PriceResult(plan.list_price, plan.benefit_price, market_price, d, j, reference, market.source, market.fetched_at.strftime("%Y-%m-%d %H:%M"), formula)


def best_result(menu_plans: list[Plan], market: Optional[MarketPrice]) -> Optional[PriceResult]:
    """施設の代表値: 差額が最大のプランの結果。調べられないなら最初のプラン。"""
    if not menu_plans:
        return None
    # ① 全プランを評価する
    results = [evaluate(p, market) for p in menu_plans]
    # ② 比較できたものがあれば差額最大、なければ最初のプラン
    comparable = [r for r in results if r.diff is not None]
    return max(comparable, key=lambda r: r.diff) if comparable else results[0]


def representative_prices(menu_ids: list[str]) -> dict[str, MarketPrice]:
    """施設ごとの、比べる日の一般サイトの価格 {施設ID: 価格}。取れていない施設は含まれない。"""
    if not menu_ids:
        return {}
    rows = table("market_prices").select("*").in_("menu_id", menu_ids).eq("is_representative", True).execute().data
    return {r["menu_id"]: MarketPrice.from_row(r) for r in rows}