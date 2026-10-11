"""検索前の画面。お得ランキング・新着・最近の口コミを見せる。"""
from __future__ import annotations

import streamlit as st

from models import User
from placeholder import image_url
from posts import recent_posts
from ranking import new_menus, top_deals
from search import min_benefit_price


def render_home(user: User) -> None:
    """検索フォームの下に出す。検索したら消える。件数が少なくても見劣りしないよう、数の集計は出さない。"""
    # ① お得ランキング（市場価格とのお得額トップ5の宿）。セクションごとに区切り線と見出しを置く
    st.divider()
    st.subheader(":material/trophy: お得ランキング")
    st.caption("市場価格（楽天トラベル）より安く泊まれる宿の上位5件。金額は1人あたり")
    cols = st.columns(5)
    for i, (m, r) in enumerate(top_deals(user.tenant_id, 5)):
        with cols[i]:
            # 施設名は長さがまちまちで折り返すため、ボタンより下に置いて位置を揃える
            st.image(image_url(m.photo_url, m.name, m.category, width=200, height=120), use_container_width=True)
            st.markdown(f"**{i+1}位**　:green[**{r.saving:,}円お得**（{r.saving_rate}%）]")
            if st.button("詳細を見る", key=f"rank-{m.id}", use_container_width=True):
                st.session_state["menu_id"] = m.id; st.session_state["page"] = "detail"; st.rerun()
            st.caption(m.name)
    # ② 新着（ランキングと同じカードの形で、画像・最安の福利厚生価格・ボタン・施設名）
    new = new_menus(user.tenant_id, 5)
    if new:
        st.divider()
        st.subheader(":material/fiber_new: 新着")
        st.caption("最近追加・更新された宿")
        cols = st.columns(5)
        for i, m in enumerate(new):
            with cols[i]:
                st.image(image_url(m.photo_url, m.name, m.category, width=200, height=120), use_container_width=True)
                st.markdown(f":red-badge[新着]　**{min_benefit_price(m):,}円〜**")
                if st.button("詳細を見る", key=f"new-{m.id}", use_container_width=True):
                    st.session_state["menu_id"] = m.id; st.session_state["page"] = "detail"; st.rerun()
                st.caption(m.name)
    # ③ 最近の口コミ
    posts = recent_posts(user.tenant_id, 3)
    if posts:
        st.divider()
        st.subheader(":material/reviews: 最近の口コミ")
        st.caption("社員が最近書いた口コミ")
        for p in posts:
            with st.container(border=True):
                st.write("★" * int(p["rating"]) + "☆" * (5 - int(p["rating"])) + f"　**{p['menu_name']}**　{(p.get('users') or {}).get('name', '社員')}")
                if p.get("comment"):
                    st.write(p["comment"])
                if p.get("photo_url"):
                    st.image(p["photo_url"], width=200)