"""Tela Configurações: integração com o Telegram para logs."""
import customtkinter as ctk

from core import store, telegram
from ui import theme, widgets
from ui.views.base import BaseView


class SettingsView(BaseView):
    def __init__(self, master, app):
        super().__init__(master, app)
        widgets.title(self, "Configurações", size=24).pack(anchor="w")
        widgets.subtitle(self, "Receba todos os logs do sistema no seu Telegram").pack(anchor="w", pady=(0, 16))

        card = widgets.card(self)
        card.pack(fill="x")
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=22, pady=22)

        widgets.title(inner, "Telegram", size=16).pack(anchor="w", pady=(0, 4))
        help_text = (
            "Conversa privada: 1) crie o bot no @BotFather  2) copie o token  "
            "3) envie /start ao seu bot  4) pegue seu Chat ID no @userinfobot\n"
            "Grupo/Canal: 1) adicione o bot ao grupo (como admin)  "
            "2) envie qualquer mensagem no grupo  "
            "3) o Chat ID do grupo começa com -100 (veja no @userinfobot encaminhando uma msg do grupo)"
        )
        widgets.subtitle(inner, help_text).pack(anchor="w", pady=(0, 14))

        widgets.field_label(inner, "Token do bot").pack(anchor="w", pady=(0, 2))
        self.token_entry = widgets.entry(inner, "123456:ABC-DEF...")
        self.token_entry.pack(fill="x", pady=(0, 12))

        widgets.field_label(inner, "Chat ID").pack(anchor="w", pady=(0, 2))
        self.chat_entry = widgets.entry(inner, "ex.: 123456789")
        self.chat_entry.pack(fill="x", pady=(0, 12))

        self.enabled_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(inner, text="Enviar logs para o Telegram", variable=self.enabled_var,
                        fg_color=theme.PRIMARY, hover_color=theme.PRIMARY_HOVER, text_color=theme.TEXT).pack(anchor="w", pady=(4, 16))

        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x")
        widgets.primary_button(row, "Salvar", self._save).pack(side="left")
        widgets.ghost_button(row, "Testar conexão", self._test).pack(side="left", padx=8)

        self.status = ctk.CTkLabel(inner, text="", font=(theme.FONT, 12), text_color=theme.MUTED)
        self.status.pack(anchor="w", pady=(14, 0))

    def on_show(self):
        self.app.run_async(store.get_all_settings, on_done=self._fill)

    def _fill(self, s):
        self.token_entry.delete(0, "end"); self.token_entry.insert(0, s.get("telegram_token", ""))
        self.chat_entry.delete(0, "end"); self.chat_entry.insert(0, s.get("telegram_chat_id", ""))
        self.enabled_var.set(s.get("telegram_enabled") == "1")

    def _save(self):
        token = self.token_entry.get().strip()
        chat = self.chat_entry.get().strip()
        enabled = "1" if self.enabled_var.get() else "0"

        def task():
            store.set_setting("telegram_token", token)
            store.set_setting("telegram_chat_id", chat)
            store.set_setting("telegram_enabled", enabled)

        self.app.run_async(task, on_done=lambda _r: self.app.toast("Configurações salvas", "success"))

    def _test(self):
        token = self.token_entry.get().strip()
        chat = self.chat_entry.get().strip()
        if not token or not chat:
            self.app.toast("Preencha token e chat id", "error")
            return
        self.status.configure(text="Enviando mensagem de teste...", text_color=theme.MUTED)

        def task():
            return telegram.test_connection(token, chat)

        def done(res):
            ok, msg = res
            if ok:
                self.status.configure(text="✅ Mensagem enviada! Verifique seu Telegram.", text_color=theme.SUCCESS)
            else:
                self.status.configure(text=f"❌ Falhou: {msg}", text_color=theme.DANGER)

        self.app.run_async(task, on_done=done)
