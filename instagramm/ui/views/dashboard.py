"""Tela Dashboard: visão geral e atalhos."""
import customtkinter as ctk

from core import service
from ui import theme, widgets
from ui.views.base import BaseView


class DashboardView(BaseView):
    def __init__(self, master, app):
        super().__init__(master, app)
        widgets.title(self, "Dashboard", size=24).pack(anchor="w")
        widgets.subtitle(self, "Visão geral das suas contas e publicações").pack(anchor="w", pady=(0, 16))

        self.cards_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.cards_frame.pack(fill="x")
        for i in range(5):
            self.cards_frame.grid_columnconfigure(i, weight=1)
        self.stat_cards = {}
        specs = [
            ("connected", "Contas conectadas", theme.SUCCESS),
            ("loops_running", "Loops ativos", theme.PRIMARY),
            ("warming", "Aquecendo", theme.WARNING),
            ("posts_24h", "Posts (24h)", theme.ACCENT),
            ("scheduled_pending", "Agendados", theme.MUTED),
        ]
        for i, (key, label, color) in enumerate(specs):
            card = widgets.card(self.cards_frame, fg_color=theme.CARD)
            card.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 8, 0))
            value = ctk.CTkLabel(card, text="—", font=(theme.FONT, 30, "bold"), text_color=color)
            value.pack(anchor="w", padx=18, pady=(16, 0))
            ctk.CTkLabel(card, text=label, font=(theme.FONT, 12), text_color=theme.MUTED).pack(anchor="w", padx=18, pady=(0, 16))
            self.stat_cards[key] = value

        logcard = widgets.card(self)
        logcard.pack(fill="both", expand=True, pady=(16, 0))
        widgets.title(logcard, "Últimas publicações", size=15).pack(anchor="w", padx=18, pady=(14, 6))
        self.log_frame = ctk.CTkScrollableFrame(logcard, fg_color="transparent")
        self.log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 12))

    def on_show(self):
        self._reload()

    def refresh(self):
        self._reload()

    def _reload(self):
        self.app.run_async(service.dashboard_stats, on_done=self._render_stats)
        self.app.run_async(lambda: service.recent_logs(15), on_done=self._render_logs)

    def _render_stats(self, stats):
        self.stat_cards["connected"].configure(text=f"{stats['connected']}/{stats['accounts']}")
        self.stat_cards["loops_running"].configure(text=str(stats["loops_running"]))
        self.stat_cards["warming"].configure(text=str(stats.get("warming", 0)))
        self.stat_cards["posts_24h"].configure(text=str(stats["posts_24h"]))
        self.stat_cards["scheduled_pending"].configure(text=str(stats["scheduled_pending"]))

    def _render_logs(self, logs):
        for c in self.log_frame.winfo_children():
            c.destroy()
        if not logs:
            ctk.CTkLabel(self.log_frame, text="Nenhuma publicação ainda.", text_color=theme.MUTED).pack(pady=24)
            return
        for log in logs:
            row = ctk.CTkFrame(self.log_frame, fg_color=theme.CARD2, corner_radius=10)
            row.pack(fill="x", padx=6, pady=3)
            when = log["posted_at"].replace("T", " ")[:16] if log["posted_at"] else ""
            ctk.CTkLabel(row, text=f"{log['account']} · {when}", text_color=theme.TEXT, font=(theme.FONT, 12), anchor="w").pack(side="left", padx=12, pady=8, fill="x", expand=True)
            ok = log["status"] == "success"
            ctk.CTkLabel(row, text="OK" if ok else "ERRO", text_color=theme.SUCCESS if ok else theme.DANGER, font=(theme.FONT, 11, "bold")).pack(side="right", padx=12)
