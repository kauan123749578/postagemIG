"""Janela principal do painel desktop."""
import threading
import traceback

import customtkinter as ctk

from core import service
from core.config import APP_NAME, APP_VERSION
from core.workers import WorkerManager
from ui import theme
from ui.views.accounts import AccountsView
from ui.views.dashboard import DashboardView
from ui.views.logs import LogsView
from ui.views.loop import LoopView
from ui.views.media import MediaView
from ui.views.publish import PublishView
from ui.views.schedule import ScheduleView

NAV = [
    ("dashboard", "  📊  Dashboard"),
    ("accounts", "  👤  Contas"),
    ("publish", "  🚀  Publicar"),
    ("loop", "  🔁  Loop contínuo"),
    ("schedule", "  ⏰  Agendamentos"),
    ("media", "  🎬  Mídia"),
    ("logs", "  📜  Logs"),
]

VIEW_CLASSES = {
    "dashboard": DashboardView,
    "accounts": AccountsView,
    "publish": PublishView,
    "loop": LoopView,
    "schedule": ScheduleView,
    "media": MediaView,
    "logs": LogsView,
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

        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._views: dict[str, ctk.CTkFrame] = {}
        self._current: str | None = None

        self._build_layout()
        self.worker = WorkerManager(on_change=self._on_worker_change)
        self.worker.start()

        self.show_view("dashboard")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- layout ----------
    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        sidebar = ctk.CTkFrame(self, fg_color=theme.SIDEBAR, corner_radius=0, width=232)
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_propagate(False)

        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.pack(fill="x", padx=18, pady=(24, 18))
        ctk.CTkLabel(brand, text="📸", font=(theme.FONT, 26)).pack(side="left")
        bt = ctk.CTkFrame(brand, fg_color="transparent")
        bt.pack(side="left", padx=10)
        ctk.CTkLabel(bt, text=APP_NAME, font=(theme.FONT, 15, "bold"), text_color=theme.TEXT).pack(anchor="w")
        ctk.CTkLabel(bt, text="instagrapi", font=(theme.FONT, 10), text_color=theme.MUTED).pack(anchor="w")

        for key, label in NAV:
            btn = ctk.CTkButton(
                sidebar,
                text=label,
                anchor="w",
                height=44,
                corner_radius=10,
                fg_color="transparent",
                hover_color=theme.CARD2,
                text_color=theme.MUTED,
                font=(theme.FONT, 13, "bold"),
                command=lambda k=key: self.show_view(k),
            )
            btn.pack(fill="x", padx=12, pady=2)
            self._nav_buttons[key] = btn

        footer = ctk.CTkLabel(sidebar, text=f"v{APP_VERSION}", font=(theme.FONT, 10), text_color=theme.MUTED)
        footer.pack(side="bottom", pady=14)

        # content
        self.content = ctk.CTkFrame(self, fg_color=theme.BG)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        # toast
        self.toast_label = ctk.CTkLabel(
            self,
            text="",
            fg_color=theme.CARD2,
            corner_radius=10,
            text_color=theme.TEXT,
            font=(theme.FONT, 12, "bold"),
            height=44,
            width=320,
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
                fg_color=theme.PRIMARY if active else "transparent",
                text_color="#ffffff" if active else theme.MUTED,
            )

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

    def _on_close(self):
        try:
            self.worker.stop()
        except Exception:  # noqa: BLE001
            pass
        self.destroy()
