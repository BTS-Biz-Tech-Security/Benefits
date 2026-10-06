"""施設と料金プランの一括登録（CSV の取り込み）。管理画面の「一括登録（仮）」タブから使う。

仮置き: 実装ガイドでは一括登録は運用担当（seed/load.py）の役割で、このファイルはガイドにない。
取り込みのルールは seed/load.py とそろえている。
- 施設: 同じテナントで施設名が同じものは更新、なければ追加
- 料金プラン: menu_key で施設の CSV の key に結びつけ、同じ施設でプラン名が同じものは更新、なければ追加
画面からの操作で一部だけ入ると混乱しやすいので、エラーが1件でもあれば取り込まない（seed/load.py はエラー行を飛ばす）。

prepare_import() は DB を使わない（確認の表示とテストのため）。DB に触るのは load_existing() と run_import() だけ。
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Any, Optional

from db import table
from models import CATEGORIES
from search import rows_of

MENU_REQUIRED = ["key", "area_code", "name", "category"]
MENU_TEXT_COLUMNS = ["address", "description", "usage_limit", "family_scope", "cancel_policy", "hotel_ref", "content_updated_at"]
PLAN_REQUIRED = ["menu_key", "name", "list_price", "benefit_price"]
PLAN_TEXT_COLUMNS = ["room_type", "meal", "grade", "coupon_code", "member_url"]
PLAN_INT_COLUMNS = ["adults", "children", "nights"]


@dataclass
class MenuAction:
    """施設1行の取り込み。menu_id があれば更新、None なら追加。"""
    key: str
    menu_id: Optional[str]
    row: dict[str, Any]


@dataclass
class PlanAction:
    """料金プラン1行の取り込み。plan_id があれば更新、None なら追加。"""
    menu_key: str
    plan_id: Optional[str]
    row: dict[str, Any]


@dataclass
class ImportResult:
    menus: list[MenuAction] = field(default_factory=list)
    plans: list[PlanAction] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def count(self, kind: str, op: str) -> int:
        """kind は "menus" か "plans"、op は "update" か "insert"。"""
        if kind == "menus":
            ids = [a.menu_id for a in self.menus]
        else:
            ids = [a.plan_id for a in self.plans]
        if op == "update":
            return sum(1 for i in ids if i is not None)
        return sum(1 for i in ids if i is None)


def parse_csv(data: bytes) -> list[dict[str, str]]:
    """CSV ファイルの中身を、行（列名 → 文字）の一覧にする。Excel で保存した CSV の先頭の印（BOM）も読める。"""
    text = data.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def _text(value: Optional[str]) -> Optional[str]:
    """前後の空白を除き、空なら None（未設定）にする。"""
    value = (value or "").strip()
    return value or None


def _missing_columns(rows: list[dict[str, str]], required: list[str]) -> list[str]:
    columns = set(rows[0].keys()) if rows else set(required)
    return [c for c in required if c not in columns]


def prepare_import(menu_rows: list[dict[str, str]], plan_rows: list[dict[str, str]], area_ids: dict[str, str],
                   existing_menus: dict[str, str], existing_plans: dict[tuple[str, str], str]) -> ImportResult:
    """CSV の行を確かめ、施設と料金プランのそれぞれを「更新」か「追加」に振り分ける。DB は使わない。

    area_ids は {エリアのコード: id}、existing_menus は {施設名: 施設の id}（そのテナントのもの）、
    existing_plans は {(施設の id, プラン名): 料金プランの id}。行番号は見出しを1行目として数える。
    """
    result = ImportResult()

    # ① 必要な列がそろっているか
    missing = _missing_columns(menu_rows, MENU_REQUIRED)
    if missing:
        result.errors.append("施設の CSV に必要な列がありません: " + ", ".join(missing))
    missing_plan = _missing_columns(plan_rows, PLAN_REQUIRED) if plan_rows else []
    if missing_plan:
        result.errors.append("料金プランの CSV に必要な列がありません: " + ", ".join(missing_plan))
    if result.errors:
        return result

    # ② 施設: 1行ずつ確かめ、施設名で既存を探して更新か追加に振り分ける
    keys: set[str] = set()
    for i, raw in enumerate(menu_rows, start=2):
        key = (raw.get("key") or "").strip()
        name = _text(raw.get("name"))
        category = (raw.get("category") or "").strip()
        area_code = (raw.get("area_code") or "").strip()
        if not name:
            result.errors.append(f"施設 {i}行目: 施設名が空です")
            continue
        if area_code and area_code not in area_ids:
            result.errors.append(f"施設 {i}行目: エリア「{area_code}」がありません")
            continue
        if category not in CATEGORIES:
            result.errors.append(f"施設 {i}行目: カテゴリ「{category}」は stay・meal・leisure のどれかにしてください")
            continue
        if not key or key in keys:
            result.errors.append(f"施設 {i}行目: key「{key}」が重複しています" if key else f"施設 {i}行目: key が空です")
            continue
        keys.add(key)
        row: dict[str, Any] = {"name": name, "category": category, "area_id": area_ids.get(area_code)}
        for column in MENU_TEXT_COLUMNS:
            row[column] = _text(raw.get(column))
        row["tags"] = [t.strip() for t in (raw.get("tags") or "").split("|") if t.strip()]
        row["matched"] = bool(row["hotel_ref"])
        result.menus.append(MenuAction(key=key, menu_id=existing_menus.get(name), row=row))

    # ③ 料金プラン: 1行ずつ確かめ、施設とプラン名で既存を探して更新か追加に振り分ける
    menu_ids = {a.key: a.menu_id for a in result.menus}
    for i, raw in enumerate(plan_rows, start=2):
        menu_key = (raw.get("menu_key") or "").strip()
        name = _text(raw.get("name"))
        error = _plan_error(raw)
        if error:
            result.errors.append(f"料金プラン {i}行目: {error}")
            continue
        if menu_key not in menu_ids:
            result.errors.append(f"料金プラン {i}行目: menu_key「{menu_key}」が施設の CSV にありません")
            continue
        if not name:
            result.errors.append(f"料金プラン {i}行目: プラン名が空です")
            continue
        row = {"name": name, "list_price": int(raw["list_price"]), "benefit_price": int(raw["benefit_price"])}
        for column in PLAN_TEXT_COLUMNS:
            row[column] = _text(raw.get(column))
        for column in PLAN_INT_COLUMNS:
            value = _text(raw.get(column))
            row[column] = int(value) if value else None
        if row["nights"] is None:
            row["nights"] = 1  # 泊数の既定は1（DB の列の既定と同じ）
        menu_id = menu_ids[menu_key]
        plan_id = existing_plans.get((menu_id, name)) if menu_id else None
        result.plans.append(PlanAction(menu_key=menu_key, plan_id=plan_id, row=row))
    return result


def _plan_error(raw: dict[str, str]) -> Optional[str]:
    """料金プラン1行の金額と人数の確認（seed/load.py の validate_plan と同じ考え方）。問題がなければ None。"""
    for column in ("list_price", "benefit_price"):
        if not (raw.get(column) or "").strip().isdigit():
            return f"{column} が数値ではありません"
    if int(raw["benefit_price"]) > int(raw["list_price"]):
        return "福利厚生価格が定価を超えています"
    for column in PLAN_INT_COLUMNS:
        value = (raw.get(column) or "").strip()
        if value and not value.isdigit():
            return f"{column} が数値ではありません"
    return None


def load_existing(tenant_id: str) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    """そのテナントの既存の施設 {施設名: id} と、料金プラン {(施設の id, プラン名): id} を DB から読む。"""
    menus = rows_of(table("menus").select("id,name").eq("tenant_id", tenant_id).is_("deleted_at", "null"))
    existing_menus = {m["name"]: m["id"] for m in menus}
    existing_plans: dict[tuple[str, str], str] = {}
    if existing_menus:
        query = table("plans").select("id,menu_id,name").in_("menu_id", list(existing_menus.values())).is_("deleted_at", "null")
        for p in rows_of(query):
            existing_plans[(p["menu_id"], p["name"])] = p["id"]
    return existing_menus, existing_plans


def run_import(result: ImportResult, tenant_id: str) -> None:
    """振り分けた結果を DB に書き込む。施設 → 料金プランの順。更新はそのテナントのものだけ。"""
    # ① 施設を更新・追加し、key → 施設の id の対応表を作る
    key_to_id: dict[str, str] = {}
    for action in result.menus:
        row = dict(action.row, tenant_id=tenant_id)
        if action.menu_id:
            table("menus").update(row).eq("id", action.menu_id).eq("tenant_id", tenant_id).execute()
            key_to_id[action.key] = action.menu_id
        else:
            inserted = rows_of(table("menus").insert(row))
            key_to_id[action.key] = inserted[0]["id"]

    # ② 料金プランを更新・追加する
    for action in result.plans:
        menu_id = key_to_id[action.menu_key]
        row = dict(action.row, menu_id=menu_id)
        if action.plan_id:
            table("plans").update(row).eq("id", action.plan_id).eq("menu_id", menu_id).execute()
        else:
            table("plans").insert(row).execute()
