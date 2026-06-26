"""Gráficos simples desenhados em Canvas (sem dependências externas)."""
import tkinter as tk

import customtkinter as ctk

from ui import theme


class BarChart(ctk.CTkFrame):
    """Gráfico de barras verticais com rótulos por dia."""

    def __init__(self, master, title="", color=theme.PRIMARY, height=190, **kw):
        super().__init__(master, fg_color=theme.CARD, corner_radius=16, border_width=1, border_color=theme.BORDER, **kw)
        self.color = color
        self.data: list[dict] = []
        ctk.CTkLabel(self, text=title, font=(theme.FONT, 14, "bold"), text_color=theme.TEXT).pack(anchor="w", padx=16, pady=(12, 2))
        self.canvas = tk.Canvas(self, height=height, bg=theme.CARD, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.canvas.bind("<Configure>", lambda _e: self._redraw())

    def set_data(self, data, color=None):
        self.data = data or []
        if color:
            self.color = color
        self._redraw()

    def _redraw(self):
        c = self.canvas
        c.delete("all")
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 20 or h < 20:
            return
        if not self.data:
            c.create_text(w / 2, h / 2, text="sem dados ainda", fill=theme.MUTED, font=(theme.FONT, 11))
            return

        pad_l, pad_r, pad_b, pad_t = 10, 10, 22, 16
        n = len(self.data)
        maxv = max((d["value"] for d in self.data), default=0) or 1
        gap = 10
        bw = max(6, (w - pad_l - pad_r - gap * (n - 1)) / n)
        base = h - pad_b

        for i, d in enumerate(self.data):
            x0 = pad_l + i * (bw + gap)
            x1 = x0 + bw
            bh = (d["value"] / maxv) * (base - pad_t)
            y0 = base - bh
            color = self.color if d["value"] > 0 else theme.BORDER
            c.create_rectangle(x0, y0, x1, base, fill=color, outline="", width=0)
            if d["value"] > 0:
                c.create_text((x0 + x1) / 2, y0 - 8, text=str(d["value"]), fill=theme.TEXT, font=(theme.FONT, 9, "bold"))
            label = d.get("day") or d.get("label") or ""
            c.create_text((x0 + x1) / 2, base + 11, text=label, fill=theme.MUTED, font=(theme.FONT, 8))


class BreakdownChart(ctk.CTkFrame):
    """Barras horizontais (proporcionais) para totais por categoria."""

    def __init__(self, master, title="", **kw):
        super().__init__(master, fg_color=theme.CARD, corner_radius=16, border_width=1, border_color=theme.BORDER, **kw)
        ctk.CTkLabel(self, text=title, font=(theme.FONT, 14, "bold"), text_color=theme.TEXT).pack(anchor="w", padx=16, pady=(12, 6))
        self.rows = ctk.CTkFrame(self, fg_color="transparent")
        self.rows.pack(fill="both", expand=True, padx=16, pady=(0, 12))

    def set_data(self, items: list[tuple]):
        """items: lista de (label, valor, cor)."""
        for c in self.rows.winfo_children():
            c.destroy()
        if not items or all(v == 0 for _l, v, _c in items):
            ctk.CTkLabel(self.rows, text="sem dados ainda", text_color=theme.MUTED, font=(theme.FONT, 11)).pack(pady=18)
            return
        maxv = max((v for _l, v, _c in items), default=0) or 1
        for label, value, color in items:
            row = ctk.CTkFrame(self.rows, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=label, width=110, anchor="w", font=(theme.FONT, 11), text_color=theme.MUTED).pack(side="left")
            bar = ctk.CTkProgressBar(row, height=12, corner_radius=6, fg_color=theme.CARD2, progress_color=color)
            bar.pack(side="left", fill="x", expand=True, padx=(4, 8))
            bar.set(value / maxv)
            ctk.CTkLabel(row, text=str(value), width=40, anchor="e", font=(theme.FONT, 11, "bold"), text_color=theme.TEXT).pack(side="right")
