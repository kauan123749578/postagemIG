"""Dialog rápido para editar e testar proxy de conta já conectada."""
import customtkinter as ctk

from core import service
from ui import theme, widgets


class ProxyDialog(ctk.CTkToplevel):
    def __init__(self, master, account: dict, on_saved=None):
        super().__init__(master)
        self.account = account
        self.on_saved = on_saved
        self.title(f"Proxy — {account.get('name') or account.get('username')}")
        self.geometry("480x340")
        self.resizable(False, False)
        self.configure(fg_color=theme.BG)
        self.transient(master)
        self.grab_set()

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=20)

        widgets.title(body, "Configurar proxy", size=16).pack(anchor="w")
        widgets.subtitle(
            body,
            f"@{account.get('username') or '—'} — salva sem precisar reconectar",
        ).pack(anchor="w", pady=(0, 12))

        widgets.field_label(body, "Proxy").pack(anchor="w")
        self.proxy_entry = widgets.entry(body, "ip:porta:usuario:senha")
        self.proxy_entry.pack(fill="x", pady=(4, 8))
        if account.get("proxy_url"):
            self.proxy_entry.insert(0, account["proxy_url"])

        widgets.subtitle(
            body,
            "HTTP, HTTPS ou SOCKS5 — ex.: socks5://user:pass@ip:porta",
        ).pack(anchor="w", pady=(0, 8))

        self.status_label = ctk.CTkLabel(
            body, text="", font=(theme.FONT, 12), text_color=theme.MUTED, anchor="w", wraplength=420,
        )
        self.status_label.pack(fill="x", pady=(0, 12))

        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x")
        widgets.ghost_button(row, "Cancelar", self.destroy, width=100).pack(side="right", padx=(8, 0))
        widgets.primary_button(row, "Salvar", self._save, width=110).pack(side="right", padx=(8, 0))
        self.test_btn = widgets.ghost_button(row, "Testar proxy", self._test, width=120)
        self.test_btn.pack(side="right")

        self.after(100, self.proxy_entry.focus_set)

    def _save(self):
        proxy = self.proxy_entry.get().strip()
        acc_id = self.account["id"]

        def task():
            return service.save_account_settings(
                acc_id,
                name=self.account.get("name") or "",
                username=self.account.get("username") or "",
                proxy_url=proxy,
            )

        def done(_r):
            if hasattr(self.master, "toast"):
                self.master.toast("Proxy salvo", "success")
            if self.on_saved:
                self.on_saved()
            self.destroy()

        if hasattr(self.master, "run_async"):
            self.master.run_async(task, on_done=done)
        else:
            task()
            done(None)

    def _test(self):
        proxy = self.proxy_entry.get().strip()
        if not proxy:
            self.status_label.configure(text="Informe um proxy para testar", text_color=theme.DANGER)
            return
        self.test_btn.configure(state="disabled", text="Testando...")
        self.status_label.configure(text="Testando conexão via proxy...", text_color=theme.MUTED)

        def task():
            return service.test_proxy(proxy)

        def done(res):
            self.test_btn.configure(state="normal", text="Testar proxy")
            if res.get("ok"):
                self.status_label.configure(
                    text=res.get("message") or "Proxy OK",
                    text_color=theme.SUCCESS,
                )
            else:
                self.status_label.configure(
                    text=res.get("message") or "Falha no teste",
                    text_color=theme.DANGER,
                )

        def err(exc):
            self.test_btn.configure(state="normal", text="Testar proxy")
            self.status_label.configure(text=str(exc), text_color=theme.DANGER)

        if hasattr(self.master, "run_async"):
            self.master.run_async(task, on_done=done, on_error=err)
        else:
            try:
                done(task())
            except Exception as exc:  # noqa: BLE001
                err(exc)
