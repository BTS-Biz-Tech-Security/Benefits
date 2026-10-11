"""施設の代わりの画像（SVG）。写真がないときに、カテゴリの色とアイコンで代用する。"""
from __future__ import annotations

import base64
import html

COLORS = {"stay": ("#5B2D8E", "#EEE7F6"), "meal": ("#B3541E", "#FBEDE4"), "leisure": ("#0E7A55", "#E3F3EC")}
# 絵文字は端末で見え方が変わるため、単純な図形で描く
ICONS = {
    # ベッド
    "stay": '<rect x="-26" y="-6" width="52" height="18" rx="3" fill="{fg}"/><rect x="-26" y="-18" width="20" height="12" rx="3" fill="{fg}" opacity=".7"/><rect x="-28" y="12" width="4" height="10" fill="{fg}"/><rect x="24" y="12" width="4" height="10" fill="{fg}"/>',
    # 皿とフォーク
    "meal": '<circle cx="6" cy="0" r="18" fill="none" stroke="{fg}" stroke-width="4"/><circle cx="6" cy="0" r="8" fill="{fg}" opacity=".5"/><rect x="-26" y="-20" width="4" height="40" rx="2" fill="{fg}"/><rect x="-30" y="-20" width="12" height="12" rx="2" fill="none" stroke="{fg}" stroke-width="3"/>',
    # 旗（レジャー）
    "leisure": '<rect x="-20" y="-22" width="4" height="46" rx="2" fill="{fg}"/><path d="M-16,-20 L22,-12 L-16,-4 Z" fill="{fg}"/><circle cx="6" cy="14" r="8" fill="none" stroke="{fg}" stroke-width="3"/>',
}


def svg(name: str, category: str, width: int = 320, height: int = 180) -> str:
    """施設名とカテゴリからSVG文字列を作る。"""
    fg, bg = COLORS.get(category, ("#6B6472", "#F1EFF3"))
    icon = ICONS.get(category, '<circle r="14" fill="{fg}"/>').replace("{fg}", fg)
    label = html.escape(name if len(name) <= 12 else name[:11] + "…")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<rect width="{width}" height="{height}" rx="10" fill="{bg}"/>'
        f'<g transform="translate({width/2},{height/2-14})">{icon}</g>'
        f'<text x="{width/2}" y="{height/2+40}" font-size="13" font-family="sans-serif" fill="{fg}" text-anchor="middle">{label}</text>'
        f'</svg>'
    )


def data_url(name: str, category: str, **kw) -> str:
    """st.image に渡せる data URL。"""
    b = base64.b64encode(svg(name, category, **kw).encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b}"


def image_url(photo_url: str | None, name: str, category: str, **kw) -> str:
    """写真URLがあればそれ、なければ代わりの画像。"""
    return photo_url or data_url(name, category, **kw)