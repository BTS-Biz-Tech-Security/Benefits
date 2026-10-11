"""検索結果の一覧。カードで価格の比較（pricing.best_plan_saving）を表示する。並び替えは おすすめ順／お得順／価格が安い順／評価が高い順。カテゴリのチップで絞り込める。"""
from __future__ import annotations

import streamlit as st

from models import CATEGORIES, Menu
from placeholder import image_url
from pricing import PlanSaving, best_plan_saving, representative_prices
from posts import rating_summary
from ranking import is_new
from search import min_benefit_price
from ui.day_plan import price_text

SORTS = {"おすすめ順": "ranked", "お得順": "diff", "価格が安い順": "price", "評価が高い順": "rating"}


def sort_key(item: tuple[int, Menu, PlanSaving | None], mode: str, ratings: dict):
    """並べ替えのキー。おすすめ順は受け取った順（ranking の共通スコアの順）。お得順はお得額（1人あたり）の大きい順（料金プランのないものは末尾）。"""
    order, m, r = item
    if mode == "ranked":
        return order
    if mode == "price":
        price = min_benefit_price(m)
        return (price is None, price or 0)
    if mode == "rating":
        return -(ratings.get(m.id, (0, 0))[1])
    return -(r.saving if r else -10**9)


def render_results(menus: list[Menu], key: str) -> None:
    """検索結果の一覧の本体。menus は ranking.rank_menus で並べたもの。key はタブごとに部品を分けるための接頭辞。検索画面から呼ばれる。"""
    if not menus:
        st.info("条件に合う施設が見つかりません。エリアや予算を変えてみてください。")
        return
    # ① 市場価格と口コミの要約をまとめて取る。施設ごとに、お得額が最大の料金プランの価格の比較を出す
    prices = representative_prices([m.id for m in menus])
    ratings = rating_summary([m.id for m in menus])
    items = [(i, m, best_plan_saving(m.plans, prices)) for i, m in enumerate(menus)]
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
            c0.image(image_url(m.photo_url, m.name, m.category, width=200, height=120), use_container_width=True)
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
            if r is not None:
                c1.markdown(price_text(r.compared_price, r.benefit_price, r.saving, r.saving_rate, r.compared_to))
            else:
                c1.markdown(":gray[価格未登録]")
            if c2.button("詳細を見る", key=f"{key}-detail-{m.id}", icon=":material/arrow_forward:"):
                st.session_state["menu_id"] = m.id
                st.session_state["page"] = "detail"
                st.rerun()