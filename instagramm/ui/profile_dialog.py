"""Dialog para editar foto de perfil e bio de uma conta."""
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from core import service
from core.config import IMAGE_EXTENSIONS
from core.instagram import BIO_MAX_LEN
from ui import theme, widgets


class ProfileDialog(ctk.CTkToplevel):
    def __init__(self, master, account: dict, on_saved=None):
        super().__init__(master)
        self.account = account
        self.on_saved = on_saved
        self.picture_path: str | None = None
        self.title(f"Perfil — @{account.get('username') or account.get('name')}")
        self.geometry("520x420")
        self.resizable(False, False)
        self.configure(fg_color=theme.BG)
        self.transient(master)
        self.grab_set()

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=20)

        widgets.title(body, "Foto e bio", size=16).pack(anchor="w")
        widgets.subtitle(
            body,
            f"@{account.get('username') or '—'} — usa a sessão já conectada",
        ).pack(anchor="w", pady=(0, 12))

        widgets.field_label(body, "Foto de perfil (opcional)").pack(anchor="w")
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", pady=(4, 8))
        self.pic_label = ctk.CTkLabel(
            row, text="Nenhuma foto selecionada", font=(theme.FONT, 12),
            text_color=theme.MUTED, anchor="w",
        )
        self.pic_label.pack(side="left", fill="x", expand=True)
        widgets.ghost_button(row, "Escolher", self._pick, width=100).pack(side="right")

        widgets.field_label(body, f"Bio (até {BIO_MAX_LEN} caracteres)").pack(anchor="w", pady=(8, 2))
        self.bio = ctk.CTkTextbox(
            body, height=110, corner_radius=10,
            fg_color=theme.CARD2, border_color=theme.BORDER, border_width=1,
            text_color=theme.TEXT, font=(theme.FONT, 13),
        )
        self.bio.pack(fill="x", pady=(0, 4))
        self.bio_count = ctk.CTkLabel(
            body, text="0 / 150", font=(theme.FONT, 11), text_color=theme.MUTED, anchor="e",
        )
        self.bio_count.pack(fill="x")
        self.bio.bind("<KeyRelease>", self._on_bio_type)

        self.status = ctk.CTkLabel(
            body, text="", font=(theme.FONT, 12), text_color=theme.MUTED, anchor="w", wraplength=460,
        )
        self.status.pack(fill="x", pady=(8, 12))

        btns = ctk.CTkFrame(body, fg_color="transparent")
        btns.pack(fill="x")
        widgets.ghost_button(btns, "Cancelar", self.destroy, width=100).pack(side="right", padx=(8, 0))
        self.apply_btn = widgets.primary_button(btns, "Aplicar", self._apply, width=120)
        self.apply_btn.pack(side="right")

    def _on_bio_type(self, _event=None):
        text = self.bio.get("1.0", "end").rstrip("\n")
        n = len(text)
        color = theme.DANGER if n > BIO_MAX_LEN else theme.MUTED
        self.bio_count.configure(text=f"{n} / {BIO_MAX_LEN}", text_color=color)

    def _pick(self):
        path = filedialog.askopenfilename(
            title="Foto de perfil",
            filetypes=[("Imagem", "*.jpg *.jpeg *.png *.webp"), ("Todos", "*.*")],
        )
        if not path:
            return
        if Path(path).suffix.lower() not in IMAGE_EXTENSIONS:
            self.status.configure(text="Use jpg/png/webp", text_color=theme.DANGER)
            return
        self.picture_path = path
        self.pic_label.configure(text=Path(path).name, text_color=theme.SUCCESS)

    def _apply(self):
        bio = self.bio.get("1.0", "end").rstrip("\n")
        bio_arg = bio if bio.strip() else None
        if not bio_arg and not self.picture_path:
            self.status.configure(text="Escolha uma foto e/ou digite a bio", text_color=theme.DANGER)
            return
        if bio_arg and len(bio_arg) > BIO_MAX_LEN:
            self.status.configure(text=f"Bio com no máximo {BIO_MAX_LEN} caracteres", text_color=theme.DANGER)
            return

        self.apply_btn.configure(state="disabled", text="Aplicando...")
        self.status.configure(text="Enviando para o Instagram...", text_color=theme.MUTED)
        acc_id = self.account["id"]
        pic = self.picture_path

        def task():
            return service.update_account_profile(
                acc_id,
                biography=bio_arg,
                picture_path=pic,
            )

        def done(res):
            self.apply_btn.configure(state="normal", text="Aplicar")
            if res.get("ok"):
                self.status.configure(text=res.get("message") or "OK", text_color=theme.SUCCESS)
                if hasattr(self.master, "toast"):
                    self.master.toast(res.get("message") or "Perfil atualizado", "success")
                if self.on_saved:
                    self.on_saved()
                self.after(700, self.destroy)
            else:
                self.status.configure(text=res.get("message") or "Falha", text_color=theme.DANGER)

        def err(exc):
            self.apply_btn.configure(state="normal", text="Aplicar")
            self.status.configure(text=str(exc), text_color=theme.DANGER)

        if hasattr(self.master, "run_async"):
            self.master.run_async(task, on_done=done, on_error=err)
        else:
            try:
                done(task())
            except Exception as exc:  # noqa: BLE001
                err(exc)
