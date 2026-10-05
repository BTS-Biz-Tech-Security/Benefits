"""ログイン中の利用者の取り出しと、画面の利用制限。各画面はここだけを使い、ログインの作り方には依存しない。"""
from __future__ import annotations

from typing import Optional

import streamlit as st

from models import User

SESSION_KEY = "bts_user"


def set_user(user: User) -> None:
    """ログインした利用者をセッションに保存する。auth.py から呼ばれる。"""
    st.session_state[SESSION_KEY] = user


def clear_user() -> None:
    """セッションの利用者を消す。ログアウト時に auth.py から呼ばれる。"""
    st.session_state.pop(SESSION_KEY, None)


def current_user() -> Optional[User]:
    """セッションに保存された利用者。未ログインなら None。"""
    return st.session_state.get(SESSION_KEY)


def require_login() -> User:
    """未ログインなら案内を出して処理を止める。各画面の1行目に置く。"""
    user = current_user()
    if user is None:
        st.info("ログインしてください。")
        st.stop()
    return user


def require_role(*roles: str) -> User:
    """指定した役割以外なら止める（メニュー管理など人事向けの画面用）。"""
    user = require_login()
    if user.role not in roles:
        st.warning("この画面を見る権限がありません。")
        st.stop()
    return user
