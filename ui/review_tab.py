"""詳細の口コミタブ。件数・星の平均・お得感の満足の割合、口コミの一覧（写真つき）、口コミを書く入口。"""
from __future__ import annotations

import streamlit as st

from dialogs.post import open_post_dialog
from models import SUB_RATINGS, Menu, Post, User
from posts import list_by_menu, summary


def stars(value: int) -> str:
    """星の数を「★★★★☆」の形にする。"""
    return "★" * value + "☆" * (5 - value)


def _render_post(post: Post) -> None:
    """口コミ1件。星・投稿者（家族構成）・利用時期、お得感と項目ごとの星、コメント、写真の順に出す。"""
    with st.container(border=True):
        # ① 総合の星と、投稿者・利用時期
        who = post.user_name or "社員"
        if post.user_family:
            who += f"（{post.user_family}）"
        when = f"{post.used_at[:7].replace('-', '/')}に利用" if post.used_at else post.created_at.strftime("%Y/%m/%d")
        st.markdown(f"{stars(post.rating)}　**{who}**　:gray[{when}]")
        # ② お得感と、項目ごとの星（入力のあるものだけ）
        details = []
        if post.deal_rating:
            details.append(f"お得感 {stars(post.deal_rating)}")
        details += [f"{SUB_RATINGS[key]} {value}" for key, value in post.sub_ratings.items()]
        if details:
            st.caption("　".join(details))
        # ③ コメントと写真
        if post.comment:
            st.write(post.comment)
        if post.photo_url:
            st.image(post.photo_url, width=280)


def render_review_tab(user: User, menu: Menu) -> None:
    """口コミタブの中身。詳細画面の枠から呼ばれる。"""
    # ① 一覧と集計を取る
    posts = list_by_menu(menu.id)
    s = summary(posts)
    # ② 見出し（件数・平均・お得感の満足の割合）と、口コミを書くボタン
    col_summary, col_button = st.columns([3, 1], vertical_alignment="center")
    if s.count:
        col_summary.markdown(f"**{s.count}件**　平均 ★{s.average}")
        if s.deal_satisfaction is not None:
            col_summary.caption(f"お得感に満足：{round(s.deal_satisfaction * 100)}%（{s.deal_count}件中）")
    if col_button.button("口コミを書く", icon=":material/rate_review:", key=f"review-write-{menu.id}"):
        open_post_dialog(user, menu, None)
    # ③ 空状態
    if not posts:
        st.info("まだ口コミがありません。利用したら最初の口コミを書いてみてください。")
    # ④ 新しい順に表示
    for post in posts:
        _render_post(post)
