"""クーポンのカード。コードの表示・コピー、使用の記録、予約ページと口コミへの入口。"""
from __future__ import annotations

import streamlit as st

from coupon import acquire, member_link
from dialogs.post import open_post_dialog
from models import Menu, Plan, User


def render_coupon_card(user: User, menu: Menu, plan: Plan) -> None:
    """詳細画面のプラン・条件タブで、各料金プランの下に出す。"""
    with st.container(border=True):
        # ① 左に説明、右にコピーできるコード
        k1, k2 = st.columns([1, 1], vertical_alignment="center")
        k1.markdown(":blue-badge[:material/confirmation_number: クーポン]")
        k1.markdown(f"予約ページでこのコードを入力すると、福利厚生価格 **{plan.benefit_price:,}円** になります")
        k2.caption("クーポンコード（右端のアイコンでコピー）")
        k2.code(plan.coupon_code, language=None)
        b1, b2 = st.columns([1, 1])
        if not st.session_state.get(f"opened-{plan.id}"):
            # ② 使ったこと・予約ページへ進んだことを1回の操作で記録する
            if b1.button("クーポンを使って予約する", key=f"cp-{plan.id}", type="primary", icon=":material/confirmation_number:", use_container_width=True):
                acquire(user, plan)
                if plan.member_url:
                    member_link(user, plan)
                st.session_state[f"opened-{plan.id}"] = True
                st.rerun()
        else:
            # ③ 押したあとは同じ位置に予約ページと口コミの入口
            if plan.member_url:
                b1.link_button("予約ページを開く", plan.member_url, type="primary", icon=":material/open_in_new:", use_container_width=True)
            if b2.button("口コミを書く", key=f"post-{plan.id}", icon=":material/rate_review:", use_container_width=True):
                open_post_dialog(user, menu, plan)
            st.caption("コードは予約ページで入力してください。「クーポン使用履歴」からいつでも見られます")
