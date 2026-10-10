"""クーポン使用履歴。自分がクーポンを使った施設とコードを一覧で見る。"""
from __future__ import annotations

import streamlit as st

from session import require_login
from db import table
from models import Plan


def render() -> None:
    """自分の行動ログ（クーポン）から、施設名・プラン名・コードを新しい順に出す。"""
    user = require_login()
    st.subheader(":material/confirmation_number: クーポン使用履歴")
    logs = table("activity_logs").select("*").eq("user_id", user.id).eq("kind", "coupon").order("occurred_at", desc=True).execute().data
    if not logs:
        st.info("まだクーポンを使っていません。施設の詳細のプラン・条件タブで「クーポンを使って予約する」を押すと、ここに残ります。")
        return
    plan_ids = [l["plan_id"] for l in logs if l.get("plan_id")]
    plans = {p["id"]: Plan.from_row(p) for p in table("plans").select("*").in_("id", plan_ids).execute().data} if plan_ids else {}
    menu_ids = list({l["menu_id"] for l in logs if l.get("menu_id")})
    menus = {m["id"]: m["name"] for m in table("menus").select("id,name").in_("id", menu_ids).execute().data} if menu_ids else {}
    seen = set()
    for l in logs:
        key = (l.get("menu_id"), l.get("plan_id"))
        if key in seen:
            continue
        seen.add(key)
        p = plans.get(l.get("plan_id"))
        with st.container(border=True):
            st.markdown(f"**{menus.get(l.get('menu_id'), '')}**" + (f"　{p.name}" if p else "") + f"　:gray[{str(l['occurred_at'])[:10].replace('-', '/')}]")
            if p and p.coupon_code:
                st.code(p.coupon_code, language=None)
            if p and p.member_url:
                st.link_button("予約ページを開く", p.member_url, icon=":material/open_in_new:")
