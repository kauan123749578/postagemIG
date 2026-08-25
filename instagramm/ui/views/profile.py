"""Tela Perfil em massa: fotos + bios em várias contas."""
from __future__ import annotations

from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from core import service
from core.config import IMAGE_EXTENSIONS
from core.instagram import BIO_MAX_LEN
from ui import theme, widgets
from ui.views.base import BaseView


class ProfileView(BaseView):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.pictures: list[str] = []
        self._account_vars: dict[int, ctk.BooleanVar] = {}

        widgets.title(self, "Perfil em massa", size=24).pack(anchor="w")
        widgets.subtitle(
            self,
            "Suba várias fotos: cada conta recebe uma (na ordem). Bio igual pra todas ou uma por linha.",
        ).pack(anchor="w", pady=(0, 12))

        self.scroll = widgets.soft_scrollable(self, speed=0.28)
        self.scroll.pack(fill="both", expand=True)

        # Fotos
        pcard, pbody = widgets.section(
            self.scroll, "Fotos de perfil", "Uma foto por conta (ciclo se sobrar conta)", icon="🖼️",
        )
        pcard.pack(fill="x", pady=(0, 12))
        row = ctk.CTkFrame(pbody, fg_color="transparent")
        row.pack(fill="x", pady=(0, 4))
        widgets.primary_button(row, "＋  Selecionar fotos", self._pick_pics, width=180).pack(side="left")
        widgets.ghost_button(row, "Limpar", self._clear_pics, width=100).pack(side="left", padx=(8, 0))
        self.pics_label = ctk.CTkLabel(
            pbody, text="Nenhuma foto selecionada", font=(theme.FONT, 12),
            text_color=theme.DANGER, anchor="w",
        )
        self.pics_label.pack(fill="x", pady=(4, 0))

        # Bio
        bcard, bbody = widgets.section(
            self.scroll, "Bio", f"Máximo {BIO_MAX_LEN} caracteres por bio", icon="✍️",
        )
        bcard.pack(fill="x", pady=(0, 12))
        self.bio_mode = ctk.StringVar(value="shared")
        ctk.CTkRadioButton(
            bbody, text="Mesma bio para todas as contas",
            variable=self.bio_mode, value="shared",
            font=(theme.FONT, 12), text_color=theme.TEXT,
            fg_color=theme.PRIMARY, hover_color=theme.PRIMARY_HOVER,
        ).pack(anchor="w", pady=(0, 4))
        ctk.CTkRadioButton(
            bbody, text="Uma bio por linha (ordem das contas selecionadas)",
            variable=self.bio_mode, value="lines",
            font=(theme.FONT, 12), text_color=theme.TEXT,
            fg_color=theme.PRIMARY, hover_color=theme.PRIMARY_HOVER,
        ).pack(anchor="w", pady=(0, 8))
        self.bio = ctk.CTkTextbox(
            bbody, height=120, corner_radius=10,
            fg_color=theme.CARD2, border_color=theme.BORDER, border_width=1,
            text_color=theme.TEXT, font=(theme.FONT, 13),
        )
        self.bio.pack(fill="x")
        ctk.CTkLabel(
            bbody,
            text="Deixe vazio se quiser mudar só a foto.",
            font=(theme.FONT, 11), text_color=theme.MUTED,
        ).pack(anchor="w", pady=(4, 0))

        # Contas
        acard, abody = widgets.section(
            self.scroll, "Contas", "Só contas conectadas recebem a alteração", icon="👥",
        )
        acard.pack(fill="x", pady=(0, 12))
        self.accounts_count = ctk.CTkLabel(
            abody, text="0 selecionada(s)", font=(theme.FONT, 12), text_color=theme.MUTED, anchor="w",
        )
        self.accounts_count.pack(fill="x", pady=(0, 6))
        btns = ctk.CTkFrame(abody, fg_color="transparent")
        btns.pack(fill="x", pady=(0, 8))
        widgets.ghost_button(btns, "Selecionar todas", self._select_all, width=140, height=34).pack(side="left")
        widgets.ghost_button(btns, "Só ativas", self._select_healthy, width=110, height=34).pack(side="left", padx=(8, 0))
        widgets.ghost_button(btns, "Limpar", self._clear_accounts, width=90, height=34).pack(side="left", padx=(8, 0))
        self.accounts_list = ctk.CTkFrame(abody, fg_color="transparent")
        self.accounts_list.pack(fill="x")

        self.apply_btn = widgets.primary_button(
            self.scroll, "Aplicar foto e bio nas contas", self._apply, height=48,
        )
        self.apply_btn.pack(fill="x", pady=(4, 28))

    # ---------- pics ----------
    def _pick_pics(self):
        paths = filedialog.askopenfilenames(
            title="Fotos de perfil",
            filetypes=[("Imagem", "*.jpg *.jpeg *.png *.webp"), ("Todos", "*.*")],
        )
        if not paths:
            return

        def work():
            saved = []
            for p in paths:
                if Path(p).suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                saved.append(service.import_image(p))
            return saved

        def done(saved):
            self.pictures.extend(saved)
            self._refresh_pics()
            self.app.toast(f"{len(saved)} foto(s) adicionada(s)", "success")

        self.app.run_async(work, on_done=done)

    def _clear_pics(self):
        self.pictures = []
        self._refresh_pics()

    def _refresh_pics(self):
        n = len(self.pictures)
        if n == 0:
            self.pics_label.configure(text="Nenhuma foto selecionada", text_color=theme.DANGER)
        else:
            names = ", ".join(Path(p).name for p in self.pictures[:4])
            extra = f" (+{n - 4})" if n > 4 else ""
            self.pics_label.configure(text=f"{n} foto(s): {names}{extra}", text_color=theme.SUCCESS)

    # ---------- accounts ----------
    def _reload_accounts(self):
        for w in self.accounts_list.winfo_children():
            w.destroy()
        self._account_vars.clear()
        accounts = service.list_accounts()
        if not accounts:
            ctk.CTkLabel(
                self.accounts_list, text="Nenhuma conta. Conecte em Contas primeiro.",
                font=(theme.FONT, 12), text_color=theme.MUTED,
            ).pack(anchor="w")
            self._update_account_count()
            return
        for acc in accounts:
            var = ctk.BooleanVar(value=False)
            self._account_vars[acc["id"]] = var
            row = ctk.CTkFrame(self.accounts_list, fg_color=theme.CARD2, corner_radius=10)
            row.pack(fill="x", pady=3)
            status = acc.get("status") or "unknown"
            color = theme.STATUS_COLORS.get(status, theme.MUTED)
            label = theme.STATUS_LABELS.get(status, status)
            ctk.CTkCheckBox(
                row,
                text=f"{acc.get('name') or 'Conta'}  @{acc.get('username') or '—'}",
                variable=var,
                font=(theme.FONT, 12),
                text_color=theme.TEXT,
                fg_color=theme.PRIMARY,
                command=self._update_account_count,
            ).pack(side="left", padx=12, pady=10)
            ctk.CTkLabel(row, text=label, font=(theme.FONT, 11, "bold"), text_color=color).pack(
                side="right", padx=12,
            )
        self._update_account_count()

    def _selected_ids(self) -> list[int]:
        return [aid for aid, var in self._account_vars.items() if var.get()]

    def _update_account_count(self):
        n = len(self._selected_ids())
        total = len(self._account_vars)
        self.accounts_count.configure(text=f"{n} de {total} selecionada(s)")

    def _select_all(self):
        for var in self._account_vars.values():
            var.set(True)
        self._update_account_count()

    def _select_healthy(self):
        accounts = {a["id"]: a for a in service.list_accounts()}
        for aid, var in self._account_vars.items():
            acc = accounts.get(aid) or {}
            var.set(acc.get("status") == "healthy" and acc.get("has_session"))
        self._update_account_count()

    def _clear_accounts(self):
        for var in self._account_vars.values():
            var.set(False)
        self._update_account_count()

    # ---------- apply ----------
    def _apply(self):
        ids = self._selected_ids()
        if not ids:
            self.app.toast("Selecione pelo menos uma conta", "error")
            return
        raw = self.bio.get("1.0", "end").rstrip("\n")
        mode = self.bio_mode.get()
        biography = None
        biographies = None
        if raw.strip():
            if mode == "lines":
                biographies = [ln.strip() for ln in raw.splitlines() if ln.strip()]
                if not biographies:
                    self.app.toast("Nenhuma bio válida nas linhas", "error")
                    return
                for b in biographies:
                    if len(b) > BIO_MAX_LEN:
                        self.app.toast(f"Bio com mais de {BIO_MAX_LEN} caracteres", "error")
                        return
            else:
                biography = raw.strip()
                if len(biography) > BIO_MAX_LEN:
                    self.app.toast(f"Bio com no máximo {BIO_MAX_LEN} caracteres", "error")
                    return
        if not self.pictures and biography is None and not biographies:
            self.app.toast("Selecione fotos e/ou digite a bio", "error")
            return

        self.apply_btn.configure(state="disabled", text="Aplicando...")

        def work():
            return service.bulk_update_profiles(
                ids,
                picture_paths=list(self.pictures) if self.pictures else None,
                biography=biography,
                biographies=biographies,
            )

        def done(res):
            self.apply_btn.configure(state="normal", text="Aplicar foto e bio nas contas")
            msg = res.get("message") or "Concluído"
            if res.get("ok"):
                self.app.toast(msg, "success")
            else:
                self.app.toast(msg, "error")
            # mostra falhas pontuais
            fails = [r for r in (res.get("results") or []) if not r.get("ok")]
            if fails and hasattr(self.app, "toast"):
                first = fails[0].get("message") or "erro"
                if len(fails) == 1:
                    self.app.toast(f"1 falha: {first}", "error")
                else:
                    self.app.toast(f"{len(fails)} falha(s). Ex.: {first}", "error")

        self.app.run_async(work, on_done=done)

    def on_show(self):
        self._reload_accounts()

    def refresh(self):
        pass
