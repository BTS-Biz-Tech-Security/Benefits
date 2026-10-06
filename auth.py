"""ログインとログアウト。Supabase Auth でメールとパスワードを確かめ、アプリ内の利用者（bts_app.users）に結びつける。

パスワードを確かめるときは、その場限りの接続（_auth_client）を使い、確かめたらすぐにサインアウトする。
db.client() はアプリ全体で1つを共有しているので、そこでログインすると、最後にログインした人の認証情報が
他の利用者の問い合わせにも使われてしまうため。ログイン中の利用者は、これまでどおり session.py で覚える。
"""
from __future__ import annotations

from typing import Any, Optional

import streamlit as st
from supabase import Client, create_client

from db import table
from models import User
from search import rows_of
from session import clear_user, set_user


def _auth_client() -> Client:
    """パスワードを確かめるためだけの、その場限りの接続。"""
    return create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["anon_key"])


def login(email: str, password: str) -> Optional[User]:
    """メールとパスワードを確かめ、アプリ内の利用者に結びつけてセッションに保存する。失敗は None。"""
    email = email.strip()
    if not email or not password:
        return None

    # ① Supabase Auth にメールとパスワードで問い合わせる
    auth_client = _auth_client()
    try:
        res: Any = auth_client.auth.sign_in_with_password({"email": email, "password": password})
    except Exception:  # メールかパスワードが違う、または接続できない
        return None

    # ② 認証IDを取り出し、その場限りの接続はすぐにサインアウトする（認証情報を残さない）
    auth_id = res.user.id if res and res.user else None
    try:
        auth_client.auth.sign_out()
    except Exception:
        pass
    if not auth_id:
        return None

    # ③ bts_app.users から auth_id の一致する利用者を取る
    rows = rows_of(table("users").select("*").eq("auth_id", auth_id).is_("deleted_at", "null").limit(1))
    if not rows:
        return None  # ログイン用のアカウントはあるが、アプリの利用者に結びついていない

    # ④ 利用者の型にしてセッションに保存する
    user = User.from_row(rows[0])
    set_user(user)
    return user


def logout() -> None:
    """セッションの利用者を消す。Supabase Auth の認証情報は login() の中で消しているので、ここではセッションだけ。"""
    clear_user()
