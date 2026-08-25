"""Preview 9:16 com sticker de link arrastável."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont, ImageTk

from core import story_sticker as ss
from ui import theme


class StoryLinkPreview(ctk.CTkFrame):
    """Canvas interativo: arraste o botão de link para posicionar."""

    PREVIEW_W = 270
    PREVIEW_H = 480

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=theme.CARD2, corner_radius=12, **kwargs)
        self.link_x = 0.5
        self.link_y = 0.8
        self.link_url = ""
        self.link_text = ""
        self._media_path: str | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._dragging = False

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(
            head, text="Preview do Story",
            font=(theme.FONT, 13, "bold"), text_color=theme.TEXT,
        ).pack(side="left")
        ctk.CTkLabel(
            head, text="Arraste o botão",
            font=(theme.FONT, 11), text_color=theme.MUTED,
        ).pack(side="right")

        wrap = ctk.CTkFrame(self, fg_color="#000", corner_radius=8)
        wrap.pack(padx=12, pady=(0, 10))
        self.canvas = tk.Canvas(
            wrap, width=self.PREVIEW_W, height=self.PREVIEW_H,
            bg="#000000", highlightthickness=0, bd=0,
        )
        self.canvas.pack()
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self._draw_placeholder()

    def _draw_placeholder(self):
        c = self.canvas
        c.delete("all")
        c.create_text(
            self.PREVIEW_W // 2, self.PREVIEW_H // 2,
            text="Selecione uma mídia\npara ver o preview",
            fill=theme.MUTED, font=(theme.FONT, 11), justify="center",
        )

    def set_media(self, path: str | None):
        self._media_path = path
        if not path or not Path(path).exists():
            self._photo = None
            self._draw_placeholder()
            return
        try:
            img = Image.open(path).convert("RGB")
            scale = min(self.PREVIEW_W / img.width, self.PREVIEW_H / img.height)
            dw = max(1, int(img.width * scale))
            dh = max(1, int(img.height * scale))
            img = img.resize((dw, dh), Image.Resampling.LANCZOS)
            bg = Image.new("RGB", (self.PREVIEW_W, self.PREVIEW_H), (0, 0, 0))
            bg.paste(img, ((self.PREVIEW_W - dw) // 2, (self.PREVIEW_H - dh) // 2))
            self._photo = ImageTk.PhotoImage(bg)
        except Exception:  # noqa: BLE001
            self._photo = None
            self._draw_placeholder()
            return
        self.redraw()

    def set_link(self, url: str, text: str = ""):
        self.link_url = (url or "").strip()
        self.link_text = (text or "").strip()
        self.redraw()

    def get_link_geom(self) -> dict:
        return {
            "url": self.link_url,
            "text": self.link_text,
            "x": round(self.link_x, 4),
            "y": round(self.link_y, 4),
            "width": 0.6,
            "height": ss.STICKER_NORM_H,
        }

    def redraw(self):
        c = self.canvas
        c.delete("all")
        if self._photo:
            c.create_image(0, 0, anchor="nw", image=self._photo)
        else:
            self._draw_placeholder()
            return

        if not self.link_url:
            c.create_text(
                self.PREVIEW_W // 2, self.PREVIEW_H - 24,
                text="Informe um link para ver o botão",
                fill=theme.MUTED, font=(theme.FONT, 10),
            )
            return

        label = self.link_text or ss.default_sticker_text(self.link_url)
        box_h = max(28, int(ss.STICKER_NORM_H * self.PREVIEW_H))
        font_size = max(10, int(box_h * 0.36))
        icon_size = max(14, int(box_h * 0.5))
        pad_x = int(box_h * 0.38)
        gap = int(box_h * 0.12)

        try:
            font = ImageFont.truetype("segoeuib.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()
        tmp = Image.new("RGBA", (400, 80), (0, 0, 0, 0))
        draw = ImageDraw.Draw(tmp)
        try:
            text_w = int(draw.textlength(label, font=font))
        except Exception:  # noqa: BLE001
            text_w = len(label) * font_size // 2
        box_w = min(int(self.PREVIEW_W * 0.88), pad_x + icon_size + gap + text_w + pad_x)

        cx = int(self.link_x * self.PREVIEW_W)
        cy = int(self.link_y * self.PREVIEW_H)
        left = cx - box_w // 2
        top = cy - box_h // 2

        c.create_rectangle(
            left + 2, top + 3, left + box_w + 2, top + box_h + 3,
            fill="#000000", outline="", stipple="gray50",
        )
        c.create_rectangle(
            left, top, left + box_w, top + box_h,
            fill="#ffffff", outline="#dddddd", width=1,
        )
        c.create_text(
            left + pad_x + icon_size // 2, top + box_h // 2,
            text="🔗", font=(theme.FONT, icon_size), fill="#111",
        )
        c.create_text(
            left + pad_x + icon_size + gap, top + box_h // 2,
            text=label[:28], anchor="w",
            font=(theme.FONT, font_size, "bold"), fill="#111111",
        )
        c.create_rectangle(left, top, left + box_w, top + box_h, outline=theme.PRIMARY, width=2, tags="sticker")

    def _on_press(self, event):
        if not self.link_url:
            return
        box_h = max(28, int(ss.STICKER_NORM_H * self.PREVIEW_H))
        label = self.link_text or ss.default_sticker_text(self.link_url)
        box_w = min(int(self.PREVIEW_W * 0.88), 180 + len(label) * 6)
        cx = int(self.link_x * self.PREVIEW_W)
        cy = int(self.link_y * self.PREVIEW_H)
        left = cx - box_w // 2
        top = cy - box_h // 2
        if left <= event.x <= left + box_w and top <= event.y <= top + box_h:
            self._dragging = True

    def _on_drag(self, event):
        if not self._dragging:
            return
        self.link_x = max(0.08, min(0.92, event.x / self.PREVIEW_W))
        self.link_y = max(0.08, min(0.92, event.y / self.PREVIEW_H))
        self.redraw()

    def _on_release(self, _event):
        self._dragging = False
