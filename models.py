"""アプリで扱うデータの型。DBの行（dict）から作り、画面と処理の間で受け渡す。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

# 種別の固定値（DBの説明列と揃える）
CATEGORIES = {"stay": "宿泊", "meal": "食事", "leisure": "レジャー"}
ROLES = {"employee": "従業員", "hr": "人事", "executive": "経営"}
ACTIVITY_KINDS = {"login": "ログイン", "coupon": "クーポン使用", "click": "予約ページを開いた"}

# menus を読むときの列。embedding（ベクトル）は大きいので画面用には読まない
MENU_COLUMNS = ("id,tenant_id,name,category,area_id,address,description,photo_url,procedure,usage_limit,family_scope,"
                "cancel_policy,max_people,hotel_ref,matched,content_updated_at,tags")


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

    @classmethod
    def from_row(cls, r: dict[str, Any]) -> "Post":
        return cls(
            id=r["id"], menu_id=r["menu_id"], user_id=r["user_id"], rating=int(r["rating"]),
            comment=r.get("comment"), created_at=datetime.fromisoformat(str(r["created_at"]).replace("Z", "+00:00")),
            user_name=(r.get("users") or {}).get("name", "") if isinstance(r.get("users"), dict) else "",
            photo_url=r.get("photo_url"),
        )
