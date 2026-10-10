"""1日プランの組み立て。検索結果の施設と周辺スポットから、午前・昼・午後・夜のプランを組む。

- プランはエリアごとに1つ。検索結果に出てくるエリアを上から順に、最大 MAX_PLANS 個まで組む
- 各枠には、同じエリア・同じカテゴリの施設のうち、お得額が最大のものを入れる。
  お得額は料金プランごとに、一般サイトの価格が取れたプランはそれ、取れなかったプランは定価と、福利厚生価格との差（plan_saving）
- 足りない枠は周辺スポットで補い、それもなければ「自由時間」にする
- 説明文は、AI のキーがあれば AI、なければ決まった文の型で作る

画面は持たない（画面は ui/day_plan.py）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

from db import table
from models import MarketPrice, Menu, Plan
from nl_search import MODEL, llm_api_key
from pricing import normalize
from search import list_areas, per_person
from spots import spots_by_area

# 枠と、その枠に入れるカテゴリ（この順に並べる）
SLOTS = [("午前", "leisure"), ("昼", "meal"), ("午後", "leisure"), ("夜", "stay")]
NIGHT = "夜"
FREE_TIME = "自由時間"
MAX_PLANS = 3
# 1日プラン提案で、宿代の予算の何倍までの宿を残すか。超えてもお得な宿を、超える額とあわせて見せるため
BUDGET_ALLOWANCE = 1.5
KIND_LABELS = {"benefit": "福利厚生", "spot": "周辺スポット", "free": "自由時間"}


@dataclass
class Spot:
    """周辺スポット（spots テーブルの1行）。"""
    id: str
    kind: str  # "meal"（食事） / "leisure"（レジャー）
    name: str
    description: Optional[str] = None
    url: Optional[str] = None


@dataclass
class PlanItem:
    """プランの1枠。"""
    slot: str  # "午前" / "昼" / "午後" / "夜"
    kind: str  # "benefit"（福利厚生） / "spot"（周辺スポット） / "free"（自由時間）
    name: str
    category: str  # "leisure" / "meal" / "stay"
    description: Optional[str] = None
    url: Optional[str] = None
    # ここから下は福利厚生の施設だけに入る（お得額が最大の料金プランの値）。周辺スポットと自由時間は None
    # 金額はすべて1人あたり（料金プランの金額を、その料金の人数で割ったもの）
    menu_id: Optional[str] = None  # 施設の id。施設名から詳細画面へ移るときに使う
    plan_name: Optional[str] = None
    plan_price: Optional[int] = None  # 料金プランに書かれている福利厚生価格そのもの（例: 2名1室の料金）
    plan_people: Optional[int] = None  # その料金が何人分か
    list_price: Optional[int] = None  # 定価（1人あたり）
    price: Optional[int] = None  # 福利厚生価格（1人あたり）
    compared_price: Optional[int] = None  # 比べる価格（1人あたり）。一般サイトの価格があればそれ、なければ定価
    compared_to: Optional[str] = None  # 比べる相手（"一般サイト" / "定価"）
    saving: Optional[int] = None  # お得額（比べる価格 − 福利厚生価格。1人あたり）。一般サイトの方が安ければマイナス
    saving_rate: Optional[int] = None  # お得額の割合（%、四捨五入）
    over_budget: Optional[int] = None  # 宿代の予算を超える額。宿泊施設だけ。予算内か、予算の指定がなければ None


@dataclass
class DayPlan:
    """1つのエリアの1日プラン。"""
    area_id: str
    area_name: str
    items: list[PlanItem]
    day_trip: bool  # 宿泊がなく日帰りのとき True
    total_price: Optional[int]  # 福利厚生価格の合計（料金はすべて1人あたりとして扱うので、1人あたりの合計）
    explanation: str = ""
    budget: Optional[int] = None  # 宿代の予算（1泊・1人あたり）。宿泊施設にだけ当てはめる
    alternative: bool = False  # 利用者が挙げたエリア以外の代替案のとき True

    @property
    def total_saving(self) -> int:
        """お得額の合計。plan.total_saving のように、値と同じ書き方で読める。
        一般サイトの方が安い施設（お得額がマイナス）は、合計に入れない。"""
        total = 0
        for item in self.items:
            if item.saving and item.saving > 0:
                total += item.saving
        return total


# 料金プランの id → そのプランの一般サイトの価格。取れなかったプランは入っていない
MarketsByPlan = dict[str, MarketPrice]

COMPARED_TO_MARKET = "一般サイト"
COMPARED_TO_LIST = "定価"


@dataclass
class PriceCompare:
    """福利厚生価格と、比べる価格（一般サイトの価格か定価）。金額はすべて1人あたり。"""
    benefit_price: int
    compared_price: int
    compared_to: str  # "一般サイト" / "定価"
    saving: int  # 比べる価格 − 福利厚生価格。一般サイトの方が安ければマイナス
    saving_rate: int  # お得額の割合（%、四捨五入）。比べる価格が0なら0


# TODO(pricing.py): pricing.plan_saving（じゅんぺいさん担当）ができたら、この関数と PriceCompare を消し、
# 「from pricing import plan_saving」に置き換える。引数と戻り値は plan_saving と同じにしてある
def plan_saving(plan: Plan, market: Optional[MarketPrice]) -> PriceCompare:
    """料金プランの福利厚生価格を、一般サイトの価格（なければ定価）と比べる。金額は1人あたり。

    一般サイトの価格は、プランの人数・泊数にそろえてから（pricing.normalize）1人あたりにする。
    """
    # ① 比べる価格を決める。一般サイトの価格があればそれ、なければ定価
    if market is not None:
        market_price, _ = normalize(market, plan)
        compared_price = per_person(market_price, plan)
        compared_to = COMPARED_TO_MARKET
    else:
        compared_price = per_person(plan.list_price, plan)
        compared_to = COMPARED_TO_LIST
    # ② 1人あたりの福利厚生価格と、お得額・割合
    benefit_price = per_person(plan.benefit_price, plan)
    saving = compared_price - benefit_price
    saving_rate = round(saving * 100 / compared_price) if compared_price else 0
    return PriceCompare(benefit_price, compared_price, compared_to, saving, saving_rate)


def best_saving_plan(menu: Menu, max_price: Optional[float] = None,
                     markets: Optional[MarketsByPlan] = None) -> Optional[Plan]:
    """施設の料金プランのうち、1人あたりのお得額が最大のもの。同額なら1人あたりの福利厚生価格が安いほう。
    プランがなければ None。

    max_price（1人あたりの上限）を渡すと、上限以内のプランの中から選ぶ。上限以内のプランがなければ、すべてのプランから選ぶ。
    markets（料金プランの id → 一般サイトの価格）を渡すと、一般サイトの価格が取れたプランはそれと、
    取れなかったプランは定価と比べたお得額で選ぶ。
    """
    markets = markets or {}
    plans = menu.plans
    if max_price is not None:
        within = [plan for plan in plans if per_person(plan.benefit_price, plan) <= max_price]
        if within:
            plans = within
    best = None
    for plan in plans:
        if best is None:
            best = plan
            continue
        saving = plan_saving(plan, markets.get(plan.id)).saving
        best_saving = plan_saving(best, markets.get(best.id)).saving
        cheaper = per_person(plan.benefit_price, plan) < per_person(best.benefit_price, best)
        if saving > best_saving or (saving == best_saving and cheaper):
            best = plan
    return best


def plan_area_ids(menus: list[Menu], limit: int = MAX_PLANS) -> list[str]:
    """プランを組むエリア。検索結果に出てくる順に、重複なしで最大 limit 個。"""
    area_ids: list[str] = []
    for menu in menus:
        if menu.area_id and menu.area_id not in area_ids:
            area_ids.append(menu.area_id)
    return area_ids[:limit]


def plan_area_id(menus: list[Menu]) -> Optional[str]:
    """検索結果のいちばん上のエリア。なければ None。"""
    area_ids = plan_area_ids(menus, limit=1)
    return area_ids[0] if area_ids else None


def price_limit(menu: Menu, budget: Optional[int], budget_categories: Iterable[str] = ("stay",),
                budget_allowance: Optional[float] = None) -> Optional[float]:
    """表示するプランの1人あたりの上限（予算 × budget_allowance）。予算か倍率がないとき、予算を当てはめないカテゴリのときは None。"""
    if not budget or budget_allowance is None or menu.category not in budget_categories:
        return None
    return budget * budget_allowance


def _pick_menu(menus: list[Menu], category: str, used: set[str], budget: Optional[int] = None,
               budget_allowance: Optional[float] = None,
               markets: Optional[MarketsByPlan] = None) -> Optional[Menu]:
    """カテゴリが合う、まだ使っていない施設のうち、1人あたりのお得額が最大のもの。同額なら検索結果で上のもの。
    お得額は、表示するプラン（予算 × budget_allowance 以内のもの）で比べる。
    markets（料金プランの id → 一般サイトの価格）にあるプランは一般サイトの価格と、ないプランは定価と比べる。"""
    best = None
    best_saving: Optional[int] = None
    for menu in menus:
        if menu.category != category or menu.id in used:
            continue
        plan = best_saving_plan(menu, price_limit(menu, budget, budget_allowance=budget_allowance), markets)
        # 料金プランのない施設は最後に回す（一般サイトの方が安い施設のお得額はマイナスなので、それよりも後ろ）
        saving = plan_saving(plan, (markets or {}).get(plan.id)).saving if plan else None
        # 「より大きいとき」だけ入れ替えるので、同額なら先に見つかった（検索結果で上の）施設が残る
        if best is None or (saving is not None and (best_saving is None or saving > best_saving)):
            best = menu
            best_saving = saving
    return best


def _pick_spot(spots: list[Spot], kind: str, used: set[str]) -> Optional[Spot]:
    """種類が合う、まだ使っていない周辺スポットのうち、最初のもの。"""
    for spot in spots:
        if spot.kind == kind and spot.id not in used:
            return spot
    return None


def benefit_item(slot: str, menu: Menu, budget: Optional[int], budget_categories: Iterable[str] = ("stay",),
                 budget_allowance: Optional[float] = None, markets: Optional[MarketsByPlan] = None) -> PlanItem:
    """福利厚生の施設を、プランの1枠にする。金額はお得額が最大の料金プランのもので、1人あたりにする。

    お得額は plan_saving で計算する。markets（料金プランの id → 一般サイトの価格）に選んだプランの価格があればそれと、
    なければ定価と比べる。
    budget_allowance を渡すと、予算 × budget_allowance 以内のプランの中からお得額が最大のものを選ぶ
    （1日プラン提案で、予算を大きく超えるプランを出さないため）。渡さなければ、すべてのプランから選ぶ（施設を検索タブ）。
    検索画面の施設一覧でも、1日プランと同じ金額を出すために使う。
    """
    item = PlanItem(slot=slot, kind="benefit", name=menu.name, category=menu.category, description=menu.description,
                    menu_id=menu.id)
    plan = best_saving_plan(menu, price_limit(menu, budget, budget_categories, budget_allowance), markets)
    if plan is None:
        return item
    compare = plan_saving(plan, (markets or {}).get(plan.id))
    item.plan_name = plan.name
    item.plan_price = plan.benefit_price
    item.plan_people = plan.adults or 1
    item.list_price = per_person(plan.list_price, plan)
    item.price = compare.benefit_price
    item.compared_price = compare.compared_price
    item.compared_to = compare.compared_to
    item.saving = compare.saving
    item.saving_rate = compare.saving_rate
    # 予算（1人あたり）と、1人あたりの金額を比べる。既定は宿だけ（1日プランの「宿代の予算」）
    if budget and menu.category in budget_categories and item.price > budget:
        item.over_budget = item.price - budget
    return item


def build_day_plan(menus: list[Menu], spots: list[Spot], area_name: str,
                   area_id: Optional[str] = None, budget: Optional[int] = None,
                   budget_allowance: Optional[float] = None,
                   markets: Optional[MarketsByPlan] = None) -> Optional[DayPlan]:
    """1つのエリアのプランを組む。area_id を省略すると、検索結果のいちばん上のエリアで組む。

    宿代の予算を超える宿も選び、超える額を記録する（超えてもお得なことを、表示と説明文で伝えるため）。
    budget_allowance を渡すと、宿のプランは予算 × budget_allowance 以内のものから選ぶ。
    markets（料金プランの id → 一般サイトの価格）にあるプランは、お得額を一般サイトの価格と比べる。ないプランは定価と比べる。
    予算は宿代の上限なので、食事・レジャーには当てはめない。
    DB も AI も使わない。
    """
    # ① エリアを決め、そのエリアの施設だけにする
    if area_id is None:
        area_id = plan_area_id(menus)
    if area_id is None:
        return None
    area_menus = [m for m in menus if m.area_id == area_id]

    # ② 枠ごとに、福利厚生の施設 → 周辺スポット → 自由時間 の順で埋める。同じ場所は2回使わない
    used: set[str] = set()
    items: list[PlanItem] = []
    for slot, category in SLOTS:
        menu = _pick_menu(area_menus, category, used, budget, budget_allowance, markets)
        if menu is not None:
            used.add(menu.id)
            items.append(benefit_item(slot, menu, budget, budget_allowance=budget_allowance, markets=markets))
            continue
        if category == "stay":
            continue  # 周辺スポットには宿泊がないので、夜の枠は出さない（日帰り）
        spot = _pick_spot(spots, category, used)
        if spot is not None:
            used.add(spot.id)
            items.append(PlanItem(slot=slot, kind="spot", name=spot.name, category=category,
                                  description=spot.description, url=spot.url))
            continue
        items.append(PlanItem(slot=slot, kind="free", name=FREE_TIME, category=category))

    # ③ 福利厚生価格を合計する（周辺スポットは価格がないので入れない）
    prices = [item.price for item in items if item.price is not None]
    total_price = sum(prices) if prices else None
    day_trip = not any(item.slot == NIGHT for item in items)
    return DayPlan(area_id=area_id, area_name=area_name, items=items, day_trip=day_trip,
                   total_price=total_price, budget=budget)


def explain_by_rule(plan: DayPlan) -> str:
    """AI を使わない説明文。「箱根で、午前は…、昼は…、午後は…、夜は…に泊まるプランです。」の形。"""
    # ① 代替案なら断り書き、そのあとにエリア名
    text = ""
    if plan.alternative:
        text += "ご希望のエリア以外からの代替案です。"
    if plan.area_name:
        text += f"{plan.area_name}で、"

    # ② 夜以外の枠を「午前は…、昼は…」とつなぐ
    daytime = [f"{item.slot}は{item.name}" for item in plan.items if item.slot != NIGHT]
    text += "、".join(daytime)

    # ③ 夜の枠（なければ日帰り）
    if plan.day_trip:
        text += "を楽しむ日帰りのプランです。"
    else:
        night = [item for item in plan.items if item.slot == NIGHT][0]
        text += f"、夜は{night.name}に泊まるプランです。"

    # ④ お得額の合計と、予算を超える施設
    if plan.total_saving > 0:
        text += f"1人あたり合計で{plan.total_saving:,}円お得です。"
    for item in plan.items:
        if item.over_budget:
            text += f"{item.slot}の{item.name}は宿代の予算を{item.over_budget:,}円超えます"
            if item.saving and item.saving > 0:
                text += f"が、{item.compared_to}より{item.saving:,}円お得です。"
            else:
                text += "。"
    return text


def _explain_with_ai(plan: DayPlan, request_text: str, api_key: str) -> str:
    """AI に説明文を書かせる。失敗したときは例外がそのまま出る（呼び出し側で決まった文の型に切り替える）。"""
    from openai import OpenAI

    # ① プランの中身を箇条書きにする
    lines = []
    for item in plan.items:
        line = f"- {item.slot}：{item.name}（{KIND_LABELS[item.kind]}）{item.description or ''}"
        if item.saving and item.saving > 0:
            line += f" {item.compared_to}{item.compared_price:,}円→福利厚生{item.price:,}円（{item.saving:,}円お得）"
        elif item.saving and item.saving < 0:
            line += f" {item.compared_to}{item.compared_price:,}円・福利厚生{item.price:,}円（{item.compared_to}の方が{-item.saving:,}円安い）"
        if item.over_budget:
            line += f" ※宿代の予算を{item.over_budget:,}円超える"
        lines.append(line)

    # ② 指示文を組み立てる
    rules = [
        "プランに含まれる場所以外の施設や店の名前を出さないこと",
        "「自由時間」の枠は、その時間の過ごし方に一般的な言葉で触れる程度にすること",
        "金額はすべて1人あたり。お得額があれば、1人あたり合計でいくらお得かに触れること",
        "宿代の予算を超える宿があれば、超える額とお得額の両方を示し、お得感の大きさを伝えること。お得額が超える額より小さいときは、そう正直に書くこと",
    ]
    if any(item.compared_to == COMPARED_TO_MARKET for item in plan.items):
        rules.append("お得額は、一般サイトの価格がある施設はそれと、ない施設は定価と比べたもの。施設ごとに、どちらと比べたかを取り違えないこと。"
                     "一般サイトの方が安い施設があれば、そう正直に書くこと")
    if plan.alternative:
        rules.append("このプランは利用者が挙げたエリア以外からの代替案なので、冒頭でそのことを断り、代わりに勧める理由を書くこと")
    rules.append("説明文だけを出力すること")

    prompt = "あなたは企業の福利厚生サービスに詳しい旅行アドバイザーです。"
    prompt += "次の1日プランについて、利用者の希望に照らして、なぜこの組み合わせがよいかを2〜3文で説明してください。\n"
    prompt += "".join(f"- {rule}\n" for rule in rules)
    prompt += f"\nエリア：{plan.area_name}\n"
    if plan.budget:
        prompt += f"宿代の予算（1泊・1人あたり）：{plan.budget:,}円\n"
    if plan.day_trip:
        prompt += "宿泊：なし（日帰り）\n"
    prompt += "プラン：\n" + "\n".join(lines) + "\n"
    prompt += f"合計のお得額（1人あたり）：{plan.total_saving:,}円\n\n利用者の希望：{request_text}"

    # ③ AI に送る
    response = OpenAI(api_key=api_key).chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=400,
    )
    return (response.choices[0].message.content or "").strip()


def explain(plan: DayPlan, request_text: str) -> str:
    """プランの説明文。AI のキーがあれば AI、なければ（または AI が失敗したら）決まった文の型。"""
    api_key = llm_api_key()
    if api_key:
        try:
            text = _explain_with_ai(plan, request_text, api_key)
        except Exception:  # AI の失敗で画面を止めない
            text = ""
        if text:
            return text
    return explain_by_rule(plan)


def _load_spots(tenant_id: str, area_id: str) -> list[Spot]:
    """エリアの周辺スポット（共通のものと、そのテナントのもの）。読み込みは spots.py に任せ、Spot の形にそろえる。"""
    spots: list[Spot] = []
    for r in spots_by_area(area_id, tenant_id):
        spots.append(Spot(id=r["id"], kind=r["kind"], name=r["name"], description=r.get("description"), url=r.get("url")))
    return spots


def _read_plan_market_rows(plan_ids: list[str]) -> list[dict[str, Any]]:
    """market_prices のうち、料金プランにひも付いた（plan_id が入った）代表値の行を読む。

    TODO(pricing.py): 料金プランごとの一般サイトの価格を読む関数が pricing.py（じゅんぺいさん担当）にできたら、
    この関数を消し、load_market_prices からそちらを呼ぶ。
    """
    if not plan_ids:
        return []
    query = table("market_prices").select("*").in_("plan_id", plan_ids).eq("is_representative", True)
    return query.execute().data


def load_market_prices(menus: list[Menu]) -> MarketsByPlan:
    """料金プランごとの一般サイトの価格（料金プランの id → 価格）。宿泊施設の料金プランだけ。

    料金プランにひも付いた価格（plan_id が入った行）だけを使う。宿ごとの価格（plan_id が空の行）は、
    どのプランの価格か分からないので使わない（1つの価格をすべてのプランと比べると、素泊まりばかり選ばれるため）。
    ひも付いた価格がないプランや、読めなかったとき（plan_id の列がまだないときを含む）は、そのプランを定価と比べる。
    """
    plan_ids = [plan.id for menu in menus if menu.category == "stay" for plan in menu.plans]
    try:
        rows = _read_plan_market_rows(plan_ids)
    except Exception:  # 一般サイトの価格が読めなくても、定価と比べて組む
        return {}
    markets: MarketsByPlan = {}
    for row in rows:
        markets[row["plan_id"]] = MarketPrice.from_row(row)
    return markets


def make_day_plans(tenant_id: str, menus: list[Menu], request_text: str, budget: Optional[int] = None,
                   requested_area_names: Iterable[str] = (),
                   markets: Optional[MarketsByPlan] = None) -> list[DayPlan]:
    """画面から呼ぶ入口。エリアごとにプランを組み、説明文を付けて返す。組めなければ空のリスト。

    menus は検索結果の順位順に並んでいる前提（順位は ranking.py が決める）。
    requested_area_names（利用者が挙げたエリア名）があれば、そのエリアのプランを先に並べ、
    それ以外のエリアのプランは代替案として後ろに並べる。合わせて最大 MAX_PLANS 個。
    宿のプランは、宿代の予算 × BUDGET_ALLOWANCE 以内のものから選ぶ。
    markets（load_market_prices の結果）を渡すと、一般サイトの価格が取れたプランは、お得額をそれと比べる。
    """
    # ① 検索結果に出てくるエリアを、上から順に全部取り出す
    area_ids = plan_area_ids(menus, limit=len(menus))
    if not area_ids:
        return []
    area_names: dict[str, str] = {}
    for area in list_areas(tenant_id):
        area_names[area.id] = area.name

    # ② 利用者が挙げたエリアがあれば、それを先に、ほかを後ろに並べ替える
    # エリア名の一部でも当たりにする（「出雲」で「松江・出雲」、「高山」で「飛騨高山」）。1文字の語は誤って当たりやすいので使わない
    words = [w for w in requested_area_names if w and len(w) >= 2]
    requested = [name for name in area_names.values() if any(w in name for w in words)]
    if requested:
        first = [a for a in area_ids if area_names.get(a) in requested]
        rest = [a for a in area_ids if area_names.get(a) not in requested]
        area_ids = first + rest

    # ③ 上から MAX_PLANS 個のエリアで、プランを組む
    plans: list[DayPlan] = []
    for area_id in area_ids[:MAX_PLANS]:
        try:
            spots = _load_spots(tenant_id, area_id)
        except Exception:  # 周辺スポットが読めなくても、福利厚生の施設だけで組む
            spots = []
        area_name = area_names.get(area_id, "")
        plan = build_day_plan(menus, spots, area_name, area_id=area_id, budget=budget, budget_allowance=BUDGET_ALLOWANCE,
                              markets=markets)
        if plan is None:
            continue
        plan.alternative = bool(requested) and area_name not in requested
        plan.explanation = explain(plan, request_text)
        plans.append(plan)
    return plans
