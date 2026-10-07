"""CSVから施設・プラン・利用者・支出額をDBに入れる。

使い方（プロジェクト直下で）:
  python -m seed.load            # 4ファイルすべて
  python -m seed.load menus      # 個別
前提: sql/001_schema.sql・002_seed_tenant.sql・004_search.sql を実行済み（tags 列は 004 で追加）。利用者は Supabase Auth 側で同じメールのアカウントを先に作る。
接続情報は .streamlit/secrets.toml から読む（streamlitの外で動かすため自前で読む）。
"""
from __future__ import annotations

import csv
import sys
import tomllib
from pathlib import Path

from supabase import create_client

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "seed"
TENANT_CODE = "sample"


def client():
    """secrets.toml を読んで bts_app スキーマのクライアントを返す。"""
    secrets = tomllib.loads((ROOT / ".streamlit" / "secrets.toml").read_text(encoding="utf-8"))
    return create_client(secrets["supabase"]["url"], secrets["supabase"]["anon_key"]).schema("bts_app")


def read_csv(name: str) -> list[dict]:
    """seed/ のCSVを辞書のリストで読む。"""
    with open(SEED / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def blank_to_none(row: dict) -> dict:
    """空文字を None に変える。"""
    return {k: (None if v == "" else v) for k, v in row.items()}


def validate_plan(row: dict) -> str | None:
    """プラン1行の検証。問題があれば理由、なければ None。"""
    for k in ("list_price", "benefit_price"):
        if not str(row.get(k, "")).isdigit():
            return f"{k} が数値ではありません"
    if int(row["benefit_price"]) > int(row["list_price"]):
        return "福利厚生価格が元値を超えています"
    return None


def load_menus(c, tenant_id: str, rows: list[dict] | None = None) -> dict[str, str]:
    """menus.csv を投入し、key→id の対応表を返す。rows を渡すと、menus.csv の代わりにその行を投入する（管理画面の一括登録用）。"""
    # ① 共通エリアを code→id にする
    areas = {a["code"]: a["id"] for a in c.table("areas").select("id,code").is_("tenant_id", "null").execute().data}
    key_to_id: dict[str, str] = {}
    # ② 1行ずつ、施設名で既存を探して更新か追加。key→id の対応表を作る
    #    削除済み（deleted_at に値がある）施設は探さない。同じ名前の行は新しい施設として追加する（管理画面で削除した施設を入れ直せる）
    for row in (read_csv("menus.csv") if rows is None else rows):
        row = blank_to_none(row)
        key = row.pop("key")
        area_code = row.pop("area_code")
        row["area_id"] = areas.get(area_code)
        row["tenant_id"] = tenant_id
        row["matched"] = bool(row.get("hotel_ref"))
        row["tags"] = [t for t in (row.get("tags") or "").split("|") if t]
        existing = (c.table("menus").select("id").eq("tenant_id", tenant_id).eq("name", row["name"])
                    .is_("deleted_at", "null").limit(1).execute().data)
        if existing:
            c.table("menus").update(row).eq("id", existing[0]["id"]).execute()
            key_to_id[key] = existing[0]["id"]
        else:
            res = c.table("menus").insert(row).execute()
            key_to_id[key] = res.data[0]["id"]
    print(f"menus: {len(key_to_id)}件")
    return key_to_id


def load_plans(c, key_to_id: dict[str, str], rows: list[dict] | None = None) -> int:
    """plans.csv を検証して投入し、投入した件数を返す。rows を渡すと、plans.csv の代わりにその行を投入する（管理画面の一括登録用）。"""
    # ① 1行ずつ検証し、違反した行は飛ばして表示する
    n = 0
    for row in (read_csv("plans.csv") if rows is None else rows):
        row = blank_to_none(row)
        err = validate_plan(row)
        if err:
            print(f"  skip {row['menu_key']} {row['name']}: {err}")
            continue
        # ② 施設の key を id に変え、数値列を int にする
        menu_id = key_to_id.get(row.pop("menu_key"))
        if not menu_id:
            continue
        row["menu_id"] = menu_id
        for k in ("adults", "children", "nights", "list_price", "benefit_price"):
            if row.get(k) is not None:
                row[k] = int(row[k])
        # ③ プラン名で既存を探して更新か追加
        existing = c.table("plans").select("id").eq("menu_id", menu_id).eq("name", row["name"]).limit(1).execute().data
        if existing:
            c.table("plans").update(row).eq("id", existing[0]["id"]).execute()
        else:
            c.table("plans").insert(row).execute()
        n += 1
    print(f"plans: {n}件")
    return n


def load_users(c, tenant_id: str) -> None:
    """users.csv から利用者を入れる。auth_id（ログイン用アカウントとの紐づけ）は、あとで Table Editor で入れる。"""
    n = 0
    for row in read_csv("users.csv"):
        row = blank_to_none(row)
        email = row["email"]
        row["tenant_id"] = tenant_id
        existing = c.table("users").select("id").eq("tenant_id", tenant_id).eq("name", row["name"]).limit(1).execute().data
        if not existing:
            c.table("users").insert(row).execute()
            n += 1
        print(f"  {row['name']} <{email}> role={row['role']}")
    print(f"users: {n}件追加")


def load_spots(c) -> None:
    """spots.csv（周辺情報の見本）を入れる。全テナント共通（tenant_id なし）。同じエリア・名称があれば飛ばす。"""
    # ① エリアのコード→IDの対応を作る
    areas = {a["code"]: a["id"] for a in c.table("areas").select("id,code").is_("tenant_id", "null").execute().data}
    n = 0
    for row in read_csv("spots.csv"):
        area_id = areas.get(row["area_code"])
        if not area_id:
            print(f"  エリアが見つからないため飛ばす: {row['area_code']}"); continue
        # ② 同じエリア・名称がなければ追加する
        existing = c.table("spots").select("id").eq("area_id", area_id).eq("name", row["name"]).limit(1).execute().data
        if not existing:
            c.table("spots").insert({"area_id": area_id, "kind": row["kind"], "name": row["name"], "description": row["description"] or None, "url": row["url"] or None, "source": "seed"}).execute()
            n += 1
    print(f"spots: {n}件追加")


def load_spend(c, tenant_id: str) -> None:
    """spend.csv を期間で upsert する。"""
    for row in read_csv("spend.csv"):
        row["tenant_id"] = tenant_id
        row["amount"] = int(row["amount"]); row["headcount"] = int(row["headcount"])
        c.table("spend").upsert(row, on_conflict="tenant_id,period_start,period_end").execute()
    print("spend: 投入")


def main(targets: list[str]) -> None:
    """指定した対象（menus/plans/users/spend/spots）を順に投入する。指定なしなら全部。"""
    c = client()
    tenant = c.table("tenants").select("id").eq("code", TENANT_CODE).limit(1).execute().data
    if not tenant:
        sys.exit("テナントがありません。sql/002_seed_tenant.sql を先に実行してください")
    tid = tenant[0]["id"]
    if not targets or "menus" in targets or "plans" in targets:
        ids = load_menus(c, tid)
        if not targets or "plans" in targets:
            load_plans(c, ids)
    if not targets or "users" in targets:
        load_users(c, tid)
    if not targets or "spend" in targets:
        load_spend(c, tid)
    if not targets or "spots" in targets:
        load_spots(c)


if __name__ == "__main__":
    main(sys.argv[1:])
