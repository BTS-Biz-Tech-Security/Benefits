"""検索結果の一覧。カードで価格の比較（1日プランと同じ day_plan.benefit_item で、予算内でお得額が最大の料金プラン）を表示する。並び替えは おすすめ順／お得順／価格が安い順／評価が高い順。カテゴリのチップで絞り込める。"""
from __future__ import annotations

# render_results に足した予算まわりの引数（budget・budget_categories・budget_allowance）の型を書くために追加
# Optional[int] は「int か None（省略）」、Iterable[str] は「文字列を順に取り出せるもの（リストやタプル）」の意味
from typing import Iterable, Optional

import streamlit as st

from day_plan import PlanItem, benefit_item
from models import CATEGORIES, Menu
from placeholder import image_url
from pricing import representative_prices
from posts import rating_summary
from ranking import is_new
from ui.day_plan import item_price_text
from ui.detail_page import open_detail

SORTS = {"おすすめ順": "ranked", "お得順": "diff", "価格が安い順": "price", "評価が高い順": "rating"}


def sort_key(item: tuple[int, Menu, PlanItem], mode: str, ratings: dict):
    """並べ替えのキー。おすすめ順は受け取った順（ranking の共通スコアの順）。お得順はお得額（1人あたり）の大きい順（料金プランのないものは末尾）。
    価格が安い順は、カードに出している金額（1人あたり）の安い順（料金プランのないものは末尾）。

    item の3つ目（r）は day_plan.PlanItem（render_results で benefit_item の結果を入れたもの）。
    料金プランがない施設では r.price・r.saving が None になるので、末尾に回す。
    """
    order, m, r = item
    if mode == "ranked":
        return order
    if mode == "price":
        # カードの金額（r.price）で並べる。全プランの最安値（search.min_benefit_price）で並べると、
        # カードに出している金額と順番が食い違うことがあるため
        return (r.price is None, r.price or 0)
    if mode == "rating":
        return -(ratings.get(m.id, (0, 0))[1])
    # お得順。料金プランがない（r.saving が None）施設は末尾
    return (r.saving is None, -(r.saving or 0))


def render_results(menus: list[Menu], key: str, *, budget: Optional[int] = None,
                   budget_categories: Iterable[str] = ("stay",), budget_allowance: Optional[float] = None) -> None:
    """検索結果の一覧の本体。menus は ranking.rank_menus で並べたもの。key はタブごとに部品を分けるための接頭辞。検索画面から呼ばれる。

    budget（1人あたり）を渡すと、budget_categories のカテゴリの施設で予算を超えるものに「予算＋〇〇円」のバッジを付ける。
    既定は宿だけ（1日プラン提案の「宿代の予算」）。施設を検索タブでは、選んだカテゴリ（「すべて」なら全カテゴリ）を渡す。
    budget_allowance を渡すと、予算 × budget_allowance 以内の料金プランから選ぶ（1日プラン提案タブ。1日プランと同じ金額にするため）。
    予算まわりの引数は省略でき、省略すれば予算を使わずに出す。

    予算まわりの引数は、検索画面の仮の施設一覧（ui/search_page.py の _render_menu_list）から引き継いだもの。
    1日プラン提案は予算の1.5倍までの宿を残す（search.filter_menus）ので、予算を超えた宿にバッジを付けて知らせるために要る。
    """
    if not menus:
        st.info("条件に合う施設が見つかりません。エリアや予算を変えてみてください。")
        return
    # ① 予算（× budget_allowance）以内でお得額が最大の料金プランを、1日プランと同じ計算（day_plan.benefit_item）で選ぶ
    prices = representative_prices([m.id for m in menus])
    ratings = rating_summary([m.id for m in menus])
    items = [(i, m, benefit_item("", m, budget, budget_categories, budget_allowance, prices)) for i, m in enumerate(menus)]
    # ② カテゴリのチップで絞る（何も選ばなければすべて）
    present = [k for k in CATEGORIES if any(m.category == k for m in menus)]
    picked = st.pills("カテゴリで絞る", [CATEGORIES[k] for k in present], selection_mode="multi", label_visibility="collapsed", key=f"{key}-pills")
    if picked:
        items = [it for it in items if CATEGORIES.get(it[1].category) in picked]
    # ③ 並び替え（最初はおすすめ順）
    c1, c2 = st.columns([3, 1])
    c1.caption(f"{len(items)}件（市場価格があればそれと、なければ定価と比較。金額は1人あたり）")
    mode = SORTS[c2.selectbox("並び替え", list(SORTS), label_visibility="collapsed", key=f"{key}-sort")]
    items.sort(key=lambda it: sort_key(it, mode, ratings))
    # ④ カードを描画し、ボタンで詳細へ
    for _, m, r in items:
        with st.container(border=True):
            c0, c1, c2 = st.columns([1, 3, 1])
            c0.image(image_url(m.photo_url, m.name, m.category, width=200, height=120), width="stretch")
            cat_icon = {"stay": ":material/bed:", "meal": ":material/restaurant:", "leisure": ":material/attractions:"}.get(m.category, "")
            cat_color = {"stay": "violet", "meal": "orange", "leisure": "green"}.get(m.category, "gray")
            badges = f":{cat_color}-badge[{cat_icon} {CATEGORIES.get(m.category, m.category)}]"
            if is_new(m.content_updated_at):
                badges += " :red-badge[:material/fiber_new: 新着]"
            if any(p.coupon_code for p in m.plans):
                badges += " :blue-badge[:material/confirmation_number: クーポンあり]"
            cnt, avg = ratings.get(m.id, (0, None))
            c1.markdown(f"#### {m.name}")
            c1.markdown(badges + (f"　社員の評価 ★{avg}（{cnt}件）" if cnt else ""))
            if m.external_rating is not None:
                c1.caption(f"外部サイトの評価 ★{m.external_rating}（{m.external_review_count or 0:,}件）")
            # 金額は、1日プランのカードと同じ item_price_text で出す（予算を超えていれば「予算＋〇〇円」のバッジも付く）
            # r は day_plan.PlanItem。料金プランがない施設でも r はあり、そのときは r.price が None になる
            if r.price is not None:
                c1.markdown(item_price_text(r))
            else:
                c1.markdown(":gray[価格未登録]")
            # 詳細画面へは、1日プランのカードと同じ open_detail で移る。カードに出した料金プランの id（r.plan_id）も渡すと、
            # 詳細画面の「プラン・条件」タブで、そのプランが先頭に「提案中のプラン」のバッジ付きで出る
            c2.button("詳細を見る", key=f"{key}-detail-{m.id}", icon=":material/arrow_forward:",
                      on_click=open_detail, args=(m.id, r.plan_id))