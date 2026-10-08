"""サイドバーのログインフォーム。メールアドレスとパスワードを受け取り、ログインして画面を更新する。"""
from __future__ import annotations

import streamlit as st

from auth import login
from models import User


def _log_login(user: User) -> None:
    """行動ログに「ログイン」を残す。

    TODO(activity.py): 行動ログの記録は activity.py（なかりんさん担当）の log() の役割。
    activity.py ができるまでは何もしない。できたら、この関数の中身を log(user, "login") の1行にする。
    """
    try:
        from activity import log  # type: ignore[import-not-found]
    except ImportError:
        return
    log(user, "login")


def render_login_form() -> None:
    """未ログインのとき、app.py がサイドバーの中で呼ぶ。"""
    # ① メールアドレスとパスワードの入力欄（st.form でまとめて送る）
    with st.form("login"):
        email = st.text_input("メールアドレス")
        password = st.text_input("パスワード", type="password")
        if st.form_submit_button("ログイン", type="primary", icon=":material/login:"):
            # ② ログインを試し、失敗ならエラーを出す
            user = login(email, password)
            if user is None:
                st.error("メールアドレスまたはパスワードが違います")
            else:
                # ③ 成功したら行動ログに「ログイン」を残し、画面を更新する
                _log_login(user)
                st.rerun()
