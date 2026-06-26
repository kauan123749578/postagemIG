"""Tela Mídia: importar e listar vídeos e imagens locais."""
from tkinter import filedialog

import customtkinter as ctk

from core import service
from ui import theme, widgets
from ui.views.base import BaseView


class MediaView(BaseView):
    def __init__(self, master, app):
        super().__init__(master, app)
        widgets.title(self, "Biblioteca de mídia", size=24).pack(anchor="w")
        widgets.subtitle(self, "Vídeos e imagens ficam salvos na pasta data/ do programa").pack(anchor="w", pady=(0, 16))

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", pady=(0, 12))
        widgets.primary_button(bar, "+ Importar vídeos", self._import_videos).pack(side="left")
        widgets.ghost_button(bar, "+ Importar imagens", self._import_images).pack(side="left", padx=8)

        cols = ctk.CTkFrame(self, fg_color="transparent")
        cols.pack(fill="both", expand=True)
        cols.grid_columnconfigure((0, 1), weight=1)
        cols.grid_rowconfigure(0, weight=1)

        vcard = widgets.card(cols)
        vcard.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        widgets.title(vcard, "Vídeos", size=15).pack(anchor="w", padx=16, pady=(14, 6))
        self.videos_frame = ctk.CTkScrollableFrame(vcard, fg_color="transparent")
        self.videos_frame.pack(fill="both", expand=True, padx=8, pady=(0, 12))

        icard = widgets.card(cols)
        icard.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        widgets.title(icard, "Imagens", size=15).pack(anchor="w", padx=16, pady=(14, 6))
        self.images_frame = ctk.CTkScrollableFrame(icard, fg_color="transparent")
        self.images_frame.pack(fill="both", expand=True, padx=8, pady=(0, 12))

    def on_show(self):
        self._reload()

    def _reload(self):
        self.app.run_async(service.list_media, on_done=self._render)

    def _render(self, media):
        self._fill(self.videos_frame, media["videos"], "Nenhum vídeo importado")
        self._fill(self.images_frame, media["images"], "Nenhuma imagem importada")

    def _fill(self, frame, items, empty):
        for c in frame.winfo_children():
            c.destroy()
        if not items:
            ctk.CTkLabel(frame, text=empty, text_color=theme.MUTED).pack(pady=24)
            return
        for it in items:
            row = ctk.CTkFrame(frame, fg_color=theme.CARD2, corner_radius=10)
            row.pack(fill="x", padx=6, pady=4)
            ctk.CTkLabel(row, text=it["name"], text_color=theme.TEXT, font=(theme.FONT, 11), anchor="w").pack(side="left", padx=12, pady=8, fill="x", expand=True)
            ctk.CTkLabel(row, text=f"{it['size_mb']} MB", text_color=theme.MUTED, font=(theme.FONT, 11)).pack(side="right", padx=12)

    def _import_videos(self):
        paths = filedialog.askopenfilenames(title="Importar vídeos", filetypes=[("Vídeos", "*.mp4 *.mov *.m4v *.webm *.avi")])
        self._import(paths, service.import_video)

    def _import_images(self):
        paths = filedialog.askopenfilenames(title="Importar imagens", filetypes=[("Imagens", "*.jpg *.jpeg *.png *.webp")])
        self._import(paths, service.import_image)

    def _import(self, paths, fn):
        if not paths:
            return
        self.app.toast("Importando...", "info")

        def task():
            for p in paths:
                fn(p)

        self.app.run_async(task, on_done=lambda _r: (self.app.toast("Mídia importada", "success"), self._reload()))
