"""Tela Loop contínuo: posta vídeos de uma lista em intervalos definidos."""
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from core import service
from ui import theme, widgets
from ui.views.base import BaseView


class LoopView(BaseView):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.accounts = []
        self.videos = []  # list[{video_path, cover_path, caption}]

        widgets.title(self, "Loop contínuo", size=24).pack(anchor="w")
        widgets.subtitle(self, "Publica os vídeos da lista em sequência, repetindo no intervalo definido").pack(anchor="w", pady=(0, 16))

        top = widgets.card(self)
        top.pack(fill="x")
        inner = ctk.CTkFrame(top, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=18)
        inner.grid_columnconfigure(0, weight=1)
        inner.grid_columnconfigure(1, weight=0)

        left = ctk.CTkFrame(inner, fg_color="transparent")
        left.grid(row=0, column=0, sticky="ew")
        widgets.field_label(left, "Conta").pack(anchor="w", pady=(0, 2))
        self.account_menu = ctk.CTkOptionMenu(left, values=["Carregando..."], command=lambda _v: self._load_loop(),
                                              fg_color=theme.CARD2, button_color=theme.PRIMARY,
                                              button_hover_color=theme.PRIMARY_HOVER, dropdown_fg_color=theme.CARD2, height=40)
        self.account_menu.pack(fill="x")

        right = ctk.CTkFrame(inner, fg_color="transparent")
        right.grid(row=0, column=1, sticky="e", padx=(16, 0))
        widgets.field_label(right, "Intervalo (segundos)").pack(anchor="w", pady=(0, 2))
        self.interval_entry = widgets.entry(right, "120", width=120)
        self.interval_entry.insert(0, "120")
        self.interval_entry.pack()

        widgets.field_label(inner, "Legenda padrão do loop").grid(row=1, column=0, columnspan=2, sticky="w", pady=(12, 2))
        self.caption_box = ctk.CTkTextbox(inner, height=60, fg_color=theme.CARD2, border_color=theme.BORDER, border_width=1, corner_radius=10)
        self.caption_box.grid(row=2, column=0, columnspan=2, sticky="ew")

        # status + controles
        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.pack(fill="x", pady=12)
        self.status_label = ctk.CTkLabel(ctrl, text="Loop parado", font=(theme.FONT, 13, "bold"), text_color=theme.MUTED)
        self.status_label.pack(side="left")
        self.stop_btn = widgets.danger_button(ctrl, "■ Parar loop", self._stop)
        self.stop_btn.pack(side="right", padx=(8, 0))
        self.start_btn = widgets.primary_button(ctrl, "▶ Iniciar loop", self._start)
        self.start_btn.pack(side="right")

        # lista de vídeos
        listcard = widgets.card(self)
        listcard.pack(fill="both", expand=True)
        lhead = ctk.CTkFrame(listcard, fg_color="transparent")
        lhead.pack(fill="x", padx=18, pady=(14, 6))
        widgets.title(lhead, "Vídeos do loop", size=15).pack(side="left")
        widgets.ghost_button(lhead, "Limpar", self._clear_videos).pack(side="right", padx=6)
        widgets.primary_button(lhead, "+ Adicionar vídeos", self._add_videos).pack(side="right")
        self.videos_frame = ctk.CTkScrollableFrame(listcard, fg_color="transparent")
        self.videos_frame.pack(fill="both", expand=True, padx=10, pady=(0, 12))

    def on_show(self):
        self.app.run_async(service.list_accounts, on_done=self._fill_accounts)

    def refresh(self):
        self._load_loop()

    def _fill_accounts(self, accounts):
        self.accounts = accounts
        if not accounts:
            self.account_menu.configure(values=["Nenhuma conta"])
            self.account_menu.set("Nenhuma conta")
            return
        labels = [f"{a['name']} (@{a['username']})" for a in accounts]
        self.account_menu.configure(values=labels)
        if self.account_menu.get() not in labels:
            self.account_menu.set(labels[0])
        self._load_loop()

    def _selected_account_id(self):
        label = self.account_menu.get()
        for a in self.accounts:
            if f"{a['name']} (@{a['username']})" == label:
                return a["id"]
        return None

    def _load_loop(self):
        acc_id = self._selected_account_id()
        if not acc_id:
            return
        self.app.run_async(lambda: service.get_loop(acc_id), on_done=self._render_loop)

    def _render_loop(self, loop):
        self.videos = loop.get("videos", [])
        self.interval_entry.delete(0, "end")
        self.interval_entry.insert(0, str(loop.get("interval_seconds", 120)))
        self.caption_box.delete("1.0", "end")
        self.caption_box.insert("1.0", loop.get("caption", ""))
        running = loop.get("is_running")
        if running:
            txt = f"● Loop rodando — {loop.get('total_posts', 0)} posts"
            if loop.get("last_error"):
                txt += f" | {loop['last_error']}"
            self.status_label.configure(text=txt, text_color=theme.SUCCESS)
        else:
            self.status_label.configure(text="Loop parado", text_color=theme.MUTED)
        self._render_videos()

    def _render_videos(self):
        for c in self.videos_frame.winfo_children():
            c.destroy()
        if not self.videos:
            ctk.CTkLabel(self.videos_frame, text="Nenhum vídeo. Clique em + Adicionar vídeos.", text_color=theme.MUTED).pack(pady=24)
            return
        for i, v in enumerate(self.videos):
            row = ctk.CTkFrame(self.videos_frame, fg_color=theme.CARD2, corner_radius=10)
            row.pack(fill="x", padx=6, pady=4)
            ctk.CTkLabel(row, text=f"{i+1}", width=28, text_color=theme.MUTED, font=(theme.FONT, 12, "bold")).pack(side="left", padx=(10, 4), pady=8)
            ctk.CTkLabel(row, text=Path(v["video_path"]).name, text_color=theme.TEXT, font=(theme.FONT, 12), anchor="w").pack(side="left", fill="x", expand=True)
            ctk.CTkButton(row, text="✕", width=30, height=28, fg_color="transparent", hover_color=theme.DANGER_HOVER,
                          text_color=theme.DANGER, command=lambda idx=i: self._remove_video(idx)).pack(side="right", padx=8)

    def _add_videos(self):
        paths = filedialog.askopenfilenames(title="Escolher vídeos", filetypes=[("Vídeos", "*.mp4 *.mov *.m4v *.webm *.avi")])
        if not paths:
            return
        self.app.toast("Importando vídeos...", "info")

        def task():
            added = []
            for p in paths:
                local = service.import_video(p)
                added.append({"video_path": local, "cover_path": "", "caption": ""})
            return added

        def done(added):
            self.videos.extend(added)
            self._render_videos()
            self._save_silent()
            self.app.toast(f"{len(added)} vídeo(s) adicionado(s)", "success")

        self.app.run_async(task, on_done=done)

    def _remove_video(self, idx):
        if 0 <= idx < len(self.videos):
            self.videos.pop(idx)
            self._render_videos()
            self._save_silent()

    def _clear_videos(self):
        self.videos = []
        self._render_videos()
        self._save_silent()

    def _save_silent(self):
        acc_id = self._selected_account_id()
        if not acc_id:
            return
        interval = _to_int(self.interval_entry.get(), 120)
        caption = self.caption_box.get("1.0", "end").strip()
        self.app.run_async(lambda: service.save_loop(acc_id, self.videos, interval, caption))

    def _start(self):
        acc_id = self._selected_account_id()
        if not acc_id:
            self.app.toast("Selecione uma conta", "error")
            return
        if not self.videos:
            self.app.toast("Adicione vídeos antes de iniciar", "error")
            return
        interval = _to_int(self.interval_entry.get(), 120)
        caption = self.caption_box.get("1.0", "end").strip()

        def task():
            service.save_loop(acc_id, self.videos, interval, caption)
            service.set_loop_running(acc_id, True)

        self.app.run_async(task, on_done=lambda _r: (self.app.toast("Loop iniciado", "success"), self._load_loop()))

    def _stop(self):
        acc_id = self._selected_account_id()
        if not acc_id:
            return
        self.app.run_async(lambda: service.set_loop_running(acc_id, False),
                           on_done=lambda _r: (self.app.toast("Loop parado", "info"), self._load_loop()))


def _to_int(value, default):
    try:
        return max(30, int(str(value).strip() or default))
    except ValueError:
        return default
