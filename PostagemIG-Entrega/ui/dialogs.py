"""Diálogos modais (2FA, confirmação)."""
import customtkinter as ctk

from ui import theme, widgets


class TwoFactorDialog(ctk.CTkToplevel):
    """Popup para digitar o código de verificação em duas etapas."""

    def __init__(self, parent, account_name: str, on_submit):
        super().__init__(parent)
        self.on_submit = on_submit
        self.title("Verificação 2FA")
        self.configure(fg_color=theme.CARD)
        self.geometry("400x300")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        widgets.title(self, "🔐 Verificação em duas etapas", size=17).pack(pady=(26, 6), padx=24)
        widgets.subtitle(
            self,
            f"Digite o código de 6 dígitos da conta @{account_name}\n(app autenticador ou SMS).",
            justify="center",
        ).pack(padx=24)

        self.code_entry = ctk.CTkEntry(
            self,
            placeholder_text="000000",
            height=54,
            justify="center",
            font=(theme.FONT, 24, "bold"),
            corner_radius=12,
            fg_color=theme.CARD2,
            border_color=theme.PRIMARY,
        )
        self.code_entry.pack(fill="x", padx=36, pady=22)
        self.code_entry.bind("<Return>", lambda _e: self._submit())

        self.error_label = ctk.CTkLabel(self, text="", text_color=theme.DANGER, font=(theme.FONT, 11), wraplength=340)
        self.error_label.pack(padx=24)

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=24, pady=(10, 20), side="bottom")
        widgets.ghost_button(btns, "Cancelar", self.destroy).pack(side="left", expand=True, fill="x", padx=(0, 6))
        self.submit_btn = widgets.primary_button(btns, "Confirmar", self._submit)
        self.submit_btn.pack(side="left", expand=True, fill="x", padx=(6, 0))

        self.after(120, self.code_entry.focus)

    def _submit(self):
        code = self.code_entry.get().strip()
        if not code:
            self.set_error("Digite o código.")
            return
        self.submit_btn.configure(state="disabled", text="Conectando...")
        self.error_label.configure(text="")
        self.on_submit(code)

    def set_error(self, msg: str):
        self.error_label.configure(text=msg)
        self.submit_btn.configure(state="normal", text="Confirmar")


def confirm(parent, message: str, title_text: str = "Confirmar") -> bool:
    dlg = ctk.CTkToplevel(parent)
    dlg.title(title_text)
    dlg.configure(fg_color=theme.CARD)
    dlg.geometry("380x180")
    dlg.resizable(False, False)
    dlg.transient(parent)
    dlg.grab_set()
    result = {"ok": False}

    widgets.title(dlg, title_text, size=16).pack(pady=(24, 8), padx=20)
    widgets.subtitle(dlg, message, wraplength=320, justify="center").pack(padx=20)

    btns = ctk.CTkFrame(dlg, fg_color="transparent")
    btns.pack(fill="x", padx=20, pady=20, side="bottom")

    def _yes():
        result["ok"] = True
        dlg.destroy()

    widgets.ghost_button(btns, "Cancelar", dlg.destroy).pack(side="left", expand=True, fill="x", padx=(0, 6))
    widgets.danger_button(btns, "Confirmar", _yes).pack(side="left", expand=True, fill="x", padx=(6, 0))
    dlg.wait_window()
    return result["ok"]
