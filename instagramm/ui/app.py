"""Janela principal do painel desktop."""
import threading
import traceback

import customtkinter as ctk

from core import challenge_flow, service
from core.config import APP_NAME, APP_VERSION
from core.workers import WorkerManager
from ui import theme
from ui.views.accounts import AccountsView
from ui.views.automations import AutomationsView
from ui.views.dashboard import DashboardView
from ui.views.logs import LogsView
from ui.views.media import MediaView
from ui.views.publish import PublishView
from ui.views.settings import SettingsView

NAV = [
    ("dashboard", "  📊  Dashboard"),
    ("accounts", "  👤  Contas"),
    ("automations", "  ⚡  Automações"),
    ("publish", "  🚀  Publicar"),
    ("media", "  🎬  Mídia"),
    ("logs", "  📜  Logs"),
    ("settings", "  ⚙️  Configurações"),
]

VIEW_CLASSES = {
    "dashboard": DashboardView,
    "accounts": AccountsView,
    "automations": AutomationsView,
    "publish": PublishView,
    "media": MediaView,
    "logs": LogsView,
    "settings": SettingsView,
}


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title(APP_NAME)
        self.geometry("1200x760")
        self.minsize(1040, 660)
        self.configure(fg_color=theme.BG)

        service.setup()

        challenge_flow.set_ui_hook(self._on_challenge_needed)
        self._challenge_dialogs: dict[int, object] = {}

        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._views: dict[str, ctk.CTkFrame] = {}
        self._current: str | None = None

        self._build_layout()
        self.worker = WorkerManager(on_change=self._on_worker_change)
        self.worker.start()

        self.show_view("dashboard")
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(1500, self._check_sessions_on_start)

    def alert_session_expired(self, account_name: str):
        self.toast(f"⚠️ Sessão de {account_name} expirou — reconecte em Contas", "error")

    def _on_challenge_needed(self, account_id: int, username: str, channel: str):
        """Chamado quando o Instagram pede código extra durante o login (thread de fundo)."""
        self.after(0, lambda: self._show_challenge_dialog(account_id, username, channel))

    def _show_challenge_dialog(self, account_id: int, username: str, channel: str):
        if account_id in self._challenge_dialogs:
            return
        from ui.dialogs import ChallengeDialog

        def on_code(code):
            challenge_flow.submit_code(account_id, code)

        def on_cancel():
            challenge_flow.cancel_wait(account_id)
            self._challenge_dialogs.pop(account_id, None)

        dlg = ChallengeDialog(self, username, channel, on_code, on_cancel=on_cancel)
        self._challenge_dialogs[account_id] = dlg
        dlg.protocol("WM_DELETE_WINDOW", on_cancel)
        dlg.lift()
        dlg.attributes("-topmost", True)
        dlg.after(200, lambda: dlg.attributes("-topmost", False))
        dlg.focus_force()

    def _check_sessions_on_start(self):
        def done(expired):
            if not expired:
                return
            names = ", ".join(e["name"] for e in expired[:3])
            extra = f" (+{len(expired)-3})" if len(expired) > 3 else ""
            self.toast(f"⚠️ Sessão expirada: {names}{extra}. Reconecte em Contas.", "error")

        self.run_async(service.check_all_accounts, on_done=done)

    # ---------- layout ----------
    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        sidebar = ctk.CTkFrame(self, fg_color=theme.SIDEBAR, corner_radius=0, width=246)
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_propagate(False)

        # cabeçalho discreto (sem logo)
        ctk.CTkFrame(sidebar, fg_color="transparent", height=18).pack(fill="x")
        ctk.CTkLabel(sidebar, text="NAVEGAÇÃO", font=(theme.FONT, 10, "bold"), text_color=theme.MUTED,
                     anchor="w").pack(fill="x", padx=24, pady=(0, 8))

        self._nav_accents: dict[str, ctk.CTkFrame] = {}
        for key, label in NAV:
            item = ctk.CTkFrame(sidebar, fg_color="transparent", height=44)
            item.pack(fill="x", padx=10, pady=2)
            item.pack_propagate(False)
            accent = ctk.CTkFrame(item, fg_color="transparent", width=3, corner_radius=2)
            accent.pack(side="left", fill="y", padx=(0, 6))
            btn = ctk.CTkButton(
                item,
                text=label,
                anchor="w",
                height=42,
                corner_radius=10,
                fg_color="transparent",
                hover_color=theme.CARD2,
                text_color=theme.TEXT_SOFT,
                font=(theme.FONT, 13, "bold"),
                command=lambda k=key: self.show_view(k),
            )
            btn.pack(side="left", fill="both", expand=True)
            self._nav_buttons[key] = btn
            self._nav_accents[key] = accent

        footer = ctk.CTkLabel(sidebar, text=f"Instablack Local  ·  v{APP_VERSION}", font=(theme.FONT, 10),
                              text_color=theme.MUTED)
        footer.pack(side="bottom", pady=(8, 14))

        refresh_btn = ctk.CTkButton(
            sidebar, text="🔄  Atualizar painel", height=40, corner_radius=10,
            fg_color=theme.CARD2, hover_color=theme.CARD3, text_color=theme.TEXT,
            border_width=1, border_color=theme.BORDER, font=(theme.FONT, 12, "bold"),
            command=self._refresh_panel,
        )
        refresh_btn.pack(side="bottom", fill="x", padx=12, pady=(0, 4))

        # content
        self.content = ctk.CTkFrame(self, fg_color=theme.BG)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        # toast
        self.toast_label = ctk.CTkLabel(
            self,
            text="",
            fg_color=theme.CARD3,
            corner_radius=12,
            text_color=theme.TEXT,
            font=(theme.FONT, 12, "bold"),
            height=46,
            width=340,
        )

    # ---------- navegação ----------
    def show_view(self, key: str):
        if key not in VIEW_CLASSES:
            return
        if self._current == key:
            self._views[key].on_show()
            return

        for k, btn in self._nav_buttons.items():
            active = k == key
            btn.configure(
                fg_color=theme.PRIMARY_SOFT if active else "transparent",
                text_color=theme.PRIMARY if active else theme.TEXT_SOFT,
            )
            self._nav_accents[k].configure(fg_color=theme.PRIMARY if active else "transparent")

        if key not in self._views:
            view = VIEW_CLASSES[key](self.content, self)
            self._views[key] = view
        view = self._views[key]

        if self._current and self._current in self._views:
            self._views[self._current].grid_forget()
        view.grid(row=0, column=0, sticky="nsew", padx=28, pady=24)
        self._current = key
        view.on_show()

    # ---------- helpers ----------
    def toast(self, message: str, kind: str = "info"):
        colors = {"info": theme.TEXT, "success": theme.SUCCESS, "error": theme.DANGER}
        self.toast_label.configure(text=message, text_color=colors.get(kind, theme.TEXT))
        self.toast_label.place(relx=0.5, rely=0.97, anchor="s")
        self.toast_label.lift()
        if getattr(self, "_toast_after", None):
            self.after_cancel(self._toast_after)
        self._toast_after = self.after(4000, self.toast_label.place_forget)

    def run_async(self, fn, on_done=None, on_error=None):
        """Roda fn() numa thread e entrega o resultado na thread da UI."""
        def worker():
            try:
                result = fn()
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                if on_error:
                    self.after(0, lambda: on_error(exc))
                else:
                    self.after(0, lambda: self.toast(str(exc), "error"))
                return
            if on_done:
                self.after(0, lambda: on_done(result))

        threading.Thread(target=worker, daemon=True).start()

    def _on_worker_change(self):
        # vem de thread de fundo -> agenda refresh na UI
        self.after(0, self._refresh_current)

    def _refresh_current(self):
        if self._current and self._current in self._views:
            try:
                self._views[self._current].refresh()
            except Exception:  # noqa: BLE001
                pass

    def _refresh_panel(self):
        """Recarrega a tela atual sob demanda (botão Atualizar painel)."""
        if self._current and self._current in self._views:
            try:
                self._views[self._current].on_show()
                self.toast("Painel atualizado", "success")
            except Exception:  # noqa: BLE001
                self.toast("Não foi possível atualizar", "error")

    def _on_close(self):
        try:
            self.worker.stop()
        except Exception:  # noqa: BLE001
            pass
        self.destroy()
