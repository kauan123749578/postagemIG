"""Tela Dashboard: métricas, desempenho e filas."""
from datetime import datetime

import customtkinter as ctk

from core import automations as auto_svc
from core import service
from ui import theme, widgets
from ui.charts import BarChart
from ui.views.base import BaseView


class DashboardView(BaseView):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.chart_days = 7
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew")
        head.grid_columnconfigure(0, weight=1)
        widgets.title(head, "Dashboard", size=24).grid(row=0, column=0, sticky="w")
        self.refresh_btn = widgets.ghost_button(
            head, "🔄  Atualizar métricas", self._refresh_metrics, width=170, height=34,
        )
        self.refresh_btn.grid(row=0, column=1, sticky="e")
        widgets.subtitle(self, "Visão geral e atividade das automações").grid(
            row=1, column=0, sticky="w", pady=(0, 14)
        )

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

        # Linha: Seu Desempenho | Automações ativas | Próximas publicações
        mid = ctk.CTkFrame(self, fg_color="transparent")
        mid.grid(row=3, column=0, sticky="ew", pady=(16, 0))
        mid.grid_columnconfigure(0, weight=2)
        mid.grid_columnconfigure(1, weight=1)
        mid.grid_columnconfigure(2, weight=1)
        mid.grid_rowconfigure(0, weight=1)

        self._build_performance(mid)
        self._build_active_autos(mid)
        self._build_upcoming(mid)

        logcard = widgets.card(self)
        logcard.grid(row=4, column=0, sticky="nsew", pady=(16, 0))
        logcard.grid_columnconfigure(0, weight=1)
        logcard.grid_rowconfigure(1, weight=1)
        widgets.title(logcard, "Últimas publicações", size=14).grid(
            row=0, column=0, sticky="w", padx=18, pady=(14, 6)
        )
        self.log_frame = widgets.soft_scrollable(logcard, speed=0.25)
        self.log_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 12))

    def _build_performance(self, parent):
        card = widgets.card(parent)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ctk.CTkFrame(card, fg_color=theme.PRIMARY, height=2, corner_radius=0).pack(fill="x")

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(12, 4))
        left = ctk.CTkFrame(head, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        top = ctk.CTkFrame(left, fg_color="transparent")
        top.pack(anchor="w", fill="x")
        ctk.CTkLabel(
            top, text="📈", width=32, height=32, corner_radius=8,
            fg_color=theme.PRIMARY_SOFT, text_color=theme.PRIMARY, font=(theme.FONT, 14),
        ).pack(side="left", padx=(0, 8))
        titles = ctk.CTkFrame(top, fg_color="transparent")
        titles.pack(side="left")
        ctk.CTkLabel(titles, text="Seu Desempenho", font=(theme.FONT, 14, "bold"), text_color=theme.TEXT).pack(anchor="w")
        self.perf_period = ctk.CTkLabel(
            titles, text="ÚLTIMOS 7 DIAS", font=(theme.FONT, 10, "bold"), text_color=theme.MUTED,
        )
        self.perf_period.pack(anchor="w")

        self.day_btns = {}
        days_row = ctk.CTkFrame(head, fg_color="transparent")
        days_row.pack(side="right")
        for d in (7, 15, 30):
            btn = ctk.CTkButton(
                days_row, text=f"{d}D", width=42, height=28, corner_radius=8,
                fg_color=theme.PRIMARY_SOFT if d == 7 else theme.CARD2,
                hover_color=theme.CARD3,
                text_color=theme.PRIMARY if d == 7 else theme.MUTED,
                font=(theme.FONT, 11, "bold"),
                border_width=1, border_color=theme.PRIMARY if d == 7 else theme.BORDER,
                command=lambda n=d: self._set_chart_days(n),
            )
            btn.pack(side="left", padx=2)
            self.day_btns[d] = btn

        legend = ctk.CTkFrame(card, fg_color="transparent")
        legend.pack(anchor="w", padx=16, pady=(0, 4))
        ctk.CTkFrame(legend, fg_color=theme.PRIMARY, width=10, height=10, corner_radius=2).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(legend, text="Publicações", font=(theme.FONT, 11), text_color=theme.MUTED).pack(side="left")

        # gráfico embutido sem título próprio
        self.chart_posts = BarChart(card, title="", color=theme.PRIMARY, height=170)
        for child in self.chart_posts.winfo_children():
            if isinstance(child, ctk.CTkLabel):
                child.pack_forget()
        self.chart_posts.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.chart_posts.configure(fg_color=theme.CARD, border_width=0)

    def _build_active_autos(self, parent):
        card = widgets.card(parent)
        card.grid(row=0, column=1, sticky="nsew", padx=4)
        ctk.CTkFrame(card, fg_color=theme.PRIMARY, height=2, corner_radius=0).pack(fill="x")
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkLabel(head, text="Automações ativas", font=(theme.FONT, 14, "bold"), text_color=theme.TEXT).pack(side="left")
        ctk.CTkButton(
            head, text="Ver todas", width=70, height=26, corner_radius=8,
            fg_color="transparent", hover_color=theme.CARD2,
            text_color=theme.PRIMARY, font=(theme.FONT, 11, "bold"),
            command=lambda: self.app.show_view("automations"),
        ).pack(side="right")
        self.autos_body = widgets.soft_scrollable(card, speed=0.22, height=200)
        self.autos_body.pack(fill="both", expand=True, padx=10, pady=(0, 12))

    def _build_upcoming(self, parent):
        card = widgets.card(parent)
        card.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
        ctk.CTkFrame(card, fg_color=theme.PRIMARY, height=2, corner_radius=0).pack(fill="x")
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkLabel(head, text="Próximas publicações", font=(theme.FONT, 14, "bold"), text_color=theme.TEXT).pack(side="left")
        self.upcoming_body = widgets.soft_scrollable(card, speed=0.22, height=200)
        self.upcoming_body.pack(fill="both", expand=True, padx=10, pady=(0, 12))

    def on_show(self):
        self._reload()

    def refresh(self):
        self._reload()

    def _refresh_metrics(self):
        self.refresh_btn.configure(state="disabled", text="Atualizando...")

        def done(_ok=None):
            self.refresh_btn.configure(state="normal", text="🔄  Atualizar métricas")
            self._reload()
            self.app.toast("Métricas atualizadas", "success")

        def err(exc):
            self.refresh_btn.configure(state="normal", text="🔄  Atualizar métricas")
            self.app.toast(str(exc), "error")

        def work():
            # bate no banco pra garantir dados frescos
            service.dashboard_stats()
            return True

        self.app.run_async(work, on_done=done, on_error=err)

    def _set_chart_days(self, days: int):
        self.chart_days = days
        self.perf_period.configure(text=f"ÚLTIMOS {days} DIAS")
        for d, btn in self.day_btns.items():
            active = d == days
            btn.configure(
                fg_color=theme.PRIMARY_SOFT if active else theme.CARD2,
                text_color=theme.PRIMARY if active else theme.MUTED,
                border_color=theme.PRIMARY if active else theme.BORDER,
            )
        self.app.run_async(lambda: service.chart_data(days), on_done=self._render_charts)

    def _reload(self):
        self.app.run_async(service.dashboard_stats, on_done=self._render_stats)
        self.app.run_async(lambda: service.chart_data(self.chart_days), on_done=self._render_charts)
        self.app.run_async(lambda: service.recent_logs(12), on_done=self._render_logs)
        self.app.run_async(auto_svc.list_active_automations_summary, on_done=self._render_autos)
        self.app.run_async(auto_svc.list_upcoming_jobs, on_done=self._render_upcoming)

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
        self.chart_posts.set_data(data.get("posts") or [])

    def _render_autos(self, items):
        for w in self.autos_body.winfo_children():
            w.destroy()
        if not items:
            box = ctk.CTkFrame(self.autos_body, fg_color=theme.CARD2, corner_radius=12, border_width=1, border_color=theme.BORDER)
            box.pack(fill="both", expand=True, pady=8)
            ctk.CTkLabel(
                box, text="Nenhuma automação cadastrada",
                font=(theme.FONT, 12), text_color=theme.MUTED,
            ).pack(pady=40)
            return
        for item in items:
            row = ctk.CTkFrame(self.autos_body, fg_color=theme.CARD2, corner_radius=10)
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(
                row, text=item.get("name") or "Automação",
                font=(theme.FONT, 12, "bold"), text_color=theme.TEXT, anchor="w",
            ).pack(fill="x", padx=10, pady=(8, 0))
            ctk.CTkLabel(
                row,
                text=f"a cada {item.get('interval_minutes')} min · {item.get('pending', 0)} na fila",
                font=(theme.FONT, 11), text_color=theme.MUTED, anchor="w",
            ).pack(fill="x", padx=10, pady=(0, 4))
            aid = item.get("id")
            if aid:
                widgets.ghost_button(
                    row, "⏸ Pausar",
                    lambda i=aid: self._pause_auto(i),
                    width=90, height=28,
                ).pack(anchor="w", padx=10, pady=(0, 8))

    def _pause_auto(self, automation_id: int):
        def work():
            return auto_svc.pause_automation(automation_id)

        def done(res):
            if res.get("ok"):
                self.app.toast(res.get("message") or "Pausada", "success")
            else:
                self.app.toast(res.get("message") or "Falha ao pausar", "error")
            self._reload()

        self.app.run_async(work, on_done=done)

    def _render_upcoming(self, items):
        for w in self.upcoming_body.winfo_children():
            w.destroy()
        if not items:
            box = ctk.CTkFrame(self.upcoming_body, fg_color=theme.CARD2, corner_radius=12, border_width=1, border_color=theme.BORDER)
            box.pack(fill="both", expand=True, pady=8)
            ctk.CTkLabel(
                box, text="Nenhuma publicação agendada",
                font=(theme.FONT, 12), text_color=theme.MUTED,
            ).pack(pady=40)
            return
        for item in items:
            row = ctk.CTkFrame(self.upcoming_body, fg_color=theme.CARD2, corner_radius=10)
            row.pack(fill="x", pady=3)
            when = item.get("scheduled_at") or ""
            try:
                dt = datetime.fromisoformat(when.replace("Z", "+00:00"))
                when_txt = dt.strftime("%d/%m %H:%M")
            except ValueError:
                when_txt = when[:16] if when else "—"
            ctk.CTkLabel(
                row, text=f"{item.get('account')} · {when_txt}",
                font=(theme.FONT, 12, "bold"), text_color=theme.TEXT, anchor="w",
            ).pack(fill="x", padx=10, pady=(8, 0))
            ctk.CTkLabel(
                row,
                text=f"{item.get('automation')} · {item.get('video') or 'Reel'}",
                font=(theme.FONT, 11), text_color=theme.MUTED, anchor="w",
            ).pack(fill="x", padx=10, pady=(0, 8))

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
