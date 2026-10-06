"""詳細画面。施設の見出しと、4つのタブ（価格比較／プラン・条件／口コミ／周辺）を持つ。

検索結果や1日プランで施設名を押すと、open_detail() で施設を覚えて、この画面に移る。
各タブの中身は担当ごとのファイルが描く。まだないタブは「準備中」と出し、TODO の印を付けている。
"""
from __future__ import annotations

import streamlit as st

from models import CATEGORIES, Menu
from search import get_menu
from session import require_login

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

    # ③ 4つのタブ
    tab_price, tab_plans, tab_reviews, tab_spots = st.tabs(
        [":material/payments: 価格比較", ":material/bed: プラン・条件", ":material/reviews: 口コミ", ":material/map: 周辺"])
    with tab_price:
        # TODO(ui/price_tab.py): じゅんぺいさん担当。render_price_tab(user, menu) ができたら、この1行をその呼び出しに置き換える
        st.info("一般サイトとの価格比較は準備中です。")
    with tab_plans:
        _render_plans_and_conditions(menu)
    with tab_reviews:
        # TODO(ui/review_tab.py): なかりんさん担当。render_review_tab(user, menu) ができたら、この1行をその呼び出しに置き換える
        st.info("口コミは準備中です。")
    with tab_spots:
        # TODO(ui/spots_tab.py): なかりんさん担当。render_spots_tab(menu) ができたら、この1行をその呼び出しに置き換える
        st.info("周辺情報は準備中です。")


def _render_plans_and_conditions(menu: Menu) -> None:
    """プラン・条件タブ。料金プランごとの内容と金額、施設の利用条件を並べる。"""
    # ① 料金プラン（福利厚生価格の安い順）
    st.markdown("**料金プラン**")
    if not menu.plans:
        st.caption("料金プランは登録されていません。")
    for plan in menu.plans:
        with st.container(border=True):
            st.markdown(f"**{plan.name}**")
            details = [f"部屋 {plan.room_type or '—'}", f"食事 {plan.meal or '—'}", f"{plan.adults or 2}名・{plan.nights}泊の料金"]
            st.caption(" ／ ".join(details))
            saving = plan.list_price - plan.benefit_price
            if saving > 0:
                rate = round(saving * 100 / plan.list_price)
                st.markdown(f":gray[~~定価 {plan.list_price:,}円~~ →] **{plan.benefit_price:,}円**　"
                            f":green[**{saving:,}円お得**（{rate}%）]")
            else:
                st.markdown(f"福利厚生 **{plan.benefit_price:,}円**")

    # ② 利用条件
    st.markdown("**利用条件**")
    st.write(f"- 利用回数の上限：{menu.usage_limit or '—'}")
    st.write(f"- 家族の範囲：{menu.family_scope or '—'}")
    st.write(f"- キャンセル条件：{menu.cancel_policy or '—'}")
    if menu.procedure:
        st.write(f"- 利用手順：{menu.procedure}")
