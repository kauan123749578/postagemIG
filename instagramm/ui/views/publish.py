"""Tela Publicar: postar Reel ou Story imediatamente."""
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
        self.media_path = None
        self.cover_path = None
        self.mode = "reel"

        widgets.title(self, "Publicar", size=24).pack(anchor="w")
        widgets.subtitle(self, "Envie Reels ou Stories do seu computador direto para o Instagram").pack(anchor="w", pady=(0, 16))

        card = widgets.card(self)
        card.pack(fill="both", expand=True)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=22, pady=22)

        widgets.field_label(inner, "Tipo").pack(anchor="w", pady=(0, 2))
        self.mode_seg = ctk.CTkSegmentedButton(
            inner, values=["Reel", "Story"], command=self._on_mode_change,
            fg_color=theme.CARD2, selected_color=theme.PRIMARY, selected_hover_color=theme.PRIMARY_HOVER,
            unselected_color=theme.CARD2, text_color=theme.TEXT,
        )
        self.mode_seg.set("Reel")
        self.mode_seg.pack(anchor="w", pady=(0, 12))

        widgets.field_label(inner, "Conta").pack(anchor="w", pady=(0, 2))
        self.account_menu = ctk.CTkOptionMenu(inner, values=["Carregando..."], fg_color=theme.CARD2,
                                              button_color=theme.PRIMARY, button_hover_color=theme.PRIMARY_HOVER,
                                              dropdown_fg_color=theme.CARD2, height=40)
        self.account_menu.pack(fill="x", pady=(0, 12))

        self.media_label_field = widgets.field_label(inner, "Vídeo (.mp4)")
        self.media_label_field.pack(anchor="w", pady=(0, 2))
        vrow = ctk.CTkFrame(inner, fg_color="transparent")
        vrow.pack(fill="x", pady=(0, 12))
        self.media_label = ctk.CTkLabel(vrow, text="Nenhum arquivo selecionado", text_color=theme.MUTED, font=(theme.FONT, 12), anchor="w")
        self.media_label.pack(side="left", fill="x", expand=True)
        self.pick_media_btn = widgets.ghost_button(vrow, "Escolher vídeo", self._pick_media)
        self.pick_media_btn.pack(side="right")

        self.cover_field = widgets.field_label(inner, "Capa / thumbnail (opcional)")
        self.cover_field.pack(anchor="w", pady=(0, 2))
        self.cover_row = ctk.CTkFrame(inner, fg_color="transparent")
        self.cover_row.pack(fill="x", pady=(0, 12))
        self.cover_label = ctk.CTkLabel(self.cover_row, text="Capa automática do vídeo", text_color=theme.MUTED, font=(theme.FONT, 12), anchor="w")
        self.cover_label.pack(side="left", fill="x", expand=True)
        widgets.ghost_button(self.cover_row, "Escolher capa", self._pick_cover).pack(side="right")

        self.link_field = widgets.field_label(inner, "Link do Story (opcional)")
        self.link_entry = widgets.entry(inner, "https://seusite.com")

        self.caption_field = widgets.field_label(inner, "Legenda")
        self.caption_field.pack(anchor="w", pady=(0, 2))
        self.caption_box = ctk.CTkTextbox(inner, height=120, fg_color=theme.CARD2, border_color=theme.BORDER, border_width=1, corner_radius=10)
        self.caption_box.pack(fill="x", pady=(0, 16))

        self.publish_btn = widgets.primary_button(inner, "🚀  Publicar Reel agora", self._publish)
        self.publish_btn.pack(fill="x")

    def on_show(self):
        self.app.run_async(service.list_accounts, on_done=self._fill_accounts)

    def _on_mode_change(self, value):
        self.mode = "story" if value == "Story" else "reel"
        self.media_path = None
        self.cover_path = None
        self.media_label.configure(text="Nenhum arquivo selecionado", text_color=theme.MUTED)
        self.cover_label.configure(text="Capa automática do vídeo", text_color=theme.MUTED)
        if self.mode == "story":
            self.media_label_field.configure(text="FOTO OU VÍDEO")
            self.pick_media_btn.configure(text="Escolher mídia")
            self.cover_field.pack_forget()
            self.cover_row.pack_forget()
            self.link_field.pack(anchor="w", pady=(0, 2), before=self.caption_field)
            self.link_entry.pack(fill="x", pady=(0, 12), before=self.caption_field)
            self.publish_btn.configure(text="📸  Publicar Story agora")
        else:
            self.media_label_field.configure(text="VÍDEO (.MP4)")
            self.pick_media_btn.configure(text="Escolher vídeo")
            self.link_field.pack_forget()
            self.link_entry.pack_forget()
            self.cover_field.pack(anchor="w", pady=(0, 2), before=self.caption_field)
            self.cover_row.pack(fill="x", pady=(0, 12), before=self.caption_field)
            self.publish_btn.configure(text="🚀  Publicar Reel agora")

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

    def _pick_media(self):
        if self.mode == "story":
            path = filedialog.askopenfilename(
                title="Escolher foto ou vídeo para Story",
                filetypes=[("Mídia", "*.jpg *.jpeg *.png *.webp *.mp4 *.mov *.m4v *.webm")],
            )
        else:
            path = filedialog.askopenfilename(
                title="Escolher vídeo", filetypes=[("Vídeos", "*.mp4 *.mov *.m4v *.webm *.avi")],
            )
        if path:
            self.media_path = path
            self.media_label.configure(text=Path(path).name, text_color=theme.TEXT)

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
        if not self.media_path:
            label = "mídia" if self.mode == "story" else "vídeo"
            self.app.toast(f"Escolha um(a) {label}", "error")
            return
        caption = self.caption_box.get("1.0", "end").strip()
        busy = "Publicando Story..." if self.mode == "story" else "Publicando Reel... (pode demorar)"
        self.publish_btn.configure(state="disabled", text=busy)

        link = self.link_entry.get().strip() if self.mode == "story" else ""

        def task():
            if self.mode == "story":
                return service.post_story_now(acc_id, self.media_path, caption, link)
            return service.post_reel_now(acc_id, self.media_path, caption, self.cover_path)

        def done(res):
            btn = "📸  Publicar Story agora" if self.mode == "story" else "🚀  Publicar Reel agora"
            self.publish_btn.configure(state="normal", text=btn)
            if res.get("ok"):
                msg = "Story publicado com sucesso!" if self.mode == "story" else "Reel publicado com sucesso!"
                self.app.toast(msg, "success")
            else:
                self.app.toast(res.get("message", "Falha ao publicar"), "error")

        def err(exc):
            btn = "📸  Publicar Story agora" if self.mode == "story" else "🚀  Publicar Reel agora"
            self.publish_btn.configure(state="normal", text=btn)
            self.app.toast(str(exc), "error")

        self.app.run_async(task, on_done=done, on_error=err)
