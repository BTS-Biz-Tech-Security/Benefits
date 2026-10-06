"""管理画面（人事・経営のみ）。メニュー管理と、開発予定の2タブ（利用の記録・社内ツール連携）。"""
from __future__ import annotations

from typing import Optional

import streamlit as st

from db import table
from models import CATEGORIES, MENU_COLUMNS, Menu, User
from search import rows_of
from session import require_role

UNSELECTED = "（選択）"


def render() -> None:
    """管理画面。app.py から呼ばれる（メニューに出るのは人事・経営の人だけ）。"""
    user = require_role("hr", "executive")
    tab_menu, tab_usage, tab_notify = st.tabs([":material/edit_note: メニュー管理", ":material/bar_chart: 利用の記録（開発予定）",
                                               ":material/notifications: 社内ツール連携（開発予定）"])
    with tab_menu:
        _render_menus(user)
    with tab_usage:
        # 見た目のみ（第6回決定）。集計は MVP のあとに作る
        st.caption("クーポン使用数・予約ページを開いた数・ログイン数を期間で集計します。MVP では見た目のみです。")
        col1, col2, col3 = st.columns(3)
        col1.metric("クーポン使用", "—")
        col2.metric("予約ページを開いた数", "—")
        col3.metric("ログイン", "—")
        st.date_input("期間", value=(), disabled=True)
    with tab_notify:
        # 見た目のみ（第6回決定）。会社ごとに使う連絡手段が違うため、横展開を考えてあとに回す
        st.caption("新着メニューや差額の実例を、社内の連絡手段に通知します。MVP では見た目のみです。")
        st.selectbox("通知先", ["Slack", "Teams", "メール"], disabled=True)
        st.button("通知を送る（開発予定）", disabled=True)


def _render_menus(user: User) -> None:
    """メニュー管理タブ。自社の施設の一覧と、選んだ1件の編集フォーム。"""
    # ① 自社の施設を読む
    query = table("menus").select(MENU_COLUMNS).eq("tenant_id", user.tenant_id).is_("deleted_at", "null").order("name")
    menus = [Menu.from_row(r) for r in rows_of(query)]
    st.caption(f"{len(menus)}件。一括登録は運用担当が行います。")

    # ② 施設を選ぶ（同じ名前の施設があっても区別できるよう、id で選ぶ）
    by_id = {menu.id: menu for menu in menus}
    picked = st.selectbox("編集するメニュー", [UNSELECTED, *by_id],
                          format_func=lambda key: by_id[key].name if key in by_id else key)
    if picked == UNSELECTED:
        st.table([{"施設名": m.name, "カテゴリ": CATEGORIES.get(m.category, m.category), "取得元の宿ID": m.hotel_ref or "",
                   "名寄せ済み": "○" if m.matched else ""} for m in menus])
        return
    _render_edit_form(user, by_id[picked])


def _render_edit_form(user: User, menu: Menu) -> None:
    """選んだ施設の編集フォーム。保存すると menus を更新する（自社の施設だけ）。"""
    with st.form("edit_menu"):
        name = st.text_input("施設名", menu.name)
        tags = st.text_input("タグ（読点「、」区切り。検索ワードの照合に使う）", "、".join(menu.tags))
        description = st.text_area("説明文", menu.description or "")
        hotel_ref = st.text_input("楽天トラベルのホテル番号", menu.hotel_ref or "")
        usage_limit = st.text_input("利用回数の上限", menu.usage_limit or "")
        family_scope = st.text_input("家族の範囲", menu.family_scope or "")
        cancel_policy = st.text_input("キャンセル条件", menu.cancel_policy or "")
        procedure = st.text_area("利用手順", menu.procedure or "")
        if not st.form_submit_button("保存", type="primary"):
            return

    # ① 入力を確かめる
    if not name.strip():
        st.error("施設名は必須です")
        return

    # ② 保存する形に整える（空の欄は「未設定」にする。タグは「、」と「,」のどちらで区切ってもよい）
    tag_list = [t.strip() for t in tags.replace(",", "、").split("、") if t.strip()]
    row = {
        "name": name.strip(),
        "description": _or_none(description),
        "tags": tag_list,
        "hotel_ref": _or_none(hotel_ref),
        "matched": bool(hotel_ref.strip()),
        "usage_limit": _or_none(usage_limit),
        "family_scope": _or_none(family_scope),
        "cancel_policy": _or_none(cancel_policy),
        "procedure": _or_none(procedure),
    }

    # ③ 自社の施設だけを更新する（他社の施設の id を指定されても書き換えないよう、テナントでも絞る）
    table("menus").update(row).eq("id", menu.id).eq("tenant_id", user.tenant_id).execute()
    st.success("保存しました")


def _or_none(text: str) -> Optional[str]:
    """前後の空白を除き、空なら None（未設定）にする。"""
    text = text.strip()
    return text or None
