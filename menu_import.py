"""施設と料金プランを1つの CSV で一括登録するための変換（第10回MTG: 施設と料金で分かれている形を1つにまとめる）。

1行が料金プラン1件。同じ施設の行は、施設の列（key〜tags）をくり返して書く。料金プランの列が空の行は、施設だけを登録する。
変換した行は seed/load.py の load_menus・load_plans にそのまま渡せる。DBには触らない。
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

SEED = Path(__file__).resolve().parent / "seed"

# 施設の列（seed/menus.csv と同じ）と、料金プランの列（seed/plans.csv の menu_key 以外。plan_ を付けて区別する）
MENU_COLUMNS = ["key", "area_code", "name", "category", "address", "description", "usage_limit", "family_scope",
                "cancel_policy", "hotel_ref", "content_updated_at", "tags"]
PLAN_COLUMNS = ["name", "room_type", "meal", "grade", "adults", "children", "nights", "list_price", "benefit_price",
                "coupon_code", "member_url"]
COMBINED_COLUMNS = MENU_COLUMNS + [f"plan_{c}" for c in PLAN_COLUMNS]
REQUIRED_COLUMNS = ["key", "area_code", "name", "category"]


def read_csv_bytes(data: bytes) -> list[dict[str, str]]:
    """CSV ファイルの中身を、行（列名 → 文字）の一覧にする。Excel で保存した CSV の先頭の印（BOM）も読める。"""
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))


def split_rows(rows: list[dict[str, str]]) -> tuple[list[dict], list[dict], list[str]]:
    """1つの CSV の行を、施設の行・料金プランの行・問題の一覧に分ける。

    施設は key ごとに最初の行の値を使う。同じ key で施設の列の値が違う行があれば、問題として知らせる（最初の行を使う）。
    料金プランは plan_name が入っている行だけ。menu_key には その行の key を入れる。
    """
    menus: dict[str, dict] = {}
    plans: list[dict] = []
    problems: list[str] = []
    for line, row in enumerate(rows, start=2):  # 見出しを1行目として数える
        # ① 施設の列を取り出す。key がない行は飛ばす
        key = (row.get("key") or "").strip()
        if not key:
            problems.append(f"{line}行目: key が空のため飛ばしました")
            continue
        menu = {c: (row.get(c) or "").strip() for c in MENU_COLUMNS}
        if key not in menus:
            menus[key] = menu
        elif menus[key] != menu:
            problems.append(f"{line}行目: key {key} の施設の列が前の行と違います（前の行の値を使います）")
        # ② 料金プランの列があれば、料金プランの行にする
        plan = {c: (row.get(f"plan_{c}") or "").strip() for c in PLAN_COLUMNS}
        if plan["name"]:
            plans.append({"menu_key": key, **plan})
    return list(menus.values()), plans, problems


def missing_columns(rows: list[dict[str, str]]) -> list[str]:
    """必要な列のうち、CSV にないもの。"""
    present = set(rows[0].keys()) if rows else set()
    return [c for c in REQUIRED_COLUMNS if c not in present]


def template_csv() -> bytes:
    """見本の CSV（見本データの施設と料金プランを1つにまとめたもの）。Excel で開けるよう BOM 付きの UTF-8 にする。"""
    with open(SEED / "menus.csv", newline="", encoding="utf-8") as f:
        menus = list(csv.DictReader(f))
    with open(SEED / "plans.csv", newline="", encoding="utf-8") as f:
        plans = list(csv.DictReader(f))
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=COMBINED_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for menu in menus:
        base = {c: menu.get(c, "") for c in MENU_COLUMNS}
        own = [p for p in plans if p["menu_key"] == menu["key"]]
        for plan in own or [{}]:
            writer.writerow({**base, **{f"plan_{c}": plan.get(c, "") for c in PLAN_COLUMNS}})
    return out.getvalue().encode("utf-8-sig")
