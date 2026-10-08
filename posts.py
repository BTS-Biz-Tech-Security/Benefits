"""口コミ。総合の星・細分化した星・お得感の満足度・コメント・写真を保存し、施設ごとの一覧と集計を返す。

集計（件数・星の平均・お得感の満足の割合・項目ごとの星の平均）は、一覧の表示とランキングの品質・減点に使う。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional

from db import client, table
from models import SUB_RATINGS, Post, User

COMMENT_MAX = 200
PHOTO_TYPES = ("image/jpeg", "image/png")
PHOTO_MAX_BYTES = 5 * 1024 * 1024
PHOTO_BUCKET = "post-photos"
# お得感の満足度がこの値以上の口コミを「満足」として数える
DEAL_SATISFIED_MIN = 4
# 一覧・集計で読む列
POST_COLUMNS = "*, users(name, family)"


def validate(rating: int, comment: str, deal_rating: Optional[int] = None,
             sub_ratings: Optional[dict[str, int]] = None) -> Optional[str]:
    """入力の検証。問題があれば理由の文字列、なければ None。お得感と細分化した星は任意。"""
    if not 1 <= int(rating) <= 5:
        return "星を選んでください"
    if deal_rating is not None and not 1 <= int(deal_rating) <= 5:
        return "お得感は1〜5で選んでください"
    for key, value in (sub_ratings or {}).items():
        if key not in SUB_RATINGS or not 1 <= int(value) <= 5:
            return "項目ごとの星は1〜5で選んでください"
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


def create(user: User, menu_id: str, rating: int, comment: str, plan_id: Optional[str] = None,
           photo_url: Optional[str] = None, deal_rating: Optional[int] = None,
           sub_ratings: Optional[dict[str, int]] = None, used_at: Optional[str] = None) -> Optional[str]:
    """投稿を保存する。失敗時はエラー文字列。sub_ratings は {列名: 1〜5}（models.SUB_RATINGS の列だけ）。"""
    # ① 入力を検証する
    err = validate(rating, comment, deal_rating, sub_ratings)
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
        "deal_rating": int(deal_rating) if deal_rating is not None else None,
        "used_at": used_at,
        **{key: int(value) for key, value in (sub_ratings or {}).items()},
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
        table("posts").select(POST_COLUMNS)
        .eq("menu_id", menu_id).eq("hidden", False).is_("deleted_at", "null")
        .order("created_at", desc=True).execute().data
    )
    return [Post.from_row(r) for r in rows]


@dataclass
class Summary:
    count: int
    average: Optional[float]  # 総合の星の平均（小数1桁）
    deal_satisfaction: Optional[float] = None  # お得感が満足（DEAL_SATISFIED_MIN 以上）の割合（0〜1）。回答がなければ None
    deal_count: int = 0  # お得感に回答した件数
    sub_averages: dict[str, float] = field(default_factory=dict)  # 細分化した星の項目ごとの平均 {列名: 平均}。回答のある項目だけ


def summarize(ratings: list[int], deal_ratings: list[Optional[int]],
              sub_ratings: Optional[list[dict[str, int]]] = None) -> Summary:
    """星・お得感・細分化した星の一覧から集計を作る。DBに触らない（テストしやすいように分けている）。

    sub_ratings は口コミごとの {列名: 1〜5}（入力のある項目だけ）。項目ごとに、回答のある口コミだけで平均を出す。
    """
    # ① 0件なら平均なし
    if not ratings:
        return Summary(0, None)
    # ② 星の平均と、お得感が満足の割合
    answered = [d for d in deal_ratings if d is not None]
    satisfaction = round(sum(1 for d in answered if d >= DEAL_SATISFIED_MIN) / len(answered), 2) if answered else None
    # ③ 細分化した星の項目ごとの平均
    values: dict[str, list[int]] = {}
    for item in sub_ratings or []:
        for key, value in item.items():
            values.setdefault(key, []).append(int(value))
    sub_averages = {key: round(sum(v) / len(v), 1) for key, v in values.items()}
    return Summary(len(ratings), round(sum(ratings) / len(ratings), 1), satisfaction, len(answered), sub_averages)


def summary(posts: list[Post]) -> Summary:
    """施設の口コミ一覧の集計（件数・星の平均・お得感の満足の割合）。"""
    return summarize([p.rating for p in posts], [p.deal_rating for p in posts], [p.sub_ratings for p in posts])


def review_stats(menu_ids: list[str]) -> dict[str, Summary]:
    """施設ごとの集計 {施設ID: Summary}。口コミのない施設は含まれない。ランキングの品質・減点に使う。"""
    if not menu_ids:
        return {}
    rows = (table("posts").select("menu_id, rating, deal_rating, " + ", ".join(SUB_RATINGS)).in_("menu_id", menu_ids)
            .eq("hidden", False).is_("deleted_at", "null").execute().data)
    by_menu: dict[str, list[dict]] = {}
    for r in rows:
        by_menu.setdefault(r["menu_id"], []).append(r)
    return {menu_id: summarize([int(r["rating"]) for r in rs], [r.get("deal_rating") for r in rs],
                               [{k: r[k] for k in SUB_RATINGS if r.get(k) is not None} for r in rs])
            for menu_id, rs in by_menu.items()}


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
    rows = table("posts").select(POST_COLUMNS).eq("tenant_id", tenant_id).eq("hidden", False).is_("deleted_at", "null").order("created_at", desc=True).limit(limit).execute().data
    ids = list({r["menu_id"] for r in rows})
    names = {m["id"]: m["name"] for m in table("menus").select("id,name").in_("id", ids).execute().data} if ids else {}
    for r in rows:
        r["menu_name"] = names.get(r["menu_id"], "")
    return rows
