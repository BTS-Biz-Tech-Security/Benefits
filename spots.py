"""周辺スポットの取得。クローリングで集めた食事・レジャーを、詳細画面と1日プランで使う。"""
from __future__ import annotations

from typing import Optional

from db import table


def spots_by_area(area_id: Optional[str], tenant_id: Optional[str] = None) -> list[dict]:
    """エリアの周辺スポット（共通のものと、そのテナントのもの）を種類・名前順で返す。"""
    if not area_id:
        return []
    query = table("spots").select("*").eq("area_id", area_id)
    if tenant_id:
        query = query.or_(f"tenant_id.is.null,tenant_id.eq.{tenant_id}")
    else:
        query = query.is_("tenant_id", "null")
    return query.order("kind").order("name").execute().data
