"""Tela Agendamentos: agenda Reels para um horário futuro."""
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from core import service
from ui import theme, widgets
from ui.dialogs import confirm
from ui.views.base import BaseView


class ScheduleView(BaseView):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.accounts = []
        self.video_path = None

        widgets.title(self, "Agendamentos", size=24).pack(anchor="w")
        widgets.subtitle(self, "Programe Reels para publicar automaticamente em um horário").pack(anchor="w", pady=(0, 16))

        self.grid_columnconfigure(0, weight=0, minsize=380)
        self.grid_columnconfigure(1, weight=1)

        form = widgets.card(self)
        form.pack_propagate(False)
        form.configure(width=360)
        form.place(x=0, y=64, relheight=0.86)
        inner = ctk.CTkFrame(form, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=18, pady=18)

        widgets.field_label(inner, "Conta").pack(anchor="w", pady=(0, 2))
        self.account_menu = ctk.CTkOptionMenu(inner, values=["Carregando..."], fg_color=theme.CARD2,
                                              button_color=theme.PRIMARY, button_hover_color=theme.PRIMARY_HOVER,
                                              dropdown_fg_color=theme.CARD2, height=40)
        self.account_menu.pack(fill="x", pady=(0, 12))

        vrow = ctk.CTkFrame(inner, fg_color="transparent")
        vrow.pack(fill="x", pady=(0, 12))
        self.video_label = ctk.CTkLabel(vrow, text="Nenhum vídeo", text_color=theme.MUTED, font=(theme.FONT, 12), anchor="w")
        self.video_label.pack(side="left", fill="x", expand=True)
        widgets.ghost_button(vrow, "Vídeo", self._pick_video).pack(side="right")

        widgets.field_label(inner, "Data e hora (DD/MM/AAAA HH:MM)").pack(anchor="w", pady=(0, 2))
        self.when_entry = widgets.entry(inner, datetime.now().strftime("%d/%m/%Y %H:%M"))
        self.when_entry.pack(fill="x", pady=(0, 12))

        widgets.field_label(inner, "Legenda").pack(anchor="w", pady=(0, 2))
        self.caption_box = ctk.CTkTextbox(inner, height=80, fg_color=theme.CARD2, border_color=theme.BORDER, border_width=1, corner_radius=10)
        self.caption_box.pack(fill="x", pady=(0, 14))

        widgets.primary_button(inner, "⏰  Agendar Reel", self._add).pack(fill="x")

        listcard = widgets.card(self)
        listcard.place(relx=0.32, y=64, relwidth=0.68, relheight=0.86)
        widgets.title(listcard, "Agendados", size=15).pack(anchor="w", padx=18, pady=(14, 6))
        self.list_frame = ctk.CTkScrollableFrame(listcard, fg_color="transparent")
        self.list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 12))

    def on_show(self):
        self.app.run_async(service.list_accounts, on_done=self._fill_accounts)
        self._reload()

    def refresh(self):
        self._reload()

    def _fill_accounts(self, accounts):
        self.accounts = [a for a in accounts if a["status"] == "healthy"]
        labels = [f"{a['name']} (@{a['username']})" for a in self.accounts] or ["Nenhuma conta conectada"]
        self.account_menu.configure(values=labels)
        self.account_menu.set(labels[0])

    def _selected_account_id(self):
        label = self.account_menu.get()
        for a in self.accounts:
            if f"{a['name']} (@{a['username']})" == label:
                return a["id"]
        return None

    def _pick_video(self):
        path = filedialog.askopenfilename(title="Escolher vídeo", filetypes=[("Vídeos", "*.mp4 *.mov *.m4v *.webm *.avi")])
        if path:
            self.video_path = path
            self.video_label.configure(text=Path(path).name, text_color=theme.TEXT)

    def _add(self):
        acc_id = self._selected_account_id()
        if not acc_id:
            self.app.toast("Selecione uma conta conectada", "error")
            return
        if not self.video_path:
            self.app.toast("Escolha um vídeo", "error")
            return
        try:
            when_local = datetime.strptime(self.when_entry.get().strip(), "%d/%m/%Y %H:%M")
        except ValueError:
            self.app.toast("Data inválida. Use DD/MM/AAAA HH:MM", "error")
            return
        when_utc = when_local.astimezone().astimezone(timezone.utc)
        caption = self.caption_box.get("1.0", "end").strip()

        def task():
            local = service.import_video(self.video_path)
            service.add_scheduled(acc_id, local, when_utc, caption)

        def done(_r):
            self.app.toast("Reel agendado", "success")
            self.video_path = None
            self.video_label.configure(text="Nenhum vídeo", text_color=theme.MUTED)
            self.caption_box.delete("1.0", "end")
            self._reload()

        self.app.run_async(task, on_done=done)

    def _reload(self):
        self.app.run_async(service.list_scheduled, on_done=self._render)

    def _render(self, items):
        for c in self.list_frame.winfo_children():
            c.destroy()
        if not items:
            ctk.CTkLabel(self.list_frame, text="Nenhum agendamento.", text_color=theme.MUTED).pack(pady=30)
            return
        for s in items:
            row = ctk.CTkFrame(self.list_frame, fg_color=theme.CARD2, corner_radius=10)
            row.pack(fill="x", padx=6, pady=4)
            info = ctk.CTkFrame(row, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True, padx=12, pady=8)
            ctk.CTkLabel(info, text=f"{s['account']} — {s['video_name']}", text_color=theme.TEXT, font=(theme.FONT, 12, "bold"), anchor="w").pack(anchor="w")
            when = s["scheduled_at"].replace("T", " ")[:16] if s["scheduled_at"] else ""
            ctk.CTkLabel(info, text=f"{when}  ·  {_status_label(s['status'])}", text_color=theme.MUTED, font=(theme.FONT, 11), anchor="w").pack(anchor="w")
            if s["status"] == "pending":
                ctk.CTkButton(row, text="Cancelar", width=80, height=28, fg_color="transparent", border_width=1,
                              border_color=theme.BORDER, text_color=theme.DANGER, hover_color=theme.DANGER_HOVER,
                              command=lambda i=s["id"]: self._cancel(i)).pack(side="right", padx=10)

    def _cancel(self, post_id):
        self.app.run_async(lambda: service.cancel_scheduled(post_id),
                           on_done=lambda _r: (self.app.toast("Agendamento cancelado", "info"), self._reload()))


def _status_label(status):
    return {"pending": "Pendente", "posted": "Publicado", "error": "Erro", "cancelled": "Cancelado"}.get(status, status)
