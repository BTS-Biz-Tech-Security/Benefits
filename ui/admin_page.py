"""管理画面（人事・経営のみ）。メニュー管理、一括登録、自動取得（見た目のみ）と、開発予定の2タブ（利用の記録・社内ツール連携）。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import streamlit as st

from db import SCHEMA, client, table
from models import CATEGORIES, MENU_COLUMNS, Menu, User
from search import rows_of
from menu_import import COMBINED_COLUMNS, missing_columns, read_csv_bytes, split_rows, template_csv
from seed.load import load_menus, load_plans, validate_plan
from session import require_role

UNSELECTED = "（選択）"


def render() -> None:
    """管理画面。app.py から呼ばれる（メニューに出るのは人事・経営の人だけ）。"""
    user = require_role("hr", "executive")
    tab_menu, tab_import, tab_crawl, tab_usage, tab_notify = st.tabs(
        [":material/edit_note: メニュー管理", ":material/upload_file: 一括登録", ":material/sync: 自動取得（開発予定）",
         ":material/bar_chart: 利用の記録（開発予定）", ":material/notifications: 社内ツール連携（開発予定）"])
    with tab_menu:
        _render_menus(user)
    with tab_import:
        _render_import(user)
    with tab_crawl:
        _render_crawl()
    with tab_usage:
        # 見た目のみ（第6回決定）。集計は MVP のあとに作る
        st.caption("クーポン使用数・予約ページを開いた数・ログイン数を期間で集計します。MVP では見た目のみです。")
        col1, col2, col3 = st.columns(3)
        col1.metric("クーポン使用", "—")
        col2.metric("予約ページを開いた数", "—")
        col3.metric("ログイン", "—")
        st.date_input("期間", value=[], disabled=True)  # 期間はまだ選べない（空の範囲）
    with tab_notify:
        # 見た目のみ（第6回決定）。会社ごとに使う連絡手段が違うため、横展開を考えてあとに回す
        st.caption("新着メニューや差額の実例を、社内の連絡手段に通知します。MVP では見た目のみです。")
        st.selectbox("通知先", ["Slack", "Teams", "メール"], disabled=True)
        st.button("通知を送る（開発予定）", disabled=True)


def _render_menus(user: User) -> None:
    """メニュー管理タブ。自社の施設の一覧と、選んだ1件の編集フォーム・削除。"""
    # ① 自社の施設を読む
    query = table("menus").select(MENU_COLUMNS).eq("tenant_id", user.tenant_id).is_("deleted_at", "null").order("name")
    menus = [Menu.from_row(r) for r in rows_of(query)]
    st.caption(f"{len(menus)}件。まとめて登録するときは「一括登録」タブを使います。")
    message = st.session_state.pop("admin_message", None)  # 削除したあとの知らせ（1回だけ出す）
    if message:
        st.success(message)

    # ② 施設を選ぶ（同じ名前の施設があっても区別できるよう、id で選ぶ）
    by_id = {menu.id: menu for menu in menus}
    picked = st.selectbox("編集するメニュー", [UNSELECTED, *by_id], key="admin_menu_pick",
                          format_func=lambda key: by_id[key].name if key in by_id else key)
    if picked == UNSELECTED:
        st.table([{"施設名": m.name, "カテゴリ": CATEGORIES.get(m.category, m.category), "取得元の宿ID": m.hotel_ref or "",
                   "名寄せ済み": "○" if m.matched else ""} for m in menus])
        return
    _render_edit_form(user, by_id[picked])
    _render_delete(user, by_id[picked])


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


def _render_delete(user: User, menu: Menu) -> None:
    """施設の削除。確認のチェックを入れるまで押せない。"""
    st.divider()
    st.markdown("**この施設を削除**")
    st.caption("削除すると、検索結果・1日プラン・この一覧に出なくなります。データは消さずに残します。"
               "同じ施設名の行を一括登録すると、新しい施設として追加されます（削除した施設の料金プランは引き継ぎません）。")
    confirmed = st.checkbox("削除してよいことを確認しました", key=f"confirm_delete_{menu.id}")
    st.button("この施設を削除", icon=":material/delete:", disabled=not confirmed,
              on_click=_delete_menu, args=(user.tenant_id, menu.id, menu.name))


def _delete_menu(tenant_id: str, menu_id: str, name: str) -> None:
    """施設を削除する（データは消さず、deleted_at に削除した日時を入れる）。自社の施設だけ。ボタンの on_click から呼ぶ。"""
    now = datetime.now(timezone.utc).isoformat()
    table("menus").update({"deleted_at": now}).eq("id", menu_id).eq("tenant_id", tenant_id).execute()
    # 一覧に戻し、削除したことを知らせる
    st.session_state["admin_menu_pick"] = UNSELECTED
    st.session_state["admin_message"] = f"「{name}」を削除しました。"


def _or_none(text: str) -> Optional[str]:
    """前後の空白を除き、空なら None（未設定）にする。"""
    text = text.strip()
    return text or None


# 自動取得タブの履歴の見本（見た目のみ。第10回MTG）。本来は取得のたびに記録される
CRAWL_HISTORY_SAMPLE = [
    {"日時": "2026/10/08 06:00", "結果": "完了", "新規": 2, "更新": 15, "提携終了": 0, "備考": ""},
    {"日時": "2026/10/07 06:00", "結果": "完了", "新規": 0, "更新": 3, "提携終了": 1, "備考": ""},
    {"日時": "2026/10/06 06:00", "結果": "一部失敗", "新規": 1, "更新": 12, "提携終了": 0, "備考": "3件のページを読めませんでした"},
]


def _render_crawl() -> None:
    """自動取得タブ（見た目のみ）。本来の仕組み（福利厚生サービスの会員サイトから定期的に集める）を見せる。"""
    st.caption("本来は、福利厚生サービスの会員サイトに定期的にログインして、施設と料金プランを自動で集めます。"
               "MVP では見た目のみで、実際の登録は「一括登録」タブの CSV で行います。")
    # ① 取得の設定（操作はできない）
    col_source, col_schedule = st.columns([2, 1])
    col_source.text_input("取得元", "福利厚生サービスの会員サイト（URL とログイン情報を登録）", disabled=True)
    col_schedule.selectbox("自動取得の頻度", ["毎日 6:00"], disabled=True)
    st.button("今すぐ取得する（開発予定）", icon=":material/sync:", disabled=True)
    # ② 取得の履歴（見本）
    st.markdown("**取得の履歴**　:gray[（表示は見本です）]")
    st.dataframe(CRAWL_HISTORY_SAMPLE, hide_index=True, use_container_width=True)


def _render_import(user: User) -> None:
    """一括登録タブ。施設と料金プランを1つにまとめた CSV を選び、seed/load.py の取り込み処理で登録する。

    1行が料金プラン1件。同じ施設の行は施設の列をくり返す（menu_import.py が施設と料金プランに分ける）。
    取り込みのルールは seed/load.py をそのまま使う（同じ施設名は更新、なければ追加など）。
    """
    st.caption("施設と料金プランを1つにまとめた CSV を選んでください。1行が料金プラン1件で、同じ施設の行は施設の列をくり返します。"
               "料金プランの列（plan_ で始まる列）が空の行は、施設だけを登録します。"
               "同じ施設名の施設と、同じ施設の同じプラン名の料金プランは更新し、ないものは追加します。")
    st.download_button("見本の CSV をダウンロード", template_csv(), file_name="menus_plans_template.csv",
                       mime="text/csv", icon=":material/download:")
    data_file = st.file_uploader("施設・料金プランの CSV", type="csv", key="import_combined")
    if data_file is None:
        return
    _render_import_preview(user, data_file.getvalue())


def _render_import_preview(user: User, data: bytes) -> None:
    """選んだ CSV の確認の表示と、「取り込む」ボタン。"""
    # ① CSV を読み、必要な列があるか確かめる
    try:
        rows = read_csv_bytes(data)
    except UnicodeDecodeError:
        st.error("CSV は文字コード UTF-8 で保存してください（Excel では「CSV UTF-8」を選びます）")
        return
    missing = missing_columns(rows)
    if not rows or missing:
        st.error("CSV に必要な列がありません: " + ", ".join(missing or ["key", "area_code", "name", "category"]))
        return

    # ② 施設と料金プランに分ける。使わない列と、まとめるときの問題を知らせる
    dropped = [c for c in rows[0].keys() if c not in COMBINED_COLUMNS]
    menu_rows, plan_rows, problems = split_rows(rows)
    skipped = []
    for plan in plan_rows:
        reason = validate_plan(plan)
        if reason:
            skipped.append(f"- {plan['menu_key']}（{plan['name']}）: {reason}")
    col_menus, col_plans = st.columns(2)
    col_menus.metric("施設", f"{len(menu_rows)}件")
    col_plans.metric("料金プラン", f"{len(plan_rows) - len(skipped)}件")
    if dropped:
        st.info("次の列は取り込みに使いません: " + ", ".join(dropped))
    if problems or skipped:
        st.warning("次の行は、確認してください（ほかの行は取り込みます）。\n\n" + "\n".join([f"- {p}" for p in problems] + skipped))

    # ③ 取り込む（seed/load.py の処理を、ログインしている人の会社に対して呼ぶ）
    if st.button("取り込む", type="primary", icon=":material/upload:"):
        db = client().schema(SCHEMA)
        key_to_id = load_menus(db, user.tenant_id, rows=menu_rows)
        plan_count = load_plans(db, key_to_id, rows=plan_rows) if plan_rows else 0
        st.success(f"取り込みました（施設 {len(key_to_id)}件・料金プラン {plan_count}件）。「メニュー管理」タブで内容を確かめられます。")
