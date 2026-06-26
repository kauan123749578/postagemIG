"""Tela Publicar: postar um Reel imediatamente."""
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from core import service
from ui import theme, widgets
from ui.views.base import BaseView


class PublishView(BaseView):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.accounts = []
        self.video_path = None
        self.cover_path = None

        widgets.title(self, "Publicar Reel", size=24).pack(anchor="w")
        widgets.subtitle(self, "Envie um vídeo do seu computador direto para o Instagram").pack(anchor="w", pady=(0, 16))

        card = widgets.card(self)
        card.pack(fill="both", expand=True)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=22, pady=22)

        widgets.field_label(inner, "Conta").pack(anchor="w", pady=(0, 2))
        self.account_menu = ctk.CTkOptionMenu(inner, values=["Carregando..."], fg_color=theme.CARD2,
                                              button_color=theme.PRIMARY, button_hover_color=theme.PRIMARY_HOVER,
                                              dropdown_fg_color=theme.CARD2, height=40)
        self.account_menu.pack(fill="x", pady=(0, 12))

        widgets.field_label(inner, "Vídeo (.mp4)").pack(anchor="w", pady=(0, 2))
        vrow = ctk.CTkFrame(inner, fg_color="transparent")
        vrow.pack(fill="x", pady=(0, 12))
        self.video_label = ctk.CTkLabel(vrow, text="Nenhum vídeo selecionado", text_color=theme.MUTED, font=(theme.FONT, 12), anchor="w")
        self.video_label.pack(side="left", fill="x", expand=True)
        widgets.ghost_button(vrow, "Escolher vídeo", self._pick_video).pack(side="right")

        widgets.field_label(inner, "Capa / thumbnail (opcional)").pack(anchor="w", pady=(0, 2))
        crow = ctk.CTkFrame(inner, fg_color="transparent")
        crow.pack(fill="x", pady=(0, 12))
        self.cover_label = ctk.CTkLabel(crow, text="Capa automática do vídeo", text_color=theme.MUTED, font=(theme.FONT, 12), anchor="w")
        self.cover_label.pack(side="left", fill="x", expand=True)
        widgets.ghost_button(crow, "Escolher capa", self._pick_cover).pack(side="right")

        widgets.field_label(inner, "Legenda").pack(anchor="w", pady=(0, 2))
        self.caption_box = ctk.CTkTextbox(inner, height=120, fg_color=theme.CARD2, border_color=theme.BORDER, border_width=1, corner_radius=10)
        self.caption_box.pack(fill="x", pady=(0, 16))

        self.publish_btn = widgets.primary_button(inner, "🚀  Publicar Reel agora", self._publish)
        self.publish_btn.pack(fill="x")

    def on_show(self):
        self.app.run_async(service.list_accounts, on_done=self._fill_accounts)

    def _fill_accounts(self, accounts):
        self.accounts = [a for a in accounts if a["status"] == "healthy"]
        if not self.accounts:
            self.account_menu.configure(values=["Nenhuma conta conectada"])
            self.account_menu.set("Nenhuma conta conectada")
            return
        labels = [f"{a['name']} (@{a['username']})" for a in self.accounts]
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

    def _pick_cover(self):
        path = filedialog.askopenfilename(title="Escolher capa", filetypes=[("Imagens", "*.jpg *.jpeg *.png *.webp")])
        if path:
            self.cover_path = path
            self.cover_label.configure(text=Path(path).name, text_color=theme.TEXT)

    def _publish(self):
        acc_id = self._selected_account_id()
        if not acc_id:
            self.app.toast("Selecione uma conta conectada", "error")
            return
        if not self.video_path:
            self.app.toast("Escolha um vídeo", "error")
            return
        caption = self.caption_box.get("1.0", "end").strip()
        self.publish_btn.configure(state="disabled", text="Publicando... (pode demorar)")

        def task():
            return service.post_reel_now(acc_id, self.video_path, caption, self.cover_path)

        def done(res):
            self.publish_btn.configure(state="normal", text="🚀  Publicar Reel agora")
            if res.get("ok"):
                self.app.toast("Reel publicado com sucesso!", "success")
            else:
                self.app.toast(res.get("message", "Falha ao publicar"), "error")

        def err(exc):
            self.publish_btn.configure(state="normal", text="🚀  Publicar Reel agora")
            self.app.toast(str(exc), "error")

        self.app.run_async(task, on_done=done, on_error=err)
