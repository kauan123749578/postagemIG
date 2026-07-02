"""Tela Editar perfil: bio, link e foto de perfil."""
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from core import service
from ui import theme, widgets
from ui.views.base import BaseView


class ProfileView(BaseView):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.accounts = []
        self.picture_path = None
        self.preselect_account_id: int | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # cabeçalho fixo com botão salvar sempre visível
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.grid_columnconfigure(0, weight=1)

        titles = ctk.CTkFrame(header, fg_color="transparent")
        titles.grid(row=0, column=0, sticky="w")
        widgets.title(titles, "Editar perfil", size=24).pack(anchor="w")
        widgets.subtitle(titles, "Bio, link na bio e foto de perfil").pack(anchor="w")

        self.save_top_btn = widgets.primary_button(header, "💾  Salvar no Instagram", self._save, height=44, width=200)
        self.save_top_btn.grid(row=0, column=1, sticky="e", padx=(12, 0))

        # formulário rolável
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.grid(row=1, column=0, sticky="nsew", pady=(0, 10))

        card, body = widgets.section(
            scroll,
            "Perfil da conta",
            "Selecione a conta e clique em Carregar perfil",
            icon="✏️",
        )
        card.pack(fill="x")

        widgets.field_label(body, "Conta").pack(anchor="w", pady=(0, 2))
        acc_row = ctk.CTkFrame(body, fg_color="transparent")
        acc_row.pack(fill="x", pady=(0, 12))
        self.account_menu = ctk.CTkOptionMenu(
            acc_row, values=["Carregando..."], command=lambda _v: self._clear_form(),
            fg_color=theme.CARD2, button_color=theme.PRIMARY,
            button_hover_color=theme.PRIMARY_HOVER, dropdown_fg_color=theme.CARD2, height=40,
        )
        self.account_menu.pack(side="left", fill="x", expand=True)
        widgets.ghost_button(acc_row, "Carregar perfil", self._load_profile, width=140).pack(side="left", padx=(8, 0))

        widgets.field_label(body, "Nome exibido").pack(anchor="w", pady=(0, 2))
        self.name_entry = widgets.entry(body, "Nome do perfil")
        self.name_entry.pack(fill="x", pady=(0, 12))

        widgets.field_label(body, "Bio").pack(anchor="w", pady=(0, 2))
        self.bio_box = ctk.CTkTextbox(
            body, height=90, fg_color=theme.CARD2, border_color=theme.BORDER,
            border_width=1, corner_radius=10, text_color=theme.TEXT,
        )
        self.bio_box.pack(fill="x", pady=(0, 12))

        widgets.field_label(body, "Link na bio").pack(anchor="w", pady=(0, 2))
        self.link_entry = widgets.entry(body, "https://seusite.com")
        self.link_entry.pack(fill="x", pady=(0, 12))

        widgets.field_label(body, "Foto de perfil").pack(anchor="w", pady=(0, 2))
        pic_row = ctk.CTkFrame(body, fg_color="transparent")
        pic_row.pack(fill="x", pady=(0, 8))
        self.pic_label = ctk.CTkLabel(pic_row, text="Nenhuma foto selecionada", text_color=theme.MUTED, font=(theme.FONT, 12), anchor="w")
        self.pic_label.pack(side="left", fill="x", expand=True)
        widgets.ghost_button(pic_row, "Escolher foto", self._pick_picture).pack(side="right")

        self.status = ctk.CTkLabel(body, text="", font=(theme.FONT, 12), text_color=theme.MUTED, wraplength=700, justify="left")
        self.status.pack(anchor="w", pady=(8, 0))

        # rodapé fixo com segundo botão salvar
        footer = ctk.CTkFrame(self, fg_color=theme.CARD, corner_radius=14, border_width=1, border_color=theme.BORDER)
        footer.grid(row=2, column=0, sticky="ew")
        widgets.primary_button(footer, "💾  Salvar alterações no Instagram", self._save).pack(fill="x", padx=16, pady=14)

    def on_show(self):
        self.app.run_async(service.list_accounts, on_done=self._fill_accounts)

    def select_account(self, account_id: int):
        """Abre já com a conta selecionada (vindo da tela Contas)."""
        self.preselect_account_id = account_id
        self.app.run_async(service.list_accounts, on_done=self._fill_accounts)

    def _fill_accounts(self, accounts):
        self.accounts = [a for a in accounts if a["status"] == "healthy"]
        if not self.accounts:
            self.account_menu.configure(values=["Nenhuma conta conectada"])
            self.account_menu.set("Nenhuma conta conectada")
            return
        labels = [f"{a['name']} (@{a['username']})" for a in self.accounts]
        self.account_menu.configure(values=labels)
        target = None
        if self.preselect_account_id:
            for a in self.accounts:
                if a["id"] == self.preselect_account_id:
                    target = f"{a['name']} (@{a['username']})"
                    break
            self.preselect_account_id = None
        if target and target in labels:
            self.account_menu.set(target)
            self._load_profile()
        elif self.account_menu.get() not in labels:
            self.account_menu.set(labels[0])

    def _selected_account_id(self):
        label = self.account_menu.get()
        for a in self.accounts:
            if f"{a['name']} (@{a['username']})" == label:
                return a["id"]
        return None

    def _clear_form(self):
        self.name_entry.delete(0, "end")
        self.bio_box.delete("1.0", "end")
        self.link_entry.delete(0, "end")
        self.picture_path = None
        self.pic_label.configure(text="Nenhuma foto selecionada", text_color=theme.MUTED)
        self.status.configure(text="")

    def _load_profile(self):
        acc_id = self._selected_account_id()
        if not acc_id:
            self.app.toast("Selecione uma conta conectada", "error")
            return
        self.status.configure(text="Carregando perfil...", text_color=theme.MUTED)

        def done(res):
            if not res.get("ok"):
                self.status.configure(text=f"❌ {res.get('message', 'Erro')}", text_color=theme.DANGER)
                if "expirada" in (res.get("message") or "").lower():
                    self.app.toast("Sessão expirada — reconecte em Contas", "error")
                return
            self.name_entry.delete(0, "end")
            self.name_entry.insert(0, res.get("full_name", ""))
            self.bio_box.delete("1.0", "end")
            self.bio_box.insert("1.0", res.get("biography", ""))
            self.link_entry.delete(0, "end")
            self.link_entry.insert(0, res.get("external_url", ""))
            self.status.configure(text=f"✅ Perfil de @{res.get('username', '')} carregado", text_color=theme.SUCCESS)

        self.app.run_async(lambda: service.get_profile(acc_id), on_done=done)

    def _pick_picture(self):
        path = filedialog.askopenfilename(
            title="Foto de perfil",
            filetypes=[("Imagens", "*.jpg *.jpeg *.png *.webp")],
        )
        if not path:
            return
        self.picture_path = path
        self.pic_label.configure(text=Path(path).name, text_color=theme.TEXT)

    def _save(self):
        acc_id = self._selected_account_id()
        if not acc_id:
            self.app.toast("Selecione uma conta conectada", "error")
            return

        biography = self.bio_box.get("1.0", "end").strip()
        external_url = self.link_entry.get().strip()
        full_name = self.name_entry.get().strip()
        picture = self.picture_path

        if not any([biography, external_url, full_name, picture]):
            self.app.toast("Preencha ao menos um campo ou escolha uma foto", "error")
            return

        self.save_top_btn.configure(state="disabled", text="Salvando...")
        self.status.configure(text="Salvando no Instagram...", text_color=theme.MUTED)

        def task():
            return service.update_profile(
                acc_id,
                biography=biography,
                external_url=external_url,
                full_name=full_name,
                picture_path=picture,
            )

        def done(res):
            self.save_top_btn.configure(state="normal", text="💾  Salvar no Instagram")
            if res.get("ok"):
                self.status.configure(text="✅ Perfil atualizado!", text_color=theme.SUCCESS)
                self.app.toast("Perfil atualizado", "success")
                self.picture_path = None
                self.pic_label.configure(text="Nenhuma foto selecionada", text_color=theme.MUTED)
            else:
                msg = res.get("message", "Erro")
                self.status.configure(text=f"❌ {msg}", text_color=theme.DANGER)
                self.app.toast(msg, "error")

        self.app.run_async(task, on_done=done)
