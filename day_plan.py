"""検索結果の施設と周辺スポットから、1日プラン（午前・昼・午後・夜）を組み立てる。

プランはエリアごとに1つ。検索結果に出てくるエリアを上位から順に、最大 MAX_PLANS 個まで組む。

各枠には、同じエリア・同じカテゴリの施設のうち、お得額（定価 − 福利厚生価格）が最大のものを入れる。

組み立て（build_day_plan）は DB も AI も使わない純粋な関数。説明文は AI のキーがあれば AI、なければ決まった文の型。
画面は持たない（画面は ui/day_plan.py）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional, cast

from db import table
from models import Menu, Plan
from nl_search import MODEL, llm_api_key
from search import list_areas

# (枠, 入れるカテゴリ)。この順に並べる
SLOTS = [("午前", "leisure"), ("昼", "meal"), ("午後", "leisure"), ("夜", "stay")]
NIGHT = "夜"
FREE_TIME = "自由時間"
MAX_PLANS = 3
KIND_LABELS = {"benefit": "福利厚生", "spot": "周辺スポット", "free": "自由時間"}


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
    url: Optional[str] = None
    # 福利厚生の施設だけに入る値（お得額が最大の料金プランのもの）。周辺スポットと自由時間は None
    plan_name: Optional[str] = None
    list_price: Optional[int] = None
    price: Optional[int] = None  # 福利厚生価格
    saving: Optional[int] = None  # お得額（定価 − 福利厚生価格）
    over_budget: Optional[int] = None  # 予算（1つのプランあたり）を超える額。予算内か予算の指定がなければ None

    @property
    def saving_rate(self) -> Optional[int]:
        """お得額の割合（%、四捨五入）。"""
        if not self.saving or not self.list_price:
            return None
        return round(self.saving * 100 / self.list_price)


@dataclass
class DayPlan:
    area_id: str
    area_name: str
    items: list[PlanItem]
    day_trip: bool  # 宿泊がなく日帰りのとき True
    total_price: Optional[int]
    explanation: str = ""
    budget: Optional[int] = None  # 1つのプランあたりの予算
    alternative: bool = False  # 利用者が挙げたエリア以外の代替案のとき True

    @property
    def total_saving(self) -> int:
        """福利厚生の施設のお得額の合計。"""
        return sum(i.saving or 0 for i in self.items)


def best_saving_plan(menu: Menu) -> Optional[Plan]:
    """お得額が最大の料金プラン（同額なら福利厚生価格が安いほう）。プランがなければ None。"""
    return min(menu.plans, key=lambda p: (p.benefit_price - p.list_price, p.benefit_price), default=None)


def _saving(menu: Menu) -> int:
    plan = best_saving_plan(menu)
    return plan.list_price - plan.benefit_price if plan else -1


def plan_area_id(menus: list[Menu]) -> Optional[str]:
    """プランのエリア。area_id がある最上位の施設のエリア。なければ None。"""
    return next((m.area_id for m in menus if m.area_id), None)


def plan_area_ids(menus: list[Menu], limit: int = MAX_PLANS) -> list[str]:
    """プランを組むエリア。検索結果に出てくる順（重複なし）に、最大 limit 個。"""
    ids: list[str] = []
    for m in menus:
        if m.area_id and m.area_id not in ids:
            ids.append(m.area_id)
    return ids[:limit]


def build_day_plan(menus: list[Menu], spots: list[Spot], area_name: str,
                   area_id: Optional[str] = None, budget: Optional[int] = None) -> Optional[DayPlan]:
    """検索結果の施設（順位順）と周辺スポットから、午前・昼・午後・夜のプランを組む。

    area_id を省略すると、検索結果の最上位のエリアで組む。
    施設は、お得額が最大のもの（同額なら検索結果で上位のもの）を選ぶ。予算を超えても選び、超える額を記録する
    （超えてもお得額が大きいことを、表示と説明文で伝える）。
    """
    area_id = area_id or plan_area_id(menus)
    if area_id is None:
        return None
    candidates = [m for m in menus if m.area_id == area_id]
    used: set[str] = set()
    items: list[PlanItem] = []
    for slot, category in SLOTS:
        fits = [m for m in candidates if m.category == category and m.id not in used]
        if fits:
            # max は同じ値なら先に出たもの（検索結果で上位）を返す
            menu = max(fits, key=_saving)
            used.add(menu.id)
            plan = best_saving_plan(menu)
            items.append(PlanItem(
                slot, "benefit", menu.name, category, menu.description,
                plan_name=plan.name if plan else None,
                list_price=plan.list_price if plan else None,
                price=plan.benefit_price if plan else None,
                saving=plan.list_price - plan.benefit_price if plan else None,
                over_budget=plan.benefit_price - budget if plan and budget and plan.benefit_price > budget else None,
            ))
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
        budget=budget,
    )


def explain_by_rule(plan: DayPlan) -> str:
    """AI を使わない説明文。「箱根で、午前は…、昼は…、午後は…、夜は…に泊まるプランです。」

    代替案なら先頭に断り書きを、予算を超える施設があれば、超える額とお得額を最後に添える。
    """
    prefix = ("ご希望のエリア以外からの代替案です。" if plan.alternative else "") + (f"{plan.area_name}で、" if plan.area_name else "")
    head = prefix + "、".join(f"{i.slot}は{i.name}" for i in plan.items if i.slot != NIGHT)
    if plan.day_trip:
        text = f"{head}を楽しむ日帰りのプランです。"
    else:
        night = next(i for i in plan.items if i.slot == NIGHT)
        text = f"{head}、夜は{night.name}に泊まるプランです。"
    if plan.total_saving > 0:
        text += f"合計で{plan.total_saving:,}円お得です。"
    for i in plan.items:
        if i.over_budget:
            text += f"{i.slot}の{i.name}は予算を{i.over_budget:,}円超えますが、定価より{i.saving or 0:,}円お得です。"
    return text


def _explain_with_ai(plan: DayPlan, request_text: str, api_key: str) -> str:
    from openai import OpenAI

    lines = "\n".join(
        f"- {i.slot}：{i.name}（{KIND_LABELS[i.kind]}）{i.description or ''}"
        + (f" 定価{i.list_price:,}円→福利厚生{i.price:,}円（{i.saving:,}円お得）" if i.saving else "")
        + (f" ※予算を{i.over_budget:,}円超える" if i.over_budget else "")
        for i in plan.items
    )
    prompt = (
        "あなたは企業の福利厚生サービスに詳しい旅行アドバイザーです。"
        "次の1日プランについて、利用者の希望に照らして、なぜこの組み合わせがよいかを2〜3文で説明してください。\n"
        "- プランに含まれる場所以外の施設や店の名前を出さないこと\n"
        "- 「自由時間」の枠は、その時間の過ごし方に一般的な言葉で触れる程度にすること\n"
        "- お得額があれば、合計でいくらお得かに触れること\n"
        "- 予算を超える施設があれば、超える額とお得額の両方を示し、お得感の大きさを伝えること。お得額が超える額より小さいときは、そう正直に書くこと\n"
        + ("- このプランは利用者が挙げたエリア以外からの代替案なので、冒頭でそのことを断り、代わりに勧める理由を書くこと\n"
           if plan.alternative else "")
        + "- 説明文だけを出力すること\n\n"
        + f"エリア：{plan.area_name}\n"
        + (f"予算（1つのプランあたり）：{plan.budget:,}円\n" if plan.budget else "")
        + ("宿泊：なし（日帰り）\n" if plan.day_trip else "")
        + f"プラン：\n{lines}\n合計のお得額：{plan.total_saving:,}円\n\n利用者の希望：{request_text}"
    )
    response = OpenAI(api_key=api_key).chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=400,
    )
    return (response.choices[0].message.content or "").strip()


def explain(plan: DayPlan, request_text: str) -> str:
    """プランの説明文。AI のキーがあれば AI、なければ（または失敗したら）決まった文の型。"""
    api_key = llm_api_key()
    if api_key:
        try:
            text = _explain_with_ai(plan, request_text, api_key)
        except Exception:  # AI の失敗で画面を止めない（決まった文の型に切り替える）
            text = ""
        if text:
            return text
    return explain_by_rule(plan)


def _load_spots(tenant_id: str, area_id: str) -> list[Spot]:
    """エリアの周辺スポット（共通のものと、そのテナントのもの）を名前順で返す。

    仮の関数: spots の読み込みは spots.py（なかりんさん担当）の仕事。
    spots.py ができたら、この関数の中身だけをその呼び出しに差し替える。
    """
    rows = (table("spots").select("id,kind,name,description,url").eq("area_id", area_id)
            .or_(f"tenant_id.is.null,tenant_id.eq.{tenant_id}").order("name").execute().data)
    return [Spot.from_row(cast(dict[str, Any], r)) for r in rows]


def make_day_plans(tenant_id: str, menus: list[Menu], request_text: str, budget: Optional[int] = None,
                   requested_area_names: Iterable[str] = ()) -> list[DayPlan]:
    """画面から呼ぶ入口。エリアごとに周辺スポットを読み、組み立て、説明文を付ける。組めなければ空のリスト。

    requested_area_names（利用者が挙げたエリア名）があれば、そのエリアのプランを先に並べ、
    それ以外のエリアのプランは代替案（alternative）として後ろに並べる。合わせて最大 MAX_PLANS 個。
    """
    all_ids = plan_area_ids(menus, limit=len(menus))
    if not all_ids:
        return []
    area_names = {a.id: a.name for a in list_areas(tenant_id)}
    requested = {n for n in requested_area_names if n in area_names.values()}
    if requested:
        all_ids = ([i for i in all_ids if area_names.get(i) in requested]
                   + [i for i in all_ids if area_names.get(i) not in requested])
    plans: list[DayPlan] = []
    for area_id in all_ids[:MAX_PLANS]:
        try:
            spots = _load_spots(tenant_id, area_id)
        except Exception:  # 周辺スポットが読めなくても、福利厚生の施設だけで組む
            spots = []
        plan = build_day_plan(menus, spots, area_names.get(area_id, ""), area_id=area_id, budget=budget)
        if plan is not None:
            plan.alternative = bool(requested) and plan.area_name not in requested
            plan.explanation = explain(plan, request_text)
            plans.append(plan)
    return plans
