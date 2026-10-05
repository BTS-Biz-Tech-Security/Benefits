"""Supabaseへの接続。接続情報は .streamlit/secrets.toml から読む。"""
from __future__ import annotations

import streamlit as st
from supabase import Client, create_client

SCHEMA = "bts_app"


@st.cache_resource
def client() -> Client:
    """アプリ全体で1つのクライアントを共有する（cache_resourceで再生成を防ぐ）。"""
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["anon_key"]
    return create_client(url, key)


def table(name: str):
    """bts_app スキーマのテーブルを指すクエリビルダーを返す。"""
    return client().schema(SCHEMA).table(name)
