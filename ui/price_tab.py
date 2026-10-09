"""詳細の価格比較タブ。プランごとに福利厚生価格・一般サイトの価格・差額を出す。"""
from __future__ import annotations

import streamlit as st

from models import Menu, User
from pricing import evaluate, representative_prices
from ui.coupon_card import render_coupon_card


def render_price_tab(user: User, menu: Menu) -> None:
    """価格比較タブの中身。詳細画面の枠から呼ばれる。クーポンのカードは ui/coupon_card.py に任せる。"""
    # ① 宿泊なら一般サイトの価格（比べる日）を取る
    market = representative_prices([menu.id]).get(menu.id) if menu.category == "stay" else None
    # ② プランごとに価格の3つ（福利厚生・一般サイト・差額）を並べる
    for p in menu.plans:
        with st.container(border=True):
            st.markdown(f"**{p.name}**" + (f"　:gray[{p.room_type or ''} {p.meal or ''}]" if p.room_type or p.meal else ""))
            if menu.category == "stay":
                r = evaluate(p, market)
                m1, m2, m3 = st.columns(3)
                m1.metric("福利厚生価格", f"{r.benefit_price:,}円")
                if r.market_price is not None:
                    m2.metric("一般サイトの価格", f"{r.market_price:,}円")
                    m3.metric("差額", f"{r.diff:+,}円")
                    m3.caption(":green[お得]" if r.diff > 0 else ":red[一般サイトの方が安い]")
                    st.caption(f"一般サイトの価格は{r.fetched_at[:10].replace('-', '/')}時点" + ("（楽天トラベル）" if r.source == "rakuten_api" else "（仮の値）") + ("　※人数・泊数を換算した目安" if r.reference else ""))
                else:
                    m2.metric("一般サイトの価格", "—")
                    m3.metric("差額", "—")
                    m3.caption("一般サイトの価格を調べられませんでした")
            else:
                st.write(f"福利厚生価格 {p.benefit_price:,}円")
            # ③ クーポンがあればカードを出す
            if p.coupon_code:
                render_coupon_card(user, menu, p)