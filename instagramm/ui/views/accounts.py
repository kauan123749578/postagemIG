"""Tela de Contas: adicionar, conectar (com 2FA), listar e excluir."""
from tkinter import filedialog

import customtkinter as ctk

from core import service
from core.device import AUTO_DEVICE_KEY, AUTO_DEVICE_LABEL, list_device_choices
from ui import theme, widgets
from ui.dialogs import TwoFactorDialog, confirm
from ui.views.base import BaseView


class AccountsView(BaseView):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.edit_id: int | None = None
        self._device_locked = False
        self._device_choices = list_device_choices()
        self._device_labels = [label for _key, label in self._device_choices]
        self._label_to_key = {label: key for key, label in self._device_choices}
        self._key_to_label = {key: label for key, label in self._device_choices}
        self.grid_columnconfigure(0, weight=0, minsize=380)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 16))
        widgets.title(header, "Contas Instagram", size=24).pack(anchor="w")
        widgets.subtitle(header, "Conecte suas contas via instagrapi — login direto com usuário e senha").pack(anchor="w")

        self._build_form()
        self._build_list()

    # ---------- formulário ----------
    def _build_form(self):
        form = widgets.card(self)
        form.grid(row=1, column=0, sticky="nsew", padx=(0, 16))
        inner = widgets.soft_scrollable(form)
        inner.pack(fill="both", expand=True, padx=16, pady=16)

        self.form_title = widgets.title(inner, "Conectar nova conta", size=16)
        self.form_title.pack(anchor="w", pady=(0, 14))

        self.fields = {}
        self.fields["name"] = self._add_field(inner, "Nome interno", "Ex.: Conta principal")
        self.fields["username"] = self._add_field(inner, "Usuário do Instagram", "sem o @")
        self.fields["password"] = self._add_field(inner, "Senha", "senha da conta", show="•")
        self.password_hint = widgets.subtitle(inner, "A senha fica salva criptografada no seu computador")
        self.password_hint.pack(anchor="w", pady=(2, 0))
        self.fields["proxy_url"] = self._add_field(inner, "Proxy (opcional)", "ip:porta:usuario:senha")
        widgets.subtitle(inner, "Tipos aceitos: HTTP, HTTPS e SOCKS5\nEx.: 185.72.240.96:7132:usuario:senha  ·  http://usuario:senha@ip:porta  ·  socks5://usuario:senha@ip:porta\nRecomendado: proxy residencial/móvel do mesmo país da conta").pack(anchor="w", pady=(2, 8))

        widgets.field_label(inner, "Modelo do celular (fingerprint)").pack(anchor="w", pady=(8, 2))
        self.device_menu = ctk.CTkOptionMenu(
            inner,
            values=self._device_labels,
            fg_color=theme.CARD2,
            button_color=theme.PRIMARY,
            button_hover_color=theme.PRIMARY,
            dropdown_fg_color=theme.CARD2,
            dropdown_hover_color=theme.PRIMARY_SOFT,
            text_color=theme.TEXT,
            font=(theme.FONT, 12),
            height=36,
            corner_radius=10,
        )
        self.device_menu.set(AUTO_DEVICE_LABEL)
        self.device_menu.pack(fill="x")
        self.device_hint = widgets.subtitle(
            inner,
            "Escolha o aparelho que o Meta vai ver no login. Contas já conectadas mantêm o modelo.",
        )
        self.device_hint.pack(anchor="w", pady=(2, 8))

        self.connect_btn = widgets.primary_button(inner, "🔗  Conectar conta", self._save_and_connect)
        self.connect_btn.pack(fill="x", pady=(10, 6))
        self.save_only_btn = widgets.ghost_button(inner, "💾  Salvar proxy e dados (sem conectar)", self._save_settings_only)
        self.save_only_btn.pack(fill="x", pady=(0, 6))
        widgets.ghost_button(inner, "Limpar", self._reset_form).pack(fill="x")

        ctk.CTkFrame(inner, height=1, fg_color=theme.BORDER).pack(fill="x", pady=14)
        widgets.subtitle(inner, "Já tem uma sessão salva? Importe um arquivo session.json:").pack(anchor="w", pady=(0, 6))
        widgets.ghost_button(inner, "📂  Importar session.json", self._import_session).pack(fill="x")

    def _add_field(self, master, label, placeholder, show=None):
        widgets.field_label(master, label).pack(anchor="w", pady=(8, 2))
        e = widgets.entry(master, placeholder, show=show)
        e.pack(fill="x")
        return e

    def _selected_device_key(self) -> str:
        label = self.device_menu.get()
        return self._label_to_key.get(label, AUTO_DEVICE_KEY)

    def _set_device_locked(self, locked: bool, label: str | None = None):
        self._device_locked = locked
        if label:
            self.device_menu.set(label)
        state = "disabled" if locked else "normal"
        try:
            self.device_menu.configure(state=state)
        except Exception:  # noqa: BLE001
            pass
        if locked:
            self.device_hint.configure(
                text="Modelo já atribuído nesta conta — não troca com sessão salva.",
                text_color=theme.PRIMARY,
            )
        else:
            self.device_hint.configure(
                text="Escolha o aparelho que o Meta vai ver no login. Contas já conectadas mantêm o modelo.",
                text_color=theme.MUTED,
            )

    # ---------- lista ----------
    def _build_list(self):
        wrap = widgets.card(self)
        wrap.grid(row=1, column=1, sticky="nsew")
        head = ctk.CTkFrame(wrap, fg_color="transparent")
        head.pack(fill="x", padx=18, pady=(16, 6))
        widgets.title(head, "Contas conectadas", size=16).pack(side="left")
        self.count_label = ctk.CTkLabel(head, text="0", fg_color=theme.CARD2, corner_radius=10, width=34, text_color=theme.MUTED, font=(theme.FONT, 12, "bold"))
        self.count_label.pack(side="right")

        self.list_frame = widgets.soft_scrollable(wrap)
        self.list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 12))

    # ---------- ações ----------
    def on_show(self):
        self._reload()

    def refresh(self):
        self._reload()

    def _reload(self):
        self.app.run_async(service.list_accounts, on_done=self._render_list)

    def _render_list(self, accounts):
        for child in self.list_frame.winfo_children():
            child.destroy()
        self.count_label.configure(text=str(len(accounts)))

        if not accounts:
            ctk.CTkLabel(self.list_frame, text="Nenhuma conta conectada ainda.\nPreencha o formulário e clique em Conectar conta.",
                         text_color=theme.MUTED, font=(theme.FONT, 12), justify="center").pack(pady=40)
            return

        for acc in accounts:
            self._render_card(acc)

    def _render_card(self, acc):
        card = ctk.CTkFrame(self.list_frame, fg_color=theme.CARD2, corner_radius=12, border_width=1, border_color=theme.BORDER)
        card.pack(fill="x", padx=6, pady=5)

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(12, 4))

        initial = (acc["username"] or acc["name"] or "?")[0].upper()
        av = ctk.CTkLabel(top, text=initial, width=42, height=42, corner_radius=12, fg_color=theme.PRIMARY, text_color="#0a0a0a", font=(theme.FONT, 18, "bold"))
        av.pack(side="left")

        info = ctk.CTkFrame(top, fg_color="transparent")
        info.pack(side="left", padx=12, fill="x", expand=True)
        line = ctk.CTkFrame(info, fg_color="transparent")
        line.pack(anchor="w", fill="x")
        ctk.CTkLabel(line, text=acc["name"], font=(theme.FONT, 14, "bold"), text_color=theme.TEXT).pack(side="left")
        widgets.status_pill(line, acc["status"]).pack(side="left", padx=8)
        ctk.CTkLabel(info, text=f"@{acc['username'] or 'sem usuário'}", font=(theme.FONT, 11), text_color=theme.MUTED).pack(anchor="w")

        usage = acc["usage"]
        meta = f"📊 {usage['posts_last_24h']} posts/24h"
        meta += "    " + ("🛡 Proxy" if acc["proxy_url"] else "○ Sem proxy")
        meta += "    " + ("🔑 Senha salva" if acc.get("has_password") else "○ Sem senha")
        ctk.CTkLabel(info, text=meta, font=(theme.FONT, 11), text_color=theme.MUTED).pack(anchor="w", pady=(4, 0))
        if acc.get("device_label"):
            ctk.CTkLabel(
                info,
                text=f"📱 {acc['device_label']}",
                font=(theme.FONT, 11),
                text_color=theme.PRIMARY,
            ).pack(anchor="w", pady=(2, 0))

        if acc["status"] != "healthy" and acc["status_message"]:
            ctk.CTkLabel(card, text=acc["status_message"], font=(theme.FONT, 11), text_color=theme.DANGER, wraplength=520, justify="left").pack(anchor="w", padx=16, pady=(0, 2))

        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.pack(fill="x", padx=14, pady=(6, 12))
        label = "Reconectar" if acc["status"] == "healthy" else "Conectar"
        connect_btn = widgets.primary_button(actions, label, lambda a=acc: self._connect_existing(a))
        connect_btn.configure(height=34, width=110)
        connect_btn.pack(side="left", padx=(0, 6))
        ctk.CTkButton(actions, text="Editar", height=34, width=80, corner_radius=10, fg_color="transparent",
                      border_width=1, border_color=theme.BORDER, text_color=theme.TEXT, hover_color=theme.CARD,
                      command=lambda a=acc: self._edit(a)).pack(side="left", padx=(0, 6))
        ctk.CTkButton(actions, text="Proxy", height=34, width=72, corner_radius=10, fg_color="transparent",
                      border_width=1, border_color=theme.PRIMARY, text_color=theme.PRIMARY, hover_color=theme.PRIMARY_SOFT,
                      command=lambda a=acc: self._edit_proxy(a)).pack(side="left", padx=(0, 6))
        widgets.danger_button(actions, "Excluir", lambda a=acc: self._delete(a)).pack(side="left")

    def _edit_proxy(self, acc):
        from ui.proxy_dialog import ProxyDialog

        ProxyDialog(self.app, acc, on_saved=self._reload)

    def _read_form(self):
        return {
            "name": self.fields["name"].get().strip(),
            "username": self.fields["username"].get().strip(),
            "password": self.fields["password"].get().strip(),
            "proxy_url": self.fields["proxy_url"].get().strip(),
            "device_key": self._selected_device_key(),
        }

    def _save_settings_only(self):
        """Salva proxy e nome sem exigir reconexão."""
        data = self._read_form()
        if not data["name"]:
            self.app.toast("Informe o nome interno", "error")
            return
        if self.edit_id is None:
            self.app.toast("Primeiro conecte a conta ou clique em Editar numa conta existente", "error")
            return

        def task():
            payload = {
                "name": data["name"],
                "username": data["username"],
                "password": data["password"] or None,
                "proxy_url": data["proxy_url"],
            }
            if not self._device_locked:
                payload["device_key"] = data["device_key"]
            service.save_account_settings(self.edit_id, **payload)

        def done(_r):
            self.app.toast("Proxy e dados salvos com sucesso", "success")
            self._reload()

        self.app.run_async(task, on_done=done)

    def _save_and_connect(self):
        data = self._read_form()
        if not data["name"]:
            self.app.toast("Informe o nome interno", "error")
            return
        if self.edit_id is None and not data["password"]:
            self.app.toast("Informe a senha da conta", "error")
            return

        self.connect_btn.configure(state="disabled", text="Conectando...")

        def task():
            if self.edit_id is None:
                acc_id = service.create_account(
                    name=data["name"], username=data["username"], password=data["password"],
                    proxy_url=data["proxy_url"],
                    device_key=data["device_key"],
                )
            else:
                acc_id = self.edit_id
                payload = {
                    "name": data["name"],
                    "username": data["username"],
                    "password": data["password"] or None,
                    "proxy_url": data["proxy_url"],
                }
                if not self._device_locked:
                    payload["device_key"] = data["device_key"]
                service.save_account_settings(acc_id, **payload)
            res = service.connect_account(acc_id, password=data["password"] or None)
            return acc_id, data["username"], res, data["proxy_url"]

        self.app.run_async(task, on_done=self._after_connect, on_error=self._connect_failed)

    def _connect_existing(self, acc):
        self.app.toast("Conectando...", "info")
        self.app.run_async(
            lambda: (acc["id"], acc["username"], service.connect_account(acc["id"]), acc.get("proxy_url", "")),
            on_done=self._after_connect,
        )

    def _after_connect(self, payload):
        acc_id, username, res, proxy_saved = payload
        self.connect_btn.configure(state="normal", text=("💾  Salvar e reconectar" if self.edit_id else "🔗  Conectar conta"))
        status = res.get("status")
        if status == "connected":
            self.app._challenge_dialogs.pop(acc_id, None)
            self.app.toast("Conta conectada com sucesso", "success")
            self._reset_form()
        elif status == "needs_2fa":
            self._open_2fa(acc_id, username)
        elif status == "needs_challenge":
            self._open_challenge(acc_id, username)
        else:
            msg = res.get("message", "Falha ao conectar")
            if proxy_saved and self.edit_id:
                self.app.toast(f"Dados salvos, mas: {msg}", "error")
            else:
                self.app.toast(msg, "error")
            if "expirada" in msg.lower() or "login" in msg.lower():
                self.app.alert_session_expired(username or "conta")
        self._reload()

    def _connect_failed(self, exc):
        self.connect_btn.configure(state="normal", text=("💾  Salvar e reconectar" if self.edit_id else "🔗  Conectar conta"))
        self.app.toast(str(exc), "error")

    def _open_2fa(self, acc_id, username):
        dlg = TwoFactorDialog(self.app, username or "", on_submit=lambda code: self._submit_2fa(dlg, acc_id, username, code))

    def _submit_2fa(self, dlg, acc_id, username, code):
        def task():
            return service.connect_account(acc_id, verification_code=code)

        def done(res):
            self.app._challenge_dialogs.pop(acc_id, None)
            if res.get("status") == "connected":
                self.app.toast("Conta conectada com sucesso", "success")
                dlg.destroy()
                self._reset_form()
            elif res.get("status") == "needs_2fa":
                dlg.set_error("Código incorreto, tente novamente.")
            elif res.get("status") == "needs_challenge":
                dlg.destroy()
                self._open_challenge(acc_id, username)
            else:
                msg = res.get("message", "Falha ao conectar")
                if msg in ("challenge", "'challenge'", "challenge_required"):
                    msg = "Verificação extra do Instagram. Tente conectar de novo."
                dlg.set_error(msg)
            self._reload()

        self.app.run_async(task, on_done=done, on_error=lambda e: dlg.set_error(str(e)))

    def _open_challenge(self, acc_id, username):
        from ui.dialogs import ChallengeDialog

        def on_submit(code):
            self.app.toast("Verificando código...", "info")

            def task():
                return service.retry_after_challenge(acc_id, code)

            def done(res):
                self.app._challenge_dialogs.pop(acc_id, None)
                if res.get("status") == "connected":
                    self.app.toast("Conta conectada com sucesso", "success")
                    self._reset_form()
                elif res.get("status") == "needs_2fa":
                    self._open_2fa(acc_id, username)
                elif res.get("status") == "needs_challenge":
                    self.app.toast("Código incorreto ou expirado. Tente de novo.", "error")
                    self._open_challenge(acc_id, username)
                else:
                    self.app.toast(res.get("message", "Falha na verificação"), "error")
                self._reload()

            self.app.run_async(task, on_done=done)

        dlg = ChallengeDialog(
            self.app, username or "", "e-mail ou SMS",
            on_submit,
            on_cancel=lambda: self.app._challenge_dialogs.pop(acc_id, None),
        )
        self.app._challenge_dialogs[acc_id] = dlg
        dlg.lift()
        dlg.focus_force()

    def _edit(self, acc):
        self.edit_id = acc["id"]
        self.form_title.configure(text="Editar conta")
        self.fields["name"].delete(0, "end"); self.fields["name"].insert(0, acc["name"])
        self.fields["username"].delete(0, "end"); self.fields["username"].insert(0, acc["username"] or "")
        self.fields["password"].delete(0, "end")
        if acc.get("has_password"):
            self.password_hint.configure(
                text="✓ Senha já salva — deixe em branco para manter ou digite uma nova para trocar",
                text_color=theme.SUCCESS,
            )
        else:
            self.password_hint.configure(
                text="Digite a senha para salvar e reconectar quando a sessão expirar",
                text_color=theme.MUTED,
            )
        self.fields["proxy_url"].delete(0, "end"); self.fields["proxy_url"].insert(0, acc["proxy_url"] or "")
        dkey = (acc.get("device_key") or "").strip()
        locked = bool(acc.get("has_session") and dkey)
        label = self._key_to_label.get(dkey) or (acc.get("device_label") or AUTO_DEVICE_LABEL)
        if dkey and label not in self._device_labels:
            self.device_menu.configure(values=self._device_labels + [label])
        self._set_device_locked(locked, label if dkey else AUTO_DEVICE_LABEL)
        self.connect_btn.configure(text="💾  Salvar e reconectar")

    def _delete(self, acc):
        if not confirm(self.app, f"Excluir a conta '{acc['name']}'?", "Excluir conta"):
            return
        self.app.run_async(lambda: service.delete_account(acc["id"]), on_done=lambda _r: (self.app.toast("Conta excluída", "success"), self._reload()))

    def _import_session(self):
        path = filedialog.askopenfilename(title="Selecionar session.json", filetypes=[("Sessão JSON", "*.json")])
        if not path:
            return
        name = self.fields["name"].get().strip()
        proxy = self.fields["proxy_url"].get().strip()
        self.app.toast("Importando sessão...", "info")

        def task():
            return service.import_session(name, path, proxy)

        def done(res):
            if res.get("status") == "connected":
                self.app.toast(res.get("message", "Sessão importada"), "success")
                self._reset_form()
            else:
                self.app.toast(res.get("message", "Falha ao importar"), "error")
            self._reload()

        self.app.run_async(task, on_done=done)

    def _reset_form(self):
        self.edit_id = None
        self.form_title.configure(text="Conectar nova conta")
        for _key, e in self.fields.items():
            e.delete(0, "end")
        self.password_hint.configure(text="A senha fica salva criptografada no seu computador", text_color=theme.MUTED)
        self.device_menu.configure(values=self._device_labels)
        self._set_device_locked(False, AUTO_DEVICE_LABEL)
        self.connect_btn.configure(text="🔗  Conectar conta")
