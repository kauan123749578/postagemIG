"""Tela Dashboard: visão geral, gráficos e últimas publicações."""
import customtkinter as ctk

from core import service
from ui import theme, widgets
from ui.charts import BarChart, BreakdownChart
from ui.views.base import BaseView

BREAKDOWN_SPECS = [
    ("like", "Curtidas", theme.DANGER),
    ("comment", "Comentários", theme.ACCENT),
    ("follow", "Seguir", theme.SUCCESS),
    ("unfollow", "Deixar de seguir", theme.WARNING),
    ("story_view", "Stories vistos", theme.PRIMARY),
    ("story_like", "Stories curtidos", theme.PINK),
    ("save", "Salvos", theme.MUTED),
    ("scroll", "Rolagens", theme.ACCENT),
]


class DashboardView(BaseView):
    def __init__(self, master, app):
        super().__init__(master, app)
        widgets.title(self, "Dashboard", size=24).pack(anchor="w")
        widgets.subtitle(self, "Visão geral, gráficos e atividade das suas contas").pack(anchor="w", pady=(0, 14))

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True)

        # cards de estatística
        self.cards_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
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
            value = ctk.CTkLabel(card, text="—", font=(theme.FONT, 28, "bold"), text_color=color)
            value.pack(anchor="w", padx=16, pady=(14, 0))
            ctk.CTkLabel(card, text=label, font=(theme.FONT, 11), text_color=theme.MUTED).pack(anchor="w", padx=16, pady=(0, 14))
            self.stat_cards[key] = value

        # gráficos
        charts = ctk.CTkFrame(self.scroll, fg_color="transparent")
        charts.pack(fill="x", pady=(16, 0))
        charts.grid_columnconfigure(0, weight=1)
        charts.grid_columnconfigure(1, weight=1)
        charts.grid_columnconfigure(2, weight=1)
        self.chart_posts = BarChart(charts, "Publicações (7 dias)", color=theme.ACCENT)
        self.chart_posts.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.chart_warm = BarChart(charts, "Ações de aquecimento (7 dias)", color=theme.PRIMARY)
        self.chart_warm.grid(row=0, column=1, sticky="nsew", padx=8)
        self.chart_errors = BarChart(charts, "Erros (7 dias)", color=theme.DANGER)
        self.chart_errors.grid(row=0, column=2, sticky="nsew", padx=(8, 0))

        # breakdown + logs
        bottom = ctk.CTkFrame(self.scroll, fg_color="transparent")
        bottom.pack(fill="both", expand=True, pady=(16, 0))
        bottom.grid_columnconfigure(0, weight=1)
        bottom.grid_columnconfigure(1, weight=1)

        self.breakdown = BreakdownChart(bottom, "Aquecimento por tipo (7 dias)")
        self.breakdown.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        logcard = widgets.card(bottom)
        logcard.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        widgets.title(logcard, "Últimas publicações", size=14).pack(anchor="w", padx=18, pady=(14, 6))
        self.log_frame = ctk.CTkScrollableFrame(logcard, fg_color="transparent", height=180)
        self.log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 12))

    def on_show(self):
        self._reload()

    def refresh(self):
        self._reload()

    def _reload(self):
        self.app.run_async(service.dashboard_stats, on_done=self._render_stats)
        self.app.run_async(lambda: service.chart_data(7), on_done=self._render_charts)
        self.app.run_async(lambda: service.recent_logs(12), on_done=self._render_logs)

    def _render_stats(self, stats):
        self.stat_cards["connected"].configure(text=f"{stats['connected']}/{stats['accounts']}")
        self.stat_cards["loops_running"].configure(text=str(stats["loops_running"]))
        self.stat_cards["warming"].configure(text=str(stats.get("warming", 0)))
        self.stat_cards["posts_24h"].configure(text=str(stats["posts_24h"]))
        self.stat_cards["scheduled_pending"].configure(text=str(stats["scheduled_pending"]))

    def _render_charts(self, data):
        self.chart_posts.set_data(data["posts"])
        self.chart_warm.set_data(data["warm"])
        self.chart_errors.set_data(data["errors"])
        bd = data.get("breakdown", {})
        self.breakdown.set_data([(label, bd.get(key, 0), color) for key, label, color in BREAKDOWN_SPECS])

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
