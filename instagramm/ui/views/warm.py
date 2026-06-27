"""Tela Aquecer contas: várias contas, ações randômicas e janela de horário."""
import customtkinter as ctk

from core import service
from ui import theme, widgets
from ui.views.base import BaseView

HOURS = [f"{h:02d}" for h in range(24)]


class WarmView(BaseView):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.accounts = []
        self.checks: dict[int, ctk.BooleanVar] = {}

        widgets.title(self, "Aquecer contas", size=24).pack(anchor="w")
        widgets.subtitle(self, "Selecione várias contas e simule atividade humana — com horário de início, fim e pausa automática").pack(anchor="w", pady=(0, 14))

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True)

        # --- seleção de contas ---
        accs_card = widgets.card(self.scroll)
        accs_card.pack(fill="x")
        head = ctk.CTkFrame(accs_card, fg_color="transparent")
        head.pack(fill="x", padx=18, pady=(14, 4))
        widgets.title(head, "Contas para aquecer", size=15).pack(side="left")
        widgets.ghost_button(head, "Limpar seleção", lambda: self._select_all(False)).pack(side="right", padx=6)
        widgets.ghost_button(head, "Selecionar todas", lambda: self._select_all(True)).pack(side="right")
        self.accs_frame = ctk.CTkFrame(accs_card, fg_color="transparent")
        self.accs_frame.pack(fill="x", padx=14, pady=(0, 14))

        # --- configuração das ações ---
        cfg = widgets.card(self.scroll)
        cfg.pack(fill="x", pady=(14, 0))
        inner = ctk.CTkFrame(cfg, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=18)
        widgets.title(inner, "Ações por ciclo (aplicadas às contas selecionadas)", size=15).pack(anchor="w", pady=(0, 10))

        grid = ctk.CTkFrame(inner, fg_color="transparent")
        grid.pack(fill="x")
        for i in range(4):
            grid.grid_columnconfigure(i, weight=1)
        self.likes = self._num(grid, "Curtidas/ciclo", "3", 0, 0)
        self.comments = self._num(grid, "Comentários/ciclo", "0", 0, 1)
        self.stories = self._num(grid, "Ver stories/ciclo", "3", 0, 2)
        self.story_likes = self._num(grid, "Curtir stories/ciclo", "0", 0, 3)
        self.follows = self._num(grid, "Seguir/ciclo", "0", 1, 0)
        self.unfollows = self._num(grid, "Deixar de seguir/ciclo", "0", 1, 1)
        self.saves = self._num(grid, "Salvar/ciclo", "0", 1, 2)
        self.scrolls = self._num(grid, "Rolagens de feed/ciclo", "1", 1, 3)

        grid2 = ctk.CTkFrame(inner, fg_color="transparent")
        grid2.pack(fill="x", pady=(12, 0))
        grid2.grid_columnconfigure(0, weight=1)
        grid2.grid_columnconfigure(1, weight=2)
        wrap_int = ctk.CTkFrame(grid2, fg_color="transparent")
        wrap_int.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        widgets.field_label(wrap_int, "Intervalo entre ciclos (min)").pack(anchor="w", pady=(0, 2))
        self.interval = widgets.entry(wrap_int, "45")
        self.interval.pack(fill="x")
        wrap_tags = ctk.CTkFrame(grid2, fg_color="transparent")
        wrap_tags.grid(row=0, column=1, sticky="ew")
        widgets.field_label(wrap_tags, "Hashtags (separadas por vírgula)").pack(anchor="w", pady=(0, 2))
        self.hashtags = widgets.entry(wrap_tags, "reels,explore,viral,foryou")
        self.hashtags.pack(fill="x")

        # --- janela de horário ---
        win = ctk.CTkFrame(inner, fg_color="transparent")
        win.pack(fill="x", pady=(14, 0))
        widgets.field_label(win, "Horário de funcionamento (fora dele o aquecimento pausa sozinho)").pack(anchor="w", pady=(0, 4))
        hrow = ctk.CTkFrame(win, fg_color="transparent")
        hrow.pack(anchor="w")
        ctk.CTkLabel(hrow, text="Começa às", font=(theme.FONT, 12), text_color=theme.TEXT_SOFT).pack(side="left", padx=(0, 6))
        self.start_hour = ctk.CTkOptionMenu(hrow, values=HOURS, width=80, fg_color=theme.CARD2, button_color=theme.PRIMARY,
                                            button_hover_color=theme.PRIMARY_HOVER, dropdown_fg_color=theme.CARD2)
        self.start_hour.set("08")
        self.start_hour.pack(side="left")
        ctk.CTkLabel(hrow, text="h     Termina às", font=(theme.FONT, 12), text_color=theme.TEXT_SOFT).pack(side="left", padx=6)
        self.end_hour = ctk.CTkOptionMenu(hrow, values=HOURS, width=80, fg_color=theme.CARD2, button_color=theme.PRIMARY,
                                          button_hover_color=theme.PRIMARY_HOVER, dropdown_fg_color=theme.CARD2)
        self.end_hour.set("23")
        self.end_hour.pack(side="left")
        ctk.CTkLabel(hrow, text="h", font=(theme.FONT, 12), text_color=theme.TEXT_SOFT).pack(side="left", padx=(6, 0))

        # --- controles ---
        ctrl = ctk.CTkFrame(self.scroll, fg_color="transparent")
        ctrl.pack(fill="x", pady=12)
        self.status_label = ctk.CTkLabel(ctrl, text="Nenhuma conta aquecendo", font=(theme.FONT, 13, "bold"), text_color=theme.MUTED)
        self.status_label.pack(side="left")
        widgets.ghost_button(ctrl, "Aquecer agora (1x)", self._run_once).pack(side="right", padx=(8, 0))
        widgets.danger_button(ctrl, "⏸ Pausar selecionadas", self._stop).pack(side="right", padx=(8, 0))
        widgets.primary_button(ctrl, "▶ Iniciar aquecimento", self._start).pack(side="right")

        info = widgets.card(self.scroll)
        info.pack(fill="x")
        widgets.title(info, "Como funciona", size=15).pack(anchor="w", padx=18, pady=(14, 4))
        txt = ("A cada ciclo o sistema entra em cada conta e faz ações leves e aleatórias usando a instagrapi: "
               "rola o feed, curte, comenta, vê e curte stories, segue e deixa de seguir.\n\n"
               "O intervalo varia ±30% para parecer humano e o aquecimento só roda dentro do horário definido — "
               "fora dele ele pausa sozinho (ninguém fica 24h no Instagram). Tudo é enviado ao seu Telegram.")
        ctk.CTkLabel(info, text=txt, justify="left", font=(theme.FONT, 12), text_color=theme.MUTED, wraplength=860).pack(anchor="w", padx=18, pady=(0, 16))

    def _num(self, master, label, default, row, col):
        wrap = ctk.CTkFrame(master, fg_color="transparent")
        wrap.grid(row=row, column=col, sticky="ew", padx=(0 if col == 0 else 6, 0), pady=(0 if row == 0 else 8, 0))
        widgets.field_label(wrap, label).pack(anchor="w", pady=(0, 2))
        e = widgets.entry(wrap, default)
        e.insert(0, default)
        e.pack(fill="x")
        return e

    def on_show(self):
        self.app.run_async(service.list_accounts, on_done=self._fill_accounts)

    def refresh(self):
        self.app.run_async(service.list_accounts, on_done=self._update_status_only)

    def _fill_accounts(self, accounts):
        self.accounts = accounts
        for c in self.accs_frame.winfo_children():
            c.destroy()
        self.checks = {}
        if not accounts:
            ctk.CTkLabel(self.accs_frame, text="Nenhuma conta. Conecte contas primeiro.", text_color=theme.MUTED).pack(pady=18, anchor="w", padx=4)
            return
        for a in accounts:
            var = ctk.BooleanVar(value=False)
            self.checks[a["id"]] = var
            row = ctk.CTkFrame(self.accs_frame, fg_color=theme.CARD2, corner_radius=10)
            row.pack(fill="x", padx=4, pady=3)
            chk = ctk.CTkCheckBox(row, text=f"  {a['name']} (@{a['username']})", variable=var,
                                  fg_color=theme.PRIMARY, hover_color=theme.PRIMARY_HOVER, text_color=theme.TEXT)
            chk.pack(side="left", padx=10, pady=8)
        # carrega config da primeira conta como ponto de partida
        first_id = accounts[0]["id"]
        self.app.run_async(lambda: service.get_warm(first_id), on_done=self._render_cfg)
        self._update_status(accounts)

    def _select_all(self, value: bool):
        for var in self.checks.values():
            var.set(value)

    def _selected_ids(self):
        return [acc_id for acc_id, var in self.checks.items() if var.get()]

    def _render_cfg(self, w):
        for entry, key in [(self.likes, "likes_per_run"), (self.comments, "comments_per_run"),
                           (self.stories, "stories_per_run"), (self.story_likes, "story_likes_per_run"),
                           (self.follows, "follows_per_run"), (self.unfollows, "unfollows_per_run"),
                           (self.saves, "saves_per_run"), (self.scrolls, "scrolls_per_run"),
                           (self.interval, "interval_minutes")]:
            entry.delete(0, "end"); entry.insert(0, str(w[key]))
        self.hashtags.delete(0, "end"); self.hashtags.insert(0, w["hashtags"])
        self.start_hour.set(f"{int(w.get('active_start_hour', 8)):02d}")
        self.end_hour.set(f"{int(w.get('active_end_hour', 23)):02d}")

    def _update_status_only(self, accounts):
        self.accounts = accounts
        self._update_status(accounts)

    def _update_status(self, accounts):
        self.app.run_async(service.list_warming, on_done=self._render_status)

    def _render_status(self, warming):
        running = [w for w in warming if w["is_running"]]
        if not running:
            self.status_label.configure(text="Nenhuma conta aquecendo", text_color=theme.MUTED)
            return
        in_window = service.within_active_window(_i(self.start_hour.get(), 8), _i(self.end_hour.get(), 23))
        state = "aquecendo" if in_window else "pausado (fora do horário)"
        self.status_label.configure(text=f"● {len(running)} conta(s) — {state}",
                                    text_color=theme.SUCCESS if in_window else theme.WARNING)

    def _cfg(self):
        return {
            "likes_per_run": _i(self.likes.get()),
            "comments_per_run": _i(self.comments.get()),
            "stories_per_run": _i(self.stories.get()),
            "story_likes_per_run": _i(self.story_likes.get()),
            "follows_per_run": _i(self.follows.get()),
            "unfollows_per_run": _i(self.unfollows.get()),
            "saves_per_run": _i(self.saves.get()),
            "scrolls_per_run": _i(self.scrolls.get()),
            "interval_minutes": _i(self.interval.get(), 45),
            "active_start_hour": _i(self.start_hour.get(), 8),
            "active_end_hour": _i(self.end_hour.get(), 23),
            "hashtags": self.hashtags.get().strip(),
        }

    def _start(self):
        ids = self._selected_ids()
        if not ids:
            self.app.toast("Marque ao menos uma conta", "error")
            return
        cfg = self._cfg()

        def task():
            service.save_warm_many(ids, **cfg)
            service.set_warm_running_many(ids, True)

        self.app.run_async(task, on_done=lambda _r: (self.app.toast(f"Aquecimento iniciado em {len(ids)} conta(s)", "success"), self._update_status(self.accounts)))

    def _stop(self):
        ids = self._selected_ids()
        if not ids:
            self.app.toast("Marque ao menos uma conta", "error")
            return
        self.app.run_async(lambda: service.set_warm_running_many(ids, False),
                           on_done=lambda _r: (self.app.toast("Aquecimento pausado", "info"), self._update_status(self.accounts)))

    def _run_once(self):
        ids = self._selected_ids()
        if not ids:
            self.app.toast("Marque ao menos uma conta", "error")
            return
        cfg = self._cfg()
        self.app.toast(f"Aquecendo {len(ids)} conta(s) agora... (pode demorar)", "info")

        def task():
            service.save_warm_many(ids, **cfg)
            results = [service.run_warm_once(acc_id) for acc_id in ids]
            return sum(1 for r in results if r.get("ok"))

        def done(ok_count):
            self.app.toast(f"Aquecimento concluído em {ok_count}/{len(ids)} conta(s)", "success")
            self._update_status(self.accounts)

        self.app.run_async(task, on_done=done)


def _i(value, default=0):
    try:
        return max(0, int(str(value).strip() or default))
    except ValueError:
        return default
