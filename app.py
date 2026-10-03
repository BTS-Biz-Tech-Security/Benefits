"""福利厚生検索アプリ MVP の入口。ページ設定、サイドバー、画面の切り替え。

画面は、その画面を作るプルリクエストの中で PAGES と ⑤ の呼び分けに足していく。
ログインフォームとログアウトは、ログイン機能のプルリクエストでつなぐ。
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from db import table
from models import User
from session import current_user, set_user

ASSETS = Path(__file__).resolve().parent / "assets"

# メニューに出す画面 {キー: 表示名}
PAGES: dict[str, str] = {}

# ① ページ設定とロゴ（st.set_page_config・st.logo）
st.set_page_config(page_title="福利厚生検索アプリ", page_icon=str(ASSETS / "icon.png"), layout="wide")

st.logo(str(ASSETS / "logo.png"), size="large")

# ② 開発用: secrets.toml に login_as（メールアドレス）があれば、その利用者としてログインした状態にする
#    パスワードを確かめないため、本番（Streamlit Cloud など）の設定には書かない
try:
    login_as = st.secrets.get("login_as")
except Exception:
    login_as = None
if login_as and current_user() is None:
    rows = table("users").select("*").eq("email", login_as).is_("deleted_at", "null").limit(1).execute().data
    if rows:
        set_user(User.from_row(rows[0]))

# ③ サイドバー（with st.sidebar）。ログイン中なら名前と、PAGES のメニュー
user = current_user()
with st.sidebar:
    st.title("福利厚生検索アプリ")
    if user is not None:
        st.write(f"{user.name}（{user.department or ''}）")
        if login_as:
            st.caption("開発用ログイン中（secrets.toml の login_as）")
        if PAGES:
            choice = st.radio("メニュー", list(PAGES.values()), label_visibility="collapsed")
            st.session_state["page"] = next(k for k, v in PAGES.items() if v == choice)

# ④ 未ログインなら案内を出して止める（st.stop）
if user is None:
    st.info("ログインしてください。ログイン機能ができるまでは、secrets.toml の login_as でログインした状態にします。")
    st.stop()

# ⑤ st.session_state["page"] に応じて ui/ の render() を読み込んで呼ぶ
page = st.session_state.get("page")
if page is None:
    st.subheader("福利厚生検索アプリ")
    st.write(f"{user.name}さん、ようこそ。")
