"""アプリで扱うデータの型。DBの行（dict）から作り、画面と処理の間で受け渡す。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

# 種別の固定値（DBの説明列と揃える）
CATEGORIES = {"stay": "宿泊", "meal": "食事", "leisure": "レジャー"}
ROLES = {"employee": "従業員", "hr": "人事", "executive": "経営"}
# 口コミの細分化した星（列名: 表示名）。楽天トラベルの評価項目に合わせる。カテゴリに合わない項目は使わない
SUB_RATINGS = {"rating_service": "サービス", "rating_location": "立地", "rating_room": "部屋",
               "rating_equipment": "設備・アメニティ", "rating_bath": "風呂", "rating_meal": "食事"}
SUB_RATINGS_BY_CATEGORY = {
    "stay": list(SUB_RATINGS),
    "leisure": ["rating_service", "rating_location", "rating_equipment"],
    "meal": ["rating_service", "rating_location", "rating_meal"],
}
ACTIVITY_KINDS = {"login": "ログイン", "coupon": "クーポン使用", "click": "予約ページを開いた"}

# menus を読むときの列。embedding（ベクトル）は大きいので画面用には読まない
MENU_COLUMNS = ("id,tenant_id,name,category,area_id,address,description,photo_url,procedure,usage_limit,family_scope,"
                "cancel_policy,max_people,hotel_ref,matched,content_updated_at,tags,external_rating,external_review_count")


@dataclass
class User:
    id: str
    tenant_id: str
    name: str
    role: str = "employee"
    department: Optional[str] = None

    @classmethod
    def from_row(cls, r: dict[str, Any]) -> "User":
        return cls(id=r["id"], tenant_id=r["tenant_id"], name=r["name"], role=r.get("role", "employee"), department=r.get("department"))

    def is_admin(self) -> bool:
        return self.role in ("hr", "executive")


@dataclass
class Area:
    id: str
    code: str
    name: str

    @classmethod
    def from_row(cls, r: dict[str, Any]) -> "Area":
        return cls(id=r["id"], code=r["code"], name=r["name"])


@dataclass
class Plan:
    id: str
    menu_id: str
    name: str
    list_price: int
    benefit_price: int
    nights: int = 1
    adults: Optional[int] = None
    children: Optional[int] = None
    room_type: Optional[str] = None
    meal: Optional[str] = None
    grade: Optional[str] = None
    coupon_code: Optional[str] = None
    member_url: Optional[str] = None

    @classmethod
    def from_row(cls, r: dict[str, Any]) -> "Plan":
        return cls(
            id=r["id"], menu_id=r["menu_id"], name=r["name"],
            list_price=int(r["list_price"]), benefit_price=int(r["benefit_price"]),
            nights=int(r.get("nights") or 1), adults=r.get("adults"), children=r.get("children"),
            room_type=r.get("room_type"), meal=r.get("meal"), grade=r.get("grade"),
            coupon_code=r.get("coupon_code"), member_url=r.get("member_url"),
        )


@dataclass
class Menu:
    id: str
    tenant_id: str
    name: str
    category: str
    area_id: Optional[str] = None
    address: Optional[str] = None
    description: Optional[str] = None
    procedure: Optional[str] = None
    usage_limit: Optional[str] = None
    family_scope: Optional[str] = None
    cancel_policy: Optional[str] = None
    max_people: Optional[int] = None
    hotel_ref: Optional[str] = None
    matched: bool = False
    photo_url: Optional[str] = None
    content_updated_at: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    external_rating: Optional[float] = None  # 外部サイト（楽天トラベル）の星の平均。宿以外は空
    external_review_count: Optional[int] = None  # 外部サイトの口コミ件数
    plans: list[Plan] = field(default_factory=list)
    # 検索のときだけ入る値（DBの列ではない）。並べ替えに使う
    keyword_hits: int = 0
    similarity: Optional[float] = None

    @classmethod
    def from_row(cls, r: dict[str, Any]) -> "Menu":
        return cls(
            id=r["id"], tenant_id=r["tenant_id"], name=r["name"], category=r["category"],
            area_id=r.get("area_id"), address=r.get("address"), description=r.get("description"),
            procedure=r.get("procedure"), usage_limit=r.get("usage_limit"), family_scope=r.get("family_scope"),
            cancel_policy=r.get("cancel_policy"), max_people=r.get("max_people"),
            hotel_ref=r.get("hotel_ref"), matched=bool(r.get("matched", False)), photo_url=r.get("photo_url"), content_updated_at=r.get("content_updated_at"),
            tags=list(r.get("tags") or []),
            external_rating=float(r["external_rating"]) if r.get("external_rating") is not None else None,
            external_review_count=r.get("external_review_count"),
        )


@dataclass
class MarketPrice:
    menu_id: str
    checkin: date
    nights: int
    adults: int
    price: int
    source: str
    fetched_at: datetime
    children: int = 0
    meal: Optional[str] = None
    source_url: Optional[str] = None

    @classmethod
    def from_row(cls, r: dict[str, Any]) -> "MarketPrice":
        return cls(
            menu_id=r["menu_id"], checkin=date.fromisoformat(str(r["checkin"])), nights=int(r["nights"]),
            adults=int(r["adults"]), children=int(r.get("children") or 0), meal=r.get("meal"),
            price=int(r["price"]), source=r["source"], source_url=r.get("source_url"),
            fetched_at=datetime.fromisoformat(str(r["fetched_at"]).replace("Z", "+00:00")),
        )


@dataclass
class Post:
    id: str
    menu_id: str
    user_id: str
    rating: int
    comment: Optional[str]
    created_at: datetime
    user_name: str = ""
    photo_url: Optional[str] = None
    deal_rating: Optional[int] = None  # お得感の満足度（1〜5）
    sub_ratings: dict[str, int] = field(default_factory=dict)  # 細分化した星 {列名: 1〜5}。入力のある項目だけ
    used_at: Optional[str] = None  # 利用時期（YYYY-MM-DD）
    user_family: str = ""  # 投稿者の属性（users.family）

    @classmethod
    def from_row(cls, r: dict[str, Any]) -> "Post":
        user = r.get("users") if isinstance(r.get("users"), dict) else {}
        return cls(
            id=r["id"], menu_id=r["menu_id"], user_id=r["user_id"], rating=int(r["rating"]),
            comment=r.get("comment"), created_at=datetime.fromisoformat(str(r["created_at"]).replace("Z", "+00:00")),
            user_name=user.get("name") or "", photo_url=r.get("photo_url"),
            deal_rating=int(r["deal_rating"]) if r.get("deal_rating") is not None else None,
            sub_ratings={k: int(r[k]) for k in SUB_RATINGS if r.get(k) is not None},
            used_at=str(r["used_at"]) if r.get("used_at") else None,
            user_family=user.get("family") or "",
        )
