"""Tela Fila escalonada: ativa o loop de cada conta em horários espaçados."""
import customtkinter as ctk

from core import service
from ui import theme, widgets
from ui.views.base import BaseView


class StaggerView(BaseView):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.accounts = []
        self.checks: dict[int, ctk.BooleanVar] = {}

        widgets.title(self, "Fila escalonada", size=24).pack(anchor="w")
        widgets.subtitle(self, "Liga os loops aos poucos: ativa uma conta agora e as próximas a cada X minutos — evita postar tudo junto").pack(anchor="w", pady=(0, 16))

        cfg = widgets.card(self)
        cfg.pack(fill="x")
        row = ctk.CTkFrame(cfg, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=16)
        left = ctk.CTkFrame(row, fg_color="transparent")
        left.pack(side="left")
        widgets.field_label(left, "Intervalo entre ativações (min)").pack(anchor="w", pady=(0, 2))
        self.stagger_entry = widgets.entry(left, "10", width=140)
        self.stagger_entry.insert(0, "10")
        self.stagger_entry.pack()
        widgets.primary_button(row, "▶ Iniciar fila", self._start).pack(side="right")
        widgets.danger_button(row, "Cancelar fila", self._cancel).pack(side="right", padx=8)

        widgets.subtitle(self, "Recomendado: 8 a 15 minutos entre cada conta.").pack(anchor="w", pady=(8, 12))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)

        accs_card = widgets.card(body)
        accs_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        widgets.title(accs_card, "Contas com loop configurado", size=14).pack(anchor="w", padx=16, pady=(14, 6))
        self.accs_frame = ctk.CTkScrollableFrame(accs_card, fg_color="transparent")
        self.accs_frame.pack(fill="both", expand=True, padx=10, pady=(0, 12))

        queue_card = widgets.card(body)
        queue_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        widgets.title(queue_card, "Fila atual", size=14).pack(anchor="w", padx=16, pady=(14, 6))
        self.queue_frame = ctk.CTkScrollableFrame(queue_card, fg_color="transparent")
        self.queue_frame.pack(fill="both", expand=True, padx=10, pady=(0, 12))

    def on_show(self):
        self._reload()

    def refresh(self):
        self._reload_queue()

    def _reload(self):
        self.app.run_async(service.list_accounts, on_done=self._render_accounts)
        self._reload_queue()

    def _reload_queue(self):
        self.app.run_async(service.list_stagger, on_done=self._render_queue)

    def _render_accounts(self, accounts):
        self.accounts = accounts
        for c in self.accs_frame.winfo_children():
            c.destroy()
        self.checks = {}
        eligible = [a for a in accounts if a.get("loop_posts") is not None]
        if not accounts:
            ctk.CTkLabel(self.accs_frame, text="Nenhuma conta. Conecte contas e configure loops.", text_color=theme.MUTED, wraplength=300).pack(pady=24)
            return
        for a in accounts:
            var = ctk.BooleanVar(value=False)
            self.checks[a["id"]] = var
            running = a.get("loop_running")
            label = f"{a['name']} (@{a['username']})"
            if running:
                label += "  • já rodando"
            chk = ctk.CTkCheckBox(self.accs_frame, text=label, variable=var,
                                  fg_color=theme.PRIMARY, hover_color=theme.PRIMARY_HOVER, text_color=theme.TEXT)
            chk.pack(anchor="w", padx=8, pady=5)

    def _render_queue(self, items):
        for c in self.queue_frame.winfo_children():
            c.destroy()
        if not items:
            ctk.CTkLabel(self.queue_frame, text="Nenhuma fila ativa.", text_color=theme.MUTED).pack(pady=24)
            return
        for it in items:
            row = ctk.CTkFrame(self.queue_frame, fg_color=theme.CARD2, corner_radius=10)
            row.pack(fill="x", padx=6, pady=3)
            when = it["activate_at"].replace("T", " ")[11:16] if it["activate_at"] else ""
            ctk.CTkLabel(row, text=it["account"], text_color=theme.TEXT, font=(theme.FONT, 12), anchor="w").pack(side="left", padx=12, pady=8, fill="x", expand=True)
            done = it["status"] == "activated"
            tag = "ativada" if done else f"às {when}"
            ctk.CTkLabel(row, text=tag, text_color=theme.SUCCESS if done else theme.ACCENT, font=(theme.FONT, 11, "bold")).pack(side="right", padx=12)

    def _start(self):
        selected = [acc_id for acc_id, var in self.checks.items() if var.get()]
        if not selected:
            self.app.toast("Marque ao menos uma conta", "error")
            return
        try:
            stagger = max(1, int(self.stagger_entry.get().strip() or 10))
        except ValueError:
            stagger = 10

        def task():
            return service.start_stagger(selected, stagger)

        def done(res):
            if res.get("ok"):
                self.app.toast(res["message"], "success")
            else:
                self.app.toast(res.get("message", "Erro"), "error")
            self._reload_queue()

        self.app.run_async(task, on_done=done)

    def _cancel(self):
        self.app.run_async(service.cancel_stagger, on_done=lambda _r: (self.app.toast("Fila cancelada", "info"), self._reload_queue()))
