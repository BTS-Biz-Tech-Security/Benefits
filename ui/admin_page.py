"""管理画面（人事・経営のみ）。メニュー管理、一括登録と、開発予定の2タブ（利用の記録・社内ツール連携）。"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Optional

import streamlit as st

from db import SCHEMA, client, table
from models import CATEGORIES, MENU_COLUMNS, Menu, User
from search import rows_of
from seed.load import load_menus, load_plans, validate_plan
from session import require_role

UNSELECTED = "（選択）"


def render() -> None:
    """管理画面。app.py から呼ばれる（メニューに出るのは人事・経営の人だけ）。"""
    user = require_role("hr", "executive")
    tab_menu, tab_import, tab_usage, tab_notify = st.tabs(
        [":material/edit_note: メニュー管理", ":material/upload_file: 一括登録",
         ":material/bar_chart: 利用の記録（開発予定）", ":material/notifications: 社内ツール連携（開発予定）"])
    with tab_menu:
        _render_menus(user)
    with tab_import:
        _render_import(user)
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
    st.caption("削除すると、検索結果・1日プラン・この一覧に出なくなります。データは消さずに残すので、"
               "戻すときは運用担当に DB の deleted_at を空にしてもらってください。削除した施設は、一括登録しても戻りません。")
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


# 一括登録で、施設の CSV に必要な列（seed/load.py の load_menus() が使う列）
IMPORT_MENU_COLUMNS = ["key", "area_code", "name", "category"]
# 一括登録で受け付ける列（seed/menus.csv・seed/plans.csv の列と同じ）。これ以外の列は捨ててから seed/load.py に渡す。
# seed/load.py は列をそのまま DB に書くので、id・deleted_at などの列が紛れ込むと、その値まで書き換わってしまうため
ALLOWED_MENU_COLUMNS = ["key", "area_code", "name", "category", "address", "description", "usage_limit", "family_scope",
                        "cancel_policy", "hotel_ref", "content_updated_at", "tags"]
ALLOWED_PLAN_COLUMNS = ["menu_key", "name", "room_type", "meal", "grade", "adults", "children", "nights", "list_price",
                        "benefit_price", "coupon_code", "member_url"]


def _render_import(user: User) -> None:
    """一括登録タブ。施設と料金プランの CSV を選び、seed/load.py の取り込み処理で登録する。

    取り込みのルールは seed/load.py をそのまま使う（同じ施設名は更新、なければ追加など）。
    """
    st.caption("seed/menus.csv・seed/plans.csv と同じ列の CSV を選んでください。取り込みは seed/load.py と同じ処理で、"
               "同じ施設名の施設と、同じ施設の同じプラン名の料金プランは更新し、ないものは追加します。")
    menus_file = st.file_uploader("施設の CSV（必須）", type="csv", key="import_menus")
    plans_file = st.file_uploader("料金プランの CSV（任意）", type="csv", key="import_plans")
    if menus_file is None:
        return
    _render_import_preview(user, menus_file.getvalue(), plans_file.getvalue() if plans_file else None)


def _keep_allowed(rows: list[dict[str, str]], allowed: list[str]) -> tuple[list[dict[str, str]], list[str]]:
    """受け付ける列だけを残した行と、捨てた列の名前を返す。"""
    dropped = [c for c in (rows[0].keys() if rows else []) if c not in allowed]
    kept = [{c: v for c, v in row.items() if c in allowed} for row in rows]
    return kept, dropped


def _read_csv(data: bytes) -> list[dict[str, str]]:
    """選ばれた CSV ファイルの中身を、行（列名 → 文字）の一覧にする。Excel で保存した CSV の先頭の印（BOM）も読める。"""
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))


def _render_import_preview(user: User, menus_data: bytes, plans_data: Optional[bytes]) -> None:
    """選んだ CSV の確認の表示と、「取り込む」ボタン。"""
    # ① CSV を読む
    try:
        menu_rows = _read_csv(menus_data)
        plan_rows = _read_csv(plans_data) if plans_data else []
    except UnicodeDecodeError:
        st.error("CSV は文字コード UTF-8 で保存してください（Excel では「CSV UTF-8」を選びます）")
        return

    # ② 受け付ける列だけを残す（それ以外の列で DB の値が書き換わらないように）
    menu_rows, dropped_menu = _keep_allowed(menu_rows, ALLOWED_MENU_COLUMNS)
    plan_rows, dropped_plan = _keep_allowed(plan_rows, ALLOWED_PLAN_COLUMNS)

    # ③ 施設の CSV に必要な列があるか（足りないと seed/load.py が途中で止まるので、取り込む前に確かめる）
    missing = [c for c in IMPORT_MENU_COLUMNS if menu_rows and c not in menu_rows[0]]
    if not menu_rows or missing:
        st.error("施設の CSV に必要な列がありません: " + ", ".join(missing or IMPORT_MENU_COLUMNS))
        return

    # ④ 確認の表示。使わない列と、seed/load.py と同じ決まりで取り込まれない料金プランの行を先に知らせる
    keys = {row.get("key") for row in menu_rows}
    skipped = []
    for i, row in enumerate(plan_rows, start=2):  # 見出しを1行目として数える
        reason = validate_plan(row)
        if reason is None and row.get("menu_key") not in keys:
            reason = "menu_key が施設の CSV にありません"
        if reason:
            skipped.append(f"- {i}行目（{row.get('name') or '名前なし'}）: {reason}")
    col_menus, col_plans = st.columns(2)
    col_menus.metric("施設", f"{len(menu_rows)}行")
    col_plans.metric("料金プラン", f"{len(plan_rows) - len(skipped)}行")
    if dropped_menu or dropped_plan:
        st.info("次の列は取り込みに使いません: " + ", ".join(dropped_menu + dropped_plan))
    if skipped:
        st.warning("次の料金プランの行は取り込まれません（ほかの行は取り込みます）。\n\n" + "\n".join(skipped))

    # ⑤ 取り込む（seed/load.py の処理を、ログインしている人の会社に対して呼ぶ）
    if st.button("取り込む", type="primary", icon=":material/upload:"):
        db = client().schema(SCHEMA)
        key_to_id = load_menus(db, user.tenant_id, rows=menu_rows)
        plan_count = load_plans(db, key_to_id, rows=plan_rows) if plan_rows else 0
        st.success(f"取り込みました（施設 {len(key_to_id)}件・料金プラン {plan_count}件）。「メニュー管理」タブで内容を確かめられます。")
