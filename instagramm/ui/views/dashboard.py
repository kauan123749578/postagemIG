"""Tela Dashboard: visão geral, gráficos e últimas publicações."""
import customtkinter as ctk

from core import service
from ui import theme, widgets
from ui.charts import BarChart
from ui.views.base import BaseView


class DashboardView(BaseView):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        widgets.title(self, "Dashboard", size=24).grid(row=0, column=0, sticky="w")
        widgets.subtitle(self, "Visão geral e atividade das automações").grid(
            row=1, column=0, sticky="w", pady=(0, 14)
        )

        # Cards preto/dourado (estilo Instablack)
        self.cards_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.cards_frame.grid(row=2, column=0, sticky="ew")
        for i in range(4):
            self.cards_frame.grid_columnconfigure(i, weight=1)

        specs = [
            ("connected", "👥", "Contas conectadas"),
            ("automations_active", "⚡", "Automações ativas"),
            ("posts_today", "🎬", "Publicações hoje"),
            ("success_rate", "📈", "Taxa de sucesso"),
        ]
        self.stat_values = {}
        self.stat_badges = {}
        for i, (key, icon, label) in enumerate(specs):
            card, value_lbl, badge_lbl = widgets.metric_card(
                self.cards_frame, icon=icon, label=label, value="—",
            )
            card.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 8, 0))
            self.stat_values[key] = value_lbl
            self.stat_badges[key] = badge_lbl

        charts = ctk.CTkFrame(self, fg_color="transparent")
        charts.grid(row=3, column=0, sticky="ew", pady=(16, 0))
        charts.grid_columnconfigure(0, weight=1)
        charts.grid_columnconfigure(1, weight=1)
        self.chart_posts = BarChart(charts, "Publicações (7 dias)", color=theme.ACCENT, height=150)
        self.chart_posts.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.chart_errors = BarChart(charts, "Erros (7 dias)", color=theme.DANGER, height=150)
        self.chart_errors.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        logcard = widgets.card(self)
        logcard.grid(row=4, column=0, sticky="nsew", pady=(16, 0))
        logcard.grid_columnconfigure(0, weight=1)
        logcard.grid_rowconfigure(1, weight=1)
        widgets.title(logcard, "Últimas publicações", size=14).grid(
            row=0, column=0, sticky="w", padx=18, pady=(14, 6)
        )
        self.log_frame = widgets.soft_scrollable(logcard, speed=0.25)
        self.log_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 12))

    def on_show(self):
        self._reload()

    def refresh(self):
        self._reload()

    def _reload(self):
        self.app.run_async(service.dashboard_stats, on_done=self._render_stats)
        self.app.run_async(lambda: service.chart_data(7), on_done=self._render_charts)
        self.app.run_async(lambda: service.recent_logs(12), on_done=self._render_logs)

    def _set_badge(self, key: str, text: str):
        badge = self.stat_badges[key]
        if text:
            badge.configure(text=text)
            if not badge.winfo_ismapped():
                badge.pack(side="right")
        else:
            badge.pack_forget()

    def _render_stats(self, stats):
        connected = stats.get("connected", 0)
        total = stats.get("accounts", 0)
        self.stat_values["connected"].configure(text=str(connected))
        self._set_badge("connected", f"{connected}/{total}" if total else "")

        autos = stats.get("automations_active", 0)
        self.stat_values["automations_active"].configure(text=str(autos))
        self._set_badge("automations_active", "ativas" if autos else "")

        posts = stats.get("posts_today", stats.get("posts_24h", 0))
        self.stat_values["posts_today"].configure(text=str(posts))
        self._set_badge("posts_today", "")

        rate = float(stats.get("success_rate", 0) or 0)
        self.stat_values["success_rate"].configure(text=f"{rate:.1f}%")
        self._set_badge("success_rate", "")

    def _render_charts(self, data):
        self.chart_posts.set_data(data["posts"])
        self.chart_errors.set_data(data["errors"])

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
            ctk.CTkLabel(
                row,
                text=f"{log['account']} · {when}",
                text_color=theme.TEXT,
                font=(theme.FONT, 12),
                anchor="w",
            ).pack(side="left", padx=12, pady=8, fill="x", expand=True)
            ok = log["status"] == "success"
            ctk.CTkLabel(
                row,
                text="OK" if ok else "ERRO",
                text_color=theme.SUCCESS if ok else theme.DANGER,
                font=(theme.FONT, 11, "bold"),
            ).pack(side="right", padx=12)
