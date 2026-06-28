"""Tela Logs: eventos do sistema (inclui aquecimento) e publicações."""
import customtkinter as ctk

from core import service
from ui import theme, widgets
from ui.views.base import BaseView

LEVEL_COLORS = {
    "success": theme.SUCCESS,
    "error": theme.DANGER,
    "warm": theme.WARNING,
    "warning": theme.WARNING,
    "info": theme.ACCENT,
}


class LogsView(BaseView):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.mode = "events"

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x")
        widgets.title(head, "Logs", size=24).pack(side="left")
        widgets.ghost_button(head, "Atualizar", self._reload, width=120).pack(side="right")
        widgets.subtitle(self, "Tudo que acontece no sistema — conexões, posts, aquecimento e erros").pack(anchor="w", pady=(0, 12))

        self.seg = ctk.CTkSegmentedButton(
            self, values=["Eventos (tudo)", "Publicações"], command=self._on_mode,
            fg_color=theme.CARD2, selected_color=theme.PRIMARY, selected_hover_color=theme.PRIMARY_HOVER,
            unselected_color=theme.CARD2, text_color=theme.TEXT,
        )
        self.seg.set("Eventos (tudo)")
        self.seg.pack(anchor="w", pady=(0, 12))

        card = widgets.card(self)
        card.pack(fill="both", expand=True)
        self.list_frame = ctk.CTkScrollableFrame(card, fg_color="transparent")
        self.list_frame.pack(fill="both", expand=True, padx=10, pady=12)

    def on_show(self):
        self._reload()

    def refresh(self):
        self._reload()

    def _on_mode(self, value):
        self.mode = "events" if value.startswith("Eventos") else "posts"
        self._reload()

    def _reload(self):
        if self.mode == "events":
            self.app.run_async(lambda: service.recent_events(120), on_done=self._render_events)
        else:
            self.app.run_async(lambda: service.recent_logs(80), on_done=self._render_posts)

    def _clear(self):
        for c in self.list_frame.winfo_children():
            c.destroy()

    def _render_events(self, events):
        self._clear()
        if not events:
            ctk.CTkLabel(self.list_frame, text="Nenhum evento ainda.", text_color=theme.MUTED).pack(pady=30)
            return
        for ev in events:
            color = LEVEL_COLORS.get(ev["level"], theme.MUTED)
            row = ctk.CTkFrame(self.list_frame, fg_color=theme.CARD2, corner_radius=10)
            row.pack(fill="x", padx=6, pady=4)
            ctk.CTkLabel(row, text="●", text_color=color, font=(theme.FONT, 14, "bold")).pack(side="left", padx=(12, 6), pady=8)
            info = ctk.CTkFrame(row, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True, pady=6)
            when = ev["created_at"].replace("T", " ")[:16] if ev["created_at"] else ""
            head = ev["account"] + "  ·  " + when if ev["account"] else when
            ctk.CTkLabel(info, text=head, text_color=theme.MUTED, font=(theme.FONT, 11), anchor="w").pack(anchor="w")
            ctk.CTkLabel(info, text=ev["message"], text_color=theme.TEXT, font=(theme.FONT, 12),
                         anchor="w", justify="left", wraplength=700).pack(anchor="w")

    def _render_posts(self, logs):
        self._clear()
        if not logs:
            ctk.CTkLabel(self.list_frame, text="Nenhuma publicação ainda.", text_color=theme.MUTED).pack(pady=30)
            return
        for log in logs:
            row = ctk.CTkFrame(self.list_frame, fg_color=theme.CARD2, corner_radius=10)
            row.pack(fill="x", padx=6, pady=4)
            info = ctk.CTkFrame(row, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True, padx=12, pady=8)
            when = log["posted_at"].replace("T", " ")[:16] if log["posted_at"] else ""
            ctk.CTkLabel(info, text=f"{log['account']} · {log['media_type']} · {when}", text_color=theme.TEXT, font=(theme.FONT, 12, "bold"), anchor="w").pack(anchor="w")
            detail = log["caption"][:80] if log["status"] == "success" else log["error"]
            if detail:
                color = theme.MUTED if log["status"] == "success" else theme.DANGER
                ctk.CTkLabel(info, text=detail, text_color=color, font=(theme.FONT, 11), anchor="w", wraplength=620, justify="left").pack(anchor="w")
            ok = log["status"] == "success"
            ctk.CTkLabel(row, text="OK" if ok else "ERRO", text_color="#fff" if ok else theme.DANGER,
                         fg_color=theme.SUCCESS if ok else "transparent", corner_radius=8, width=52,
                         font=(theme.FONT, 11, "bold")).pack(side="right", padx=12)
