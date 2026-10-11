"""ランキング（第10回MTG）。共通のスコアの上に、タブごとの並べ方を載せる二階建て。

- 共通スコア（施設ごと、0〜100点）: お得度・品質と信頼・条件への適合度を重みで足し、満足度が低い施設を減点する
- 施設を検索タブ: 共通スコアの高い順（重みは固定）
- 1日プラン提案タブ: 入力の文章で重みを変えた共通スコアから、プランの点を出して高い順
- 検索前の画面: お得ランキング（市場価格とのお得額の大きい順）と新着

点数の計算（score_menus・plan_score など）はDBに触らない。DBから読むのは facility_scores だけ。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from day_plan import DayPlan
from models import MarketPrice, Menu
from posts import Summary, review_stats
from pricing import COMPARED_TO_MARKET, PlanSaving, best_plan_saving, representative_prices
from search import search_menus

NEW_DAYS = 14

# ① 共通スコアの重み（お得度・品質・条件適合）。施設を検索タブはこの値で固定
SEARCH_WEIGHTS = {"deal": 0.40, "quality": 0.35, "fit": 0.25}
# 1日プラン提案タブ: 文章にこの語があれば、その重みに替える（上から順に見て最初に当たったもの）
PLAN_WEIGHT_RULES = [
    (("安く", "安い", "お得", "節約", "格安", "予算"), {"deal": 0.60, "quality": 0.25, "fit": 0.15}),
    (("家族", "子ども", "子供", "評判", "口コミ", "高級", "記念日"), {"deal": 0.25, "quality": 0.50, "fit": 0.25}),
]

# ② 品質: 従業員の口コミの比重。件数が FULL_REVIEWS 件以上で EMPLOYEE_MAX_WEIGHT、0件で0（外部の評価が100%）
EMPLOYEE_MAX_WEIGHT = 0.8
FULL_REVIEWS = 10
NEUTRAL_RATING = 3.0  # 外部の評価も口コミもない施設の星

# ③ 減点: お得感の満足の割合がこれを下回る施設
LOW_DEAL_SATISFACTION = 0.5
LOW_DEAL_PENALTY = 30

# ④ 1日プランの加点・減点（実装しながら調整する値）
SAVING_BONUS_PER_YEN = 1 / 500  # お得額の合計 500円ごとに1点
SAVING_BONUS_MAX = 20
SPOT_COUNT_BONUS = {2: 5, 3: 10}  # 福利厚生の施設の数ごとの加点（3件以上は3の値）
PLAN_PENALTY = 15  # 減点のある施設を含むプラン


@dataclass
class FacilityScore:
    deal: float  # お得度（0〜100）
    quality: float  # 品質・信頼（0〜100）
    fit: float  # 条件への適合度（0〜100）
    penalty: float  # 減点
    total: float  # 重みを付けて足し、減点を引いたもの


def deal_parts(menu: Menu, markets: dict[str, MarketPrice]) -> tuple[int, float]:
    """お得額（1人あたり）と割引率（0〜1）。お得額が最大の料金プランの pricing.best_plan_saving の結果を使う
    （プランに市場価格があればそれと、なければ定価と比べる）。マイナスは0にする。プランがなければ (0, 0)。"""
    result = best_plan_saving(menu.plans, markets)
    if result is None:
        return 0, 0.0
    return max(result.saving, 0), max(result.saving_rate / 100, 0.0)


def quality_score(external_rating: Optional[float], employee: Optional[Summary]) -> float:
    """外部の評価と社員の星を、口コミの件数に応じた比重で混ぜて0〜100点にする。"""
    # ① 社員の比重: 件数 ÷ FULL_REVIEWS × EMPLOYEE_MAX_WEIGHT（上限あり）
    count = employee.count if employee else 0
    employee_avg = employee.average if employee and employee.average is not None else None
    # ② どちらかしかなければ、あるほうだけ。どちらもなければ中間の値
    if external_rating is None and employee_avg is None:
        rating = NEUTRAL_RATING
    elif external_rating is None:
        rating = employee_avg
    elif employee_avg is None:
        rating = external_rating
    else:
        weight = EMPLOYEE_MAX_WEIGHT * min(count, FULL_REVIEWS) / FULL_REVIEWS
        rating = weight * employee_avg + (1 - weight) * external_rating
    return round(rating / 5 * 100, 1)


def fit_score(menu: Menu, keyword_count: int) -> float:
    """検索ワードのうち、施設に含まれる割合（0〜100点）。検索ワードがなければ全施設100点（並びに影響しない）。"""
    if keyword_count <= 0:
        return 100.0
    return round(min(menu.keyword_hits, keyword_count) / keyword_count * 100, 1)


def penalty_of(employee: Optional[Summary]) -> float:
    """お得感の満足の割合が LOW_DEAL_SATISFACTION を下回れば LOW_DEAL_PENALTY。回答がなければ0。"""
    if employee and employee.deal_satisfaction is not None and employee.deal_satisfaction < LOW_DEAL_SATISFACTION:
        return LOW_DEAL_PENALTY
    return 0


def score_menus(menus: list[Menu], markets: dict[str, MarketPrice], stats: dict[str, Summary],
                keyword_count: int, weights: Optional[dict[str, float]] = None) -> dict[str, FacilityScore]:
    """施設ごとの共通スコア {施設ID: FacilityScore}。DBに触らない。"""
    w = weights or SEARCH_WEIGHTS
    # ① お得度は、検索結果の中で最大の額・率を100点として比べる（額だけだと高い施設が有利になるため率も使う）
    parts = {m.id: deal_parts(m, markets) for m in menus}
    max_saving = max((s for s, _ in parts.values()), default=0) or 1
    max_rate = max((r for _, r in parts.values()), default=0) or 1
    scores = {}
    for m in menus:
        saving, rate = parts[m.id]
        deal = round(50 * saving / max_saving + 50 * rate / max_rate, 1)
        # ② 品質・条件適合・減点
        quality = quality_score(m.external_rating, stats.get(m.id))
        fit = fit_score(m, keyword_count)
        penalty = penalty_of(stats.get(m.id))
        # ③ 重みを付けて足し、減点を引く
        total = round(w["deal"] * deal + w["quality"] * quality + w["fit"] * fit - penalty, 1)
        scores[m.id] = FacilityScore(deal, quality, fit, penalty, total)
    return scores


def rank_menus(menus: list[Menu], scores: dict[str, FacilityScore]) -> list[Menu]:
    """施設を共通スコアの高い順に並べる（施設を検索タブ）。同点は名前順。"""
    return sorted(menus, key=lambda m: (-scores[m.id].total if m.id in scores else 0, m.name))


def plan_weights(request_text: str) -> dict[str, float]:
    """1日プラン提案タブの重み。文章に PLAN_WEIGHT_RULES の語があればその重み、なければ施設を検索タブと同じ。"""
    for words, weights in PLAN_WEIGHT_RULES:
        if any(word in (request_text or "") for word in words):
            return weights
    return SEARCH_WEIGHTS


def plan_score(plan: DayPlan, scores: dict[str, FacilityScore]) -> float:
    """1日プランの点 = 施設の共通スコアの平均 + お得額の合計の加点 + 施設の数の加点 - 減点。"""
    # ① プランの中の福利厚生の施設（周辺スポット・自由時間は点数がないので数えない）
    items = [i for i in plan.items if i.kind == "benefit" and i.menu_id in scores]
    if not items:
        return 0.0
    # ② 品質のベース: 共通スコアの平均
    base = sum(scores[i.menu_id].total for i in items) / len(items)
    # ③ お得額の合計の加点と、施設の数（1日の充実度）の加点
    saving_bonus = min(plan.total_saving * SAVING_BONUS_PER_YEN, SAVING_BONUS_MAX)
    count_bonus = SPOT_COUNT_BONUS.get(min(len(items), 3), 0)
    # ④ 満足度が低い施設を含めば減点
    penalty = PLAN_PENALTY if any(scores[i.menu_id].penalty for i in items) else 0
    return round(base + saving_bonus + count_bonus - penalty, 1)


def rank_plans(plans: list[DayPlan], scores: dict[str, FacilityScore]) -> list[DayPlan]:
    """1日プランを点の高い順に並べる。利用者が挙げたエリアのプランを先に、代替案を後ろにする順は残す。"""
    return sorted(plans, key=lambda p: (p.alternative, -plan_score(p, scores)))


def facility_scores(menus: list[Menu], keywords: list[str], weights: Optional[dict[str, float]] = None) -> dict[str, FacilityScore]:
    """検索結果の施設の共通スコア。市場価格と口コミの集計をまとめてDBから読んで計算する。検索画面から呼ばれる。"""
    ids = [m.id for m in menus]
    return score_menus(menus, representative_prices(ids), review_stats(ids), len([k for k in keywords if k]), weights)


def is_new(content_updated_at: Optional[str]) -> bool:
    """内容の更新日が NEW_DAYS 日以内なら新着。"""
    if not content_updated_at:
        return False
    return date.fromisoformat(str(content_updated_at)[:10]) >= date.today() - timedelta(days=NEW_DAYS)


def all_stay_menus(tenant_id: str) -> list[Menu]:
    """ランキング用: 宿泊施設全件（プラン付き）。"""
    return search_menus(tenant_id, category="stay")


def top_deals(tenant_id: str, limit: int = 5) -> list[tuple[Menu, PlanSaving]]:
    """市場価格より安い宿を、お得額（1人あたり）の大きい順に上位まで返す。市場価格のない宿は入れない。検索前の画面で使う。"""
    # ① 宿泊施設と市場価格をまとめて取る
    menus = all_stay_menus(tenant_id)
    prices = representative_prices([m.id for m in menus])
    # ② 施設ごとに最も得なプランを選び、市場価格より安いものだけ残す
    ranked = [(m, best_plan_saving(m.plans, prices)) for m in menus]
    ranked = [(m, r) for m, r in ranked if r and r.compared_to == COMPARED_TO_MARKET and r.saving > 0]
    # ③ お得額の大きい順に並べて上位を返す
    ranked.sort(key=lambda x: -x[1].saving)
    return ranked[:limit]


def new_menus(tenant_id: str, limit: int = 5) -> list[Menu]:
    """新着の施設（宿泊）。料金プランのない施設は出さない。"""
    menus = [m for m in all_stay_menus(tenant_id) if m.plans and is_new(m.content_updated_at)]
    return sorted(menus, key=lambda m: m.name)[:limit]