"""口コミ。星・コメント・写真を保存し、施設ごとの一覧と件数・平均を返す。"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from db import client, table
from models import Post, User

COMMENT_MAX = 200
PHOTO_TYPES = ("image/jpeg", "image/png")
PHOTO_MAX_BYTES = 5 * 1024 * 1024
PHOTO_BUCKET = "post-photos"


def validate(rating: int, comment: str) -> Optional[str]:
    """入力の検証。問題があれば理由の文字列、なければ None。"""
    if not 1 <= int(rating) <= 5:
        return "星を選んでください"
    if len(comment or "") > COMMENT_MAX:
        return f"コメントは{COMMENT_MAX}文字までにしてください"
    return None


def validate_photo(content_type: str, size: int) -> Optional[str]:
    """写真の検証。形式は JPEG / PNG、大きさは 5MB まで。"""
    if content_type not in PHOTO_TYPES:
        return "写真は JPEG か PNG にしてください"
    if size > PHOTO_MAX_BYTES:
        return "写真は 5MB までにしてください"
    return None


def upload_photo(user: User, data: bytes, content_type: str) -> str:
    """写真を Supabase Storage（公開バケット post-photos）に保存してURLを返す。"""
    # ① テナント・利用者ごとのフォルダに一意な名前で置く
    ext = "png" if content_type == "image/png" else "jpg"
    path = f"{user.tenant_id}/{user.id}/{uuid.uuid4().hex}.{ext}"
    storage = client().storage.from_(PHOTO_BUCKET)
    storage.upload(path, data, {"content-type": content_type})
    return storage.get_public_url(path)


def create(user: User, menu_id: str, rating: int, comment: str, plan_id: Optional[str] = None, photo_url: Optional[str] = None) -> Optional[str]:
    """投稿を保存する。失敗時はエラー文字列。"""
    # ① 入力を検証する
    err = validate(rating, comment)
    if err:
        return err
    # ② 保存する行を組み立てる（コメントの空文字は None）
    row = {
        "tenant_id": user.tenant_id,
        "user_id": user.id,
        "menu_id": menu_id,
        "plan_id": plan_id,
        "rating": int(rating),
        "comment": (comment or "").strip() or None,
        "photo_url": photo_url,
    }
    # ③ 保存する。失敗は文字列で返す
    try:
        table("posts").insert(row).execute()
    except Exception as e:
        return f"投稿を保存できませんでした: {e}"
    return None


def list_by_menu(menu_id: str) -> list[Post]:
    """施設の投稿一覧（非表示・削除済みを除く、新しい順、投稿者名つき）。"""
    # ① 非表示・削除済みを除き、投稿者名を結合して新しい順に取る
    rows = (
        table("posts").select("*, users(name)")
        .eq("menu_id", menu_id).eq("hidden", False).is_("deleted_at", "null")
        .order("created_at", desc=True).execute().data
    )
    return [Post.from_row(r) for r in rows]


@dataclass
class Summary:
    count: int
    average: Optional[float]


def summary(posts: list[Post]) -> Summary:
    """件数と星の平均。"""
    # ① 0件なら平均なし、それ以外は星の平均（小数1桁）
    if not posts:
        return Summary(0, None)
    return Summary(len(posts), round(sum(p.rating for p in posts) / len(posts), 1))


def rating_summary(menu_ids: list[str]) -> dict[str, tuple[int, float]]:
    """施設ごとの口コミ件数と平均。一覧の表示と評価順の並び替えに使う。"""
    if not menu_ids:
        return {}
    rows = table("posts").select("menu_id, rating").in_("menu_id", menu_ids).eq("hidden", False).is_("deleted_at", "null").execute().data
    acc: dict[str, list[int]] = {}
    for r in rows:
        acc.setdefault(r["menu_id"], []).append(int(r["rating"]))
    return {k: (len(v), round(sum(v) / len(v), 1)) for k, v in acc.items()}


def recent_posts(tenant_id: str, limit: int = 3) -> list[dict]:
    """最近の口コミ（施設名つき）。検索前の画面に出す。"""
    rows = table("posts").select("*, users(name)").eq("tenant_id", tenant_id).eq("hidden", False).is_("deleted_at", "null").order("created_at", desc=True).limit(limit).execute().data
    ids = list({r["menu_id"] for r in rows})
    names = {m["id"]: m["name"] for m in table("menus").select("id,name").in_("id", ids).execute().data} if ids else {}
    for r in rows:
        r["menu_name"] = names.get(r["menu_id"], "")
    return rows
