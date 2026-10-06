"""福利厚生検索アプリ MVP の入口。ページ設定、サイドバー、画面の切り替え。

画面は、その画面を作るプルリクエストの中で PAGES と ⑤ の呼び分けに足していく。
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from db import table
from models import ROLES, User
from auth import logout
from session import current_user, set_user
from ui.login_form import render_login_form

ASSETS = Path(__file__).resolve().parent / "assets"

# メニューに出す画面 {キー: 表示名}
PAGES: dict[str, str] = {
    "search": ":material/search: 検索",
}

# ① ページ設定とロゴ（st.set_page_config・st.logo）
st.set_page_config(page_title="福利厚生検索アプリ", page_icon=str(ASSETS / "icon.png"), layout="wide")

st.logo(str(ASSETS / "logo.png"), size="large")

# ② 開発用ログイン: サイドバーで見本の利用者を選ぶと、その人としてログインした状態になる
#    パスワードを確かめない仕組みなので、本番運用では外す
st.sidebar.title("福利厚生検索アプリ")
users = [User.from_row(r) for r in table("users").select("*").is_("deleted_at", "null").order("name").execute().data]
labels = {f"{u.name}（{ROLES.get(u.role, u.role)}・{u.department or ''}）": u for u in users}
# 選び直したときだけ切り替える（ログインフォームでのログインを上書きしないため）
st.sidebar.selectbox("開発用: 利用者を選ぶ", list(labels), index=None, key="dev_user", placeholder="選ぶとその人としてログインした状態になる",
                     on_change=lambda: set_user(labels[st.session_state["dev_user"]]) if st.session_state.get("dev_user") else None)

# ③ サイドバー（with st.sidebar）
#    未ログイン: ログインフォーム（ui/login_form.py）
#    ログイン後: 名前、PAGES のメニュー、ログアウト
user = current_user()
with st.sidebar:
    if user is None:
        render_login_form()
    else:
        st.write(f"{user.name}（{user.department or ''}）")
        pages = dict(PAGES)
        if user.is_admin():
            pages["admin"] = ":material/settings: メニュー管理"  # 人事・経営の人にだけ出す
        if pages:
            choice = st.radio("メニュー", list(pages.values()), label_visibility="collapsed")
            chosen = next(k for k, v in pages.items() if v == choice)
            # 詳細画面（メニューにない画面）を開いている間は、メニューの「検索」で上書きしない。
            # 詳細画面からは「検索結果に戻る」で戻る。ほかのメニューを選んだときは、そちらに移る
            if st.session_state.get("page") != "detail" or chosen != "search":
                st.session_state["page"] = chosen
        if st.button("ログアウト", icon=":material/logout:"):
            logout()
            # 前の人の検索結果や開いていた画面が、次にログインした人に見えないよう、画面の状態をすべて消す
            st.session_state.clear()
            st.rerun()

# ④ 未ログインなら案内を出して止める（st.stop）
if user is None:
    st.info("左のフォームから、メールアドレスとパスワードでログインしてください。")
    st.stop()

# ⑤ st.session_state["page"] に応じて ui/ の render() を読み込んで呼ぶ
page = st.session_state.get("page")
if page is None:
    st.subheader("福利厚生検索アプリ")
    st.write(f"{user.name}さん、ようこそ。")
elif page == "search":
    from ui.search_page import render
    render()
elif page == "detail":
    from ui.detail_page import render
    render()
elif page == "admin":
    from ui.admin_page import render
    render()
