"""福利厚生検索アプリ MVP の入口。ページ設定、サイドバー、画面の切り替え。"""
from __future__ import annotations

import importlib
from pathlib import Path

import streamlit as st

from db import table
from models import User
from session import current_user, set_user

# ログイン機能（auth.py・ui/login_form.py）ができる前でも起動できるようにする。その間は login_as で確かめる
try:
    from auth import logout
    from ui.login_form import render_login_form
except ModuleNotFoundError:
    logout = None
    render_login_form = None

ASSETS = Path(__file__).resolve().parent / "assets"

# ① ページ設定とロゴ（st.set_page_config・st.logo）
st.set_page_config(page_title="福利厚生検索アプリ", page_icon=str(ASSETS / "icon.png"), layout="wide")

st.logo(str(ASSETS / "logo.png"), size="large")

# ② 開発用: secrets.toml に login_as（メールアドレス）があれば、その利用者としてログインした状態にする
#    パスワードを確かめないため、本番（Streamlit Cloud など）の設定には書かない
#    ログアウトした後は自動ログインしない（ログインフォームを確かめられるようにするため）
try:
    login_as = st.secrets.get("login_as")
except Exception:
    login_as = None
if login_as and current_user() is None and not st.session_state.get("login_as_off"):
    rows = table("users").select("*").eq("email", login_as).is_("deleted_at", "null").limit(1).execute().data
    if rows:
        set_user(User.from_row(rows[0]))

# ③ サイドバー（with st.sidebar）
#    未ログイン: render_login_form()（ui/login_form.py）
#    ログイン後: 名前、st.radio でページを選ぶ（人事ならメニュー管理も）、ログアウト
user = current_user()
with st.sidebar:
    st.title("福利厚生検索アプリ")
    if user is None:
        if render_login_form:
            render_login_form()
        else:
            st.caption("ログイン機能はまだありません。secrets.toml の login_as で確かめてください")
    else:
        st.write(f"{user.name}（{user.department or ''}）")
        if login_as:
            st.caption("開発用ログイン中（secrets.toml の login_as）")
        pages = {"search": ":material/search: 検索", "mypage": ":material/confirmation_number: クーポン使用履歴"}
        if user.is_admin():
            pages["admin"] = ":material/settings: メニュー管理"
        choice = st.radio("メニュー", list(pages.values()), label_visibility="collapsed")
        chosen = next(k for k, v in pages.items() if v == choice)
        if st.session_state.get("page") not in ("detail",) or chosen != "search":
            st.session_state["page"] = chosen
        if logout and st.button("ログアウト", icon=":material/logout:"):
            logout()
            st.session_state["login_as_off"] = True
            st.rerun()

# ④ 未ログインなら案内を出して止める（st.stop）
if user is None:
    st.info("左からログインしてください。" if render_login_form else "secrets.toml の login_as でログインした状態にして確かめてください。")
    st.stop()

# ⑤ st.session_state["page"] に応じて ui/ の render() を読み込んで呼ぶ
#    まだないファイルがある画面は、止まらずに「まだできていない」と出す（各担当が並行して作るため）
PAGES = {"search": "ui.search_page", "detail": "ui.detail_page", "admin": "ui.admin_page", "mypage": "ui.mypage"}
module_name = PAGES.get(st.session_state.get("page", "search"), "ui.search_page")
try:
    render = importlib.import_module(module_name).render
except ModuleNotFoundError as e:
    st.info(f"この画面はまだ動きません（{e.name} がまだありません）")
    st.stop()
render()
