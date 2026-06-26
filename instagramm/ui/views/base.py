import customtkinter as ctk

from ui import theme


class BaseView(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=theme.BG)
        self.app = app

    def on_show(self):
        """Chamado toda vez que a tela aparece."""

    def refresh(self):
        """Atualização vinda dos workers (roda na thread da UI)."""
