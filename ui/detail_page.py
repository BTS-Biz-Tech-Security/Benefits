"""詳細画面。施設の見出しと、3つのタブ（プラン・条件／口コミ／周辺）を持つ。

検索結果や1日プランで施設名を押すと、open_detail() で施設を覚えて、この画面に移る。
各タブの中身は担当ごとのファイルが描く。クーポンのカードは、プラン・条件タブの各料金プランの下に出す。
"""
from __future__ import annotations

import streamlit as st

from day_plan import load_market_prices, plan_saving
from models import CATEGORIES, Menu, User
from search import get_menu
from session import require_login
from ui.coupon_card import render_coupon_card
from ui.review_tab import render_review_tab
from ui.spots_tab import render_spots_tab

# カテゴリごとのバッジの色とアイコン
CATEGORY_BADGES = {
    "stay": ("violet", ":material/bed:"),
    "meal": ("orange", ":material/restaurant:"),
    "leisure": ("green", ":material/attractions:"),
}


def open_detail(menu_id: str) -> None:
    """施設を覚えて、詳細画面に移る。ボタンの on_click に渡して使う。"""
    st.session_state["menu_id"] = menu_id
    st.session_state["page"] = "detail"


def back_to_search() -> None:
    """検索画面に戻る。検索結果は st.session_state に残っているので、そのまま表示される。"""
    st.session_state["page"] = "search"


def render() -> None:
    """詳細画面。app.py から呼ばれる。"""
    user = require_login()

    # ① 覚えておいた施設を、DB から読む（利用者の会社の施設だけ）
    st.button("検索結果に戻る", icon=":material/arrow_back:", on_click=back_to_search)
    menu_id = st.session_state.get("menu_id")
    menu = get_menu(menu_id, user.tenant_id) if menu_id else None
    if menu is None:
        st.info("検索結果から施設を選んでください。")
        return

    # ② 見出し（施設名・バッジ・住所・紹介文）
    st.subheader(menu.name)
    color, icon = CATEGORY_BADGES.get(menu.category, ("gray", ""))
    badges = f":{color}-badge[{icon} {CATEGORIES.get(menu.category, menu.category)}]"
    if any(plan.coupon_code for plan in menu.plans):
        badges += "　:blue-badge[:material/confirmation_number: クーポンあり]"
    st.markdown(badges)
    if menu.address:
        st.caption(menu.address)
    if menu.description:
        st.write(menu.description)

    # ③ 3つのタブ
    tab_plans, tab_reviews, tab_spots = st.tabs(
        [":material/bed: プラン・条件", ":material/reviews: 口コミ", ":material/map: 周辺"])
    with tab_plans:
        _render_plans_and_conditions(user, menu)
    with tab_reviews:
        render_review_tab(user, menu)
    with tab_spots:
        render_spots_tab(user, menu)


def _render_plans_and_conditions(user: User, menu: Menu) -> None:
    """プラン・条件タブ。料金プランごとの内容と金額（クーポンがあればその下にカード）、施設の利用条件を並べる。"""
    # ① 料金プラン（福利厚生価格の安い順）
    st.markdown("**料金プラン**")
    if not menu.plans:
        st.caption("料金プランは登録されていません。")
    markets = load_market_prices([menu])  # 料金プランの id → 市場価格（取れたプランだけ）
    for plan in menu.plans:
        with st.container(border=True):
            st.markdown(f"**{plan.name}**")
            details = [f"部屋 {plan.room_type or '—'}", f"食事 {plan.meal or '—'}", f"{plan.adults or 1}名・{plan.nights}泊の料金"]
            st.caption(" ／ ".join(details))
            # 1日プランや一覧と同じ見せ方（1人あたりの金額と、料金プランに書かれた金額）
            # ui.day_plan は ui.detail_page を読み込んでいるので、ここで読み込む（ファイルの先頭で読むと循環してしまう）
            from ui.day_plan import price_text
            # お得額は1日プラン・施設一覧と同じく plan_saving で計算する
            # 市場価格が取れた料金プランはそれと、取れなかったプランは定価と比べる
            compare = plan_saving(plan, markets.get(plan.id))
            st.markdown(price_text(compare.benefit_price, compare.compared_price, compare.saving, compare.saving_rate,
                                   compare.compared_to, plan_price=plan.benefit_price, plan_people=plan.adults or 1))
            # クーポンがあれば、料金プランの下にカードを出す（表示と記録は ui/coupon_card.py に任せる）
            if plan.coupon_code:
                render_coupon_card(user, menu, plan)

    # ② 利用条件
    st.markdown("**利用条件**")
    st.write(f"- 利用回数の上限：{menu.usage_limit or '—'}")
    st.write(f"- 家族の範囲：{menu.family_scope or '—'}")
    st.write(f"- キャンセル条件：{menu.cancel_policy or '—'}")
    if menu.procedure:
        st.write(f"- 利用手順：{menu.procedure}")
