"""Tela Aquecer contas: simula atividade humana para 'esquentar' o perfil."""
import customtkinter as ctk

from core import service
from ui import theme, widgets
from ui.views.base import BaseView


class WarmView(BaseView):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.accounts = []

        widgets.title(self, "Aquecer contas", size=24).pack(anchor="w")
        widgets.subtitle(self, "Simula curtidas, stories e follows como um usuário real — reduz bloqueios").pack(anchor="w", pady=(0, 16))

        cfg = widgets.card(self)
        cfg.pack(fill="x")
        inner = ctk.CTkFrame(cfg, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=18)

        widgets.field_label(inner, "Conta").pack(anchor="w", pady=(0, 2))
        self.account_menu = ctk.CTkOptionMenu(inner, values=["Carregando..."], command=lambda _v: self._load(),
                                              fg_color=theme.CARD2, button_color=theme.PRIMARY,
                                              button_hover_color=theme.PRIMARY_HOVER, dropdown_fg_color=theme.CARD2, height=40)
        self.account_menu.pack(fill="x", pady=(0, 12))

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
        widgets.field_label(wrap_int, "Intervalo (min)").pack(anchor="w", pady=(0, 2))
        self.interval = widgets.entry(wrap_int, "45")
        self.interval.pack(fill="x")
        wrap_tags = ctk.CTkFrame(grid2, fg_color="transparent")
        wrap_tags.grid(row=0, column=1, sticky="ew")
        widgets.field_label(wrap_tags, "Hashtags (separadas por vírgula)").pack(anchor="w", pady=(0, 2))
        self.hashtags = widgets.entry(wrap_tags, "reels,explore,viral,foryou")
        self.hashtags.pack(fill="x")

        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.pack(fill="x", pady=12)
        self.status_label = ctk.CTkLabel(ctrl, text="Aquecimento parado", font=(theme.FONT, 13, "bold"), text_color=theme.MUTED)
        self.status_label.pack(side="left")
        widgets.ghost_button(ctrl, "Aquecer agora (1x)", self._run_once).pack(side="right", padx=(8, 0))
        self.stop_btn = widgets.danger_button(ctrl, "■ Parar", self._stop)
        self.stop_btn.pack(side="right", padx=(8, 0))
        self.start_btn = widgets.primary_button(ctrl, "▶ Iniciar aquecimento", self._start)
        self.start_btn.pack(side="right")

        info = widgets.card(self)
        info.pack(fill="both", expand=True)
        widgets.title(info, "Como funciona", size=15).pack(anchor="w", padx=18, pady=(14, 4))
        txt = ("A cada ciclo o sistema entra na conta e faz ações leves e aleatórias usando a instagrapi:\n"
               "• lê o feed principal\n• curte algumas publicações de hashtags\n• assiste stories\n"
               "• opcionalmente segue/salva\n\nO intervalo varia automaticamente ±30% para parecer humano. "
               "Comece devagar (poucas ações) em contas novas. Todos os ciclos são enviados ao seu Telegram.")
        ctk.CTkLabel(info, text=txt, justify="left", font=(theme.FONT, 12), text_color=theme.MUTED, wraplength=820).pack(anchor="w", padx=18, pady=(0, 16))

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
        self._load()

    def _fill_accounts(self, accounts):
        self.accounts = accounts
        labels = [f"{a['name']} (@{a['username']})" for a in accounts] or ["Nenhuma conta"]
        self.account_menu.configure(values=labels)
        if self.account_menu.get() not in labels:
            self.account_menu.set(labels[0])
        self._load()

    def _account_id(self):
        label = self.account_menu.get()
        for a in self.accounts:
            if f"{a['name']} (@{a['username']})" == label:
                return a["id"]
        return None

    def _load(self):
        acc_id = self._account_id()
        if not acc_id:
            return
        self.app.run_async(lambda: service.get_warm(acc_id), on_done=self._render)

    def _render(self, w):
        for entry, key in [(self.likes, "likes_per_run"), (self.comments, "comments_per_run"),
                           (self.stories, "stories_per_run"), (self.story_likes, "story_likes_per_run"),
                           (self.follows, "follows_per_run"), (self.unfollows, "unfollows_per_run"),
                           (self.saves, "saves_per_run"), (self.scrolls, "scrolls_per_run"),
                           (self.interval, "interval_minutes")]:
            entry.delete(0, "end"); entry.insert(0, str(w[key]))
        self.hashtags.delete(0, "end"); self.hashtags.insert(0, w["hashtags"])
        if w["is_running"]:
            txt = f"● Aquecendo — {w['total_actions']} ações no total"
            if w["last_summary"]:
                txt += f"\n{w['last_summary']}"
            self.status_label.configure(text=txt, text_color=theme.SUCCESS)
        else:
            extra = f"  ·  {w['last_summary']}" if w["last_summary"] else ""
            self.status_label.configure(text="Aquecimento parado" + extra, text_color=theme.MUTED)

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
            "hashtags": self.hashtags.get().strip(),
        }

    def _save_cfg(self, acc_id):
        service.save_warm(acc_id, **self._cfg())

    def _start(self):
        acc_id = self._account_id()
        if not acc_id:
            self.app.toast("Selecione uma conta", "error")
            return

        def task():
            self._save_cfg(acc_id)
            service.set_warm_running(acc_id, True)

        self.app.run_async(task, on_done=lambda _r: (self.app.toast("Aquecimento iniciado", "success"), self._load()))

    def _stop(self):
        acc_id = self._account_id()
        if not acc_id:
            return
        self.app.run_async(lambda: service.set_warm_running(acc_id, False),
                           on_done=lambda _r: (self.app.toast("Aquecimento parado", "info"), self._load()))

    def _run_once(self):
        acc_id = self._account_id()
        if not acc_id:
            self.app.toast("Selecione uma conta", "error")
            return
        self.app.toast("Aquecendo agora... (pode demorar)", "info")

        def task():
            self._save_cfg(acc_id)
            return service.run_warm_once(acc_id)

        def done(res):
            if res.get("ok"):
                self.app.toast(f"Aquecimento: {res['text']}", "success")
            else:
                self.app.toast(res.get("message", "Falha no aquecimento"), "error")
            self._load()

        self.app.run_async(task, on_done=done)


def _i(value, default=0):
    try:
        return max(0, int(str(value).strip() or default))
    except ValueError:
        return default
