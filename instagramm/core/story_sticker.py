"""Desenha o botão de link no Story (pílula + ícone PNG) — igual InstifyPro."""
from __future__ import annotations

import io
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from PIL import Image, ImageDraw, ImageFont

from core.config import BASE_DIR, IMAGE_EXTENSIONS, VIDEO_EXTENSIONS

STORY_W = 1080
STORY_H = 1920
STICKER_NORM_H = 0.068625
LINK_ICON_PATH = BASE_DIR / "assets" / "link-sticker.png"


def default_sticker_text(url: str) -> str:
    try:
        host = urlparse(url).hostname or ""
        if host.lower().startswith("www."):
            host = host[4:]
        return host.upper()[:60] if host else "LINK"
    except Exception:  # noqa: BLE001
        return "LINK"


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = (
        ["segoeuib.ttf", "arialbd.ttf", "Arial Bold.ttf"]
        if bold
        else ["segoeui.ttf", "arial.ttf", "Arial.ttf"]
    )
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _round_rect(draw: ImageDraw.ImageDraw, box: tuple, radius: int, fill: str | tuple) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def draw_link_sticker(
    img: Image.Image,
    *,
    url: str,
    text: str = "",
    x: float = 0.5,
    y: float = 0.8,
) -> dict[str, float]:
    """Queima pílula branca + ícone + texto. Retorna width/height normalizados."""
    W, H = img.size
    label = (text or default_sticker_text(url)).strip() or "LINK"
    box_h = max(52, int(STICKER_NORM_H * H))
    font_size = max(14, int(box_h * 0.38))
    icon_size = max(18, int(box_h * 0.52))
    pad_x = int(box_h * 0.42)
    gap = int(box_h * 0.14)
    radius = int(box_h * 0.28)

    font = _load_font(font_size, bold=True)
    draw = ImageDraw.Draw(img)

    try:
        text_w = int(draw.textlength(label, font=font))
    except Exception:  # noqa: BLE001
        text_w = len(label) * font_size // 2

    box_w = min(int(W * 0.88), pad_x + icon_size + gap + text_w + pad_x)
    cx = int(x * W)
    cy = int(y * H)
    left = cx - box_w // 2
    top = cy - box_h // 2
    mid_y = top + box_h // 2

    # sombra
    _round_rect(draw, (left + 2, top + 4, left + box_w + 2, top + box_h + 4), radius, (0, 0, 0, 72))
    # pílula
    _round_rect(draw, (left, top, left + box_w, top + box_h), radius, (255, 255, 255, 245))

    # ícone PNG
    icon_x = left + pad_x
    icon_y = mid_y - icon_size // 2
    if LINK_ICON_PATH.is_file():
        try:
            ic = Image.open(LINK_ICON_PATH).convert("RGBA")
            ic = ic.resize((icon_size, icon_size), Image.Resampling.LANCZOS)
            img.paste(ic, (icon_x, icon_y), ic)
        except Exception:  # noqa: BLE001
            draw.text((icon_x, mid_y), "🔗", fill="#111111", font=_load_font(icon_size), anchor="lm")
    else:
        draw.text((icon_x, mid_y), "🔗", fill="#111111", font=_load_font(icon_size), anchor="lm")

    # texto
    text_x = left + pad_x + icon_size + gap
    draw.text((text_x, mid_y), label, fill="#111111", font=font, anchor="lm")

    return {"width": box_w / W, "height": box_h / H}


def _letterbox_image(src: Path) -> Image.Image:
    img = Image.open(src).convert("RGB")
    canvas = Image.new("RGB", (STORY_W, STORY_H), (0, 0, 0))
    scale = min(STORY_W / img.width, STORY_H / img.height)
    dw = int(img.width * scale)
    dh = int(img.height * scale)
    resized = img.resize((dw, dh), Image.Resampling.LANCZOS)
    canvas.paste(resized, ((STORY_W - dw) // 2, (STORY_H - dh) // 2))
    return canvas


def prepare_story_image(
    media_path: str | Path,
    link: dict[str, Any] | None = None,
) -> tuple[Path, dict[str, float] | None]:
    """Gera JPEG 1080x1920 com sticker queimado (se link). Retorna path temp + geom."""
    src = Path(media_path)
    ext = src.suffix.lower()
    geom = None

    if ext in IMAGE_EXTENSIONS:
        img = _letterbox_image(src)
    elif ext in VIDEO_EXTENSIONS:
        from core.video_deps import make_video_thumbnail

        thumb = make_video_thumbnail(src)
        try:
            img = _letterbox_image(thumb)
        finally:
            if thumb.is_file():
                try:
                    thumb.unlink()
                except OSError:
                    pass
    else:
        raise ValueError(f"Formato não suportado: {ext}")

    if link and link.get("url"):
        geom = draw_link_sticker(
            img,
            url=str(link["url"]),
            text=str(link.get("text") or ""),
            x=float(link.get("x", 0.5)),
            y=float(link.get("y", 0.8)),
        )

    out = Path(tempfile.gettempdir()) / f"story_stamped_{src.stem}.jpg"
    img.save(out, "JPEG", quality=92)
    return out, geom


def link_dict_from_geom(
    url: str,
    *,
    text: str = "",
    x: float = 0.5,
    y: float = 0.8,
    width: float | None = None,
    height: float | None = None,
) -> dict[str, Any]:
    return {
        "url": url,
        "text": text,
        "x": x,
        "y": y,
        "width": width or 0.6,
        "height": height or STICKER_NORM_H,
    }
