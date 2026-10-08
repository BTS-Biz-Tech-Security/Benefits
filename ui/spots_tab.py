"""詳細の周辺タブ。クローリングで集めた食事・レジャーを出す。"""
from __future__ import annotations

import streamlit as st

from models import Menu, User
from spots import spots_by_area


def render_spots_tab(user: User, menu: Menu) -> None:
    """周辺タブの中身。詳細画面の枠から呼ばれる。"""
    # ① エリアの周辺情報を取る
    spots = spots_by_area(menu.area_id, user.tenant_id)
    if not spots:
        st.info("周辺の情報はまだありません。")
    # ② 食事・レジャーに分けてリンク付きで並べる
    for kind, label in (("meal", ":material/restaurant: 食事"), ("leisure", ":material/attractions: レジャー")):
        items = [sp for sp in spots if sp["kind"] == kind]
        if items:
            st.markdown(f"**{label}**")
            for sp in items:
                st.write(f"- [{sp['name']}]({sp['url']})　:gray[{sp.get('description') or ''}]")
    st.caption("公開情報をもとにした案内です。宿の比較には使っていません。")
