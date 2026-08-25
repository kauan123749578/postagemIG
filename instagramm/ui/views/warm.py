"""Tela Aquecer contas: pré-configurada, várias contas e janela de horário."""
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

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x")
        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        widgets.title(left, "Aquecer contas", size=24).pack(anchor="w")
        widgets.subtitle(left, "Já vem pré-configurado no modo recomendado — é só apertar Iniciar").pack(anchor="w")
        widgets.chip(header, "PRESET RECOMENDADO", theme.ACCENT, theme.PRIMARY_SOFT).pack(side="right", pady=6)

        self.scroll = widgets.soft_scrollable(self)
        self.scroll.pack(fill="both", expand=True, pady=(12, 0))

        # --- seleção de contas ---
        accs_card, accs_body = widgets.section(
            self.scroll, "Contas para aquecer", "Todas já vêm selecionadas — desmarque o que não quiser", icon="👥"
        )
        accs_card.pack(fill="x")
        tools = ctk.CTkFrame(accs_body, fg_color="transparent")
        tools.pack(fill="x", pady=(0, 8))
        widgets.ghost_button(tools, "Selecionar todas", lambda: self._select_all(True), height=34, width=150).pack(side="left")
        widgets.ghost_button(tools, "Limpar seleção", lambda: self._select_all(False), height=34, width=140).pack(side="left", padx=8)
        self.accs_frame = ctk.CTkFrame(accs_body, fg_color="transparent")
        self.accs_frame.pack(fill="x")

        # --- ações por ciclo ---
        cfg_card, cfg_body = widgets.section(
            self.scroll, "Ações por ciclo", "Aplicadas a todas as contas selecionadas", icon="⚙️"
        )
        cfg_card.pack(fill="x", pady=(14, 0))

        grid = ctk.CTkFrame(cfg_body, fg_color="transparent")
        grid.pack(fill="x")
        for i in range(4):
            grid.grid_columnconfigure(i, weight=1, uniform="warm")
        self.likes = self._stepper(grid, "❤️  Curtidas", 5, 0, 0)
        self.comments = self._stepper(grid, "💬  Comentários", 1, 0, 1)
        self.stories = self._stepper(grid, "👁  Ver stories", 5, 0, 2)
        self.story_likes = self._stepper(grid, "💗  Curtir stories", 2, 0, 3)
        self.follows = self._stepper(grid, "➕  Seguir", 1, 1, 0)
        self.unfollows = self._stepper(grid, "➖  Deixar de seguir", 0, 1, 1)
        self.saves = self._stepper(grid, "🔖  Salvar", 1, 1, 2)
        self.scrolls = self._stepper(grid, "📜  Rolar feed", 2, 1, 3)

        # --- ritmo e horário ---
        rit_card, rit_body = widgets.section(
            self.scroll, "Ritmo e horário", "Intervalo entre ciclos e janela ativa (fora dela pausa sozinho)", icon="⏱"
        )
        rit_card.pack(fill="x", pady=(14, 0))

        line = ctk.CTkFrame(rit_body, fg_color="transparent")
        line.pack(fill="x")
        line.grid_columnconfigure(0, weight=1)
        line.grid_columnconfigure(1, weight=2)
        wrap_int = ctk.CTkFrame(line, fg_color="transparent")
        wrap_int.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        widgets.field_label(wrap_int, "Intervalo entre ciclos (min)").pack(anchor="w", pady=(0, 2))
        self.interval = widgets.entry(wrap_int, "40")
        self.interval.insert(0, "40")
        self.interval.pack(fill="x")
        wrap_tags = ctk.CTkFrame(line, fg_color="transparent")
        wrap_tags.grid(row=0, column=1, sticky="ew")
        widgets.field_label(wrap_tags, "Hashtags (separadas por vírgula)").pack(anchor="w", pady=(0, 2))
        self.hashtags = widgets.entry(wrap_tags, "reels,explore,viral,foryou,fyp")
        self.hashtags.insert(0, "reels,explore,viral,foryou,fyp")
        self.hashtags.pack(fill="x")

        win = ctk.CTkFrame(rit_body, fg_color="transparent")
        win.pack(fill="x", pady=(14, 0))
        widgets.field_label(win, "Horário de funcionamento").pack(anchor="w", pady=(0, 4))
        hrow = ctk.CTkFrame(win, fg_color="transparent")
        hrow.pack(anchor="w")
        ctk.CTkLabel(hrow, text="Começa às", font=(theme.FONT, 12), text_color=theme.TEXT_SOFT).pack(side="left", padx=(0, 6))
        self.start_hour = self._hour_menu(hrow, "08")
        ctk.CTkLabel(hrow, text="h      Termina às", font=(theme.FONT, 12), text_color=theme.TEXT_SOFT).pack(side="left", padx=6)
        self.end_hour = self._hour_menu(hrow, "23")
        ctk.CTkLabel(hrow, text="h", font=(theme.FONT, 12), text_color=theme.TEXT_SOFT).pack(side="left", padx=(6, 0))

        # --- barra de controle fixa ---
        ctrl = widgets.card(self, fg_color=theme.CARD2)
        ctrl.pack(fill="x", pady=(12, 0))
        cinner = ctk.CTkFrame(ctrl, fg_color="transparent")
        cinner.pack(fill="x", padx=18, pady=12)
        self.status_label = ctk.CTkLabel(cinner, text="Nenhuma conta aquecendo", font=(theme.FONT, 13, "bold"), text_color=theme.MUTED)
        self.status_label.pack(side="left")
        widgets.primary_button(cinner, "▶  Iniciar aquecimento", self._start, width=190).pack(side="right")
        widgets.danger_button(cinner, "⏸  Pausar", self._stop, width=110).pack(side="right", padx=8)
        widgets.ghost_button(cinner, "Aquecer agora (1x)", self._run_once, width=160).pack(side="right", padx=(0, 8))

    def _stepper(self, master, label, default, row, col):
        wrap = ctk.CTkFrame(master, fg_color="transparent")
        wrap.grid(row=row, column=col, sticky="ew", padx=(0 if col == 0 else 8, 0), pady=(0 if row == 0 else 10, 0))
        widgets.field_label(wrap, label).pack(anchor="w", pady=(0, 3))
        st = widgets.Stepper(wrap, default=default, lo=0, hi=99)
        st.pack(fill="x")
        return st

    def _hour_menu(self, master, default):
        m = ctk.CTkOptionMenu(master, values=HOURS, width=82, height=36, fg_color=theme.CARD2,
                              button_color=theme.PRIMARY, button_hover_color=theme.PRIMARY_HOVER,
                              dropdown_fg_color=theme.CARD2, text_color=theme.TEXT, corner_radius=10)
        m.set(default)
        m.pack(side="left")
        return m

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
            ctk.CTkLabel(self.accs_frame, text="Nenhuma conta. Conecte contas primeiro.", text_color=theme.MUTED).pack(pady=14, anchor="w")
            return
        for a in accounts:
            var = ctk.BooleanVar(value=True)  # já vem marcada
            self.checks[a["id"]] = var
            row = ctk.CTkFrame(self.accs_frame, fg_color=theme.CARD2, corner_radius=10)
            row.pack(fill="x", pady=3)
            chk = ctk.CTkCheckBox(row, text=f"  {a['name']}  ·  @{a['username']}", variable=var,
                                  fg_color=theme.PRIMARY, hover_color=theme.PRIMARY_HOVER, text_color=theme.TEXT,
                                  font=(theme.FONT, 12))
            chk.pack(side="left", padx=12, pady=9)
            pill = widgets.status_pill(row, a.get("status", "unknown"))
            pill.pack(side="right", padx=12)
        # carrega config da primeira conta (preset recomendado se nova)
        first_id = accounts[0]["id"]
        self.app.run_async(lambda: service.get_warm(first_id), on_done=self._render_cfg)
        self._update_status(accounts)

    def _select_all(self, value: bool):
        for var in self.checks.values():
            var.set(value)

    def _selected_ids(self):
        return [acc_id for acc_id, var in self.checks.items() if var.get()]

    def _render_cfg(self, w):
        self.likes.set(w["likes_per_run"])
        self.comments.set(w["comments_per_run"])
        self.stories.set(w["stories_per_run"])
        self.story_likes.set(w["story_likes_per_run"])
        self.follows.set(w["follows_per_run"])
        self.unfollows.set(w["unfollows_per_run"])
        self.saves.set(w["saves_per_run"])
        self.scrolls.set(w["scrolls_per_run"])
        self.interval.delete(0, "end"); self.interval.insert(0, str(w["interval_minutes"]))
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
        state = "aquecendo agora" if in_window else "pausado (fora do horário)"
        self.status_label.configure(text=f"●  {len(running)} conta(s)  ·  {state}",
                                    text_color=theme.SUCCESS if in_window else theme.WARNING)

    def _cfg(self):
        return {
            "likes_per_run": self.likes.get(),
            "comments_per_run": self.comments.get(),
            "stories_per_run": self.stories.get(),
            "story_likes_per_run": self.story_likes.get(),
            "follows_per_run": self.follows.get(),
            "unfollows_per_run": self.unfollows.get(),
            "saves_per_run": self.saves.get(),
            "scrolls_per_run": self.scrolls.get(),
            "interval_minutes": _i(self.interval.get(), 40),
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
