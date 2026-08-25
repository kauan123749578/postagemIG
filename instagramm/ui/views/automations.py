"""Tela Automações — modelo Instablack local (1 legenda + N vídeos + 1 capa + N contas)."""
from __future__ import annotations

from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from core import automations as auto_svc
from core import service
from core.config import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from ui import theme, widgets
from ui.views.base import BaseView

INTERVAL_OPTIONS = [
    ("5 minutos", 5),
    ("10 minutos", 10),
    ("15 minutos", 15),
    ("30 minutos", 30),
    ("60 minutos", 60),
]


class AutomationsView(BaseView):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.videos: list[str] = []
        self.cover_path: str = ""
        self._account_vars: dict[int, ctk.BooleanVar] = {}

        widgets.title(self, "Automações", size=24).pack(anchor="w")
        widgets.subtitle(
            self,
            "Crie como no Instablack: legenda fixa, vários Reels, uma capa e anti-farm entre contas",
        ).pack(anchor="w", pady=(0, 12))

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True)

        self._build_form()
        self._build_list()

    # ---------- form ----------
    def _build_form(self):
        card, body = widgets.section(
            self.scroll,
            "Conteúdo",
            "Nome, tipo e legenda da publicação",
            icon="📄",
        )
        card.pack(fill="x", pady=(0, 12))

        widgets.field_label(body, "Nome da automação").pack(anchor="w")
        self.name_entry = widgets.entry(body, placeholder="Ex.: Reels a cada 1 hora")
        self.name_entry.pack(fill="x", pady=(4, 12))

        widgets.field_label(body, "Tipo de conteúdo").pack(anchor="w")
        self.type_label = ctk.CTkLabel(
            body, text="Reels (vídeo)", font=(theme.FONT, 13), text_color=theme.TEXT,
            fg_color=theme.CARD2, corner_radius=8, height=36, anchor="w",
        )
        self.type_label.pack(fill="x", pady=(4, 12), padx=0)
        self.type_label.configure(padx=12)

        widgets.field_label(body, "Legenda *").pack(anchor="w")
        self.caption = ctk.CTkTextbox(
            body, height=110, corner_radius=10,
            fg_color=theme.CARD2, border_color=theme.BORDER, border_width=1,
            text_color=theme.TEXT, font=(theme.FONT, 13),
        )
        self.caption.pack(fill="x", pady=(4, 4))
        ctk.CTkLabel(
            body,
            text="Obrigatória. Fixa: todas as contas usam o mesmo texto. Sem legenda não cria.",
            font=(theme.FONT, 11), text_color=theme.MUTED, wraplength=720, justify="left",
        ).pack(anchor="w", pady=(0, 4))

        # Mídia
        mcard, mbody = widgets.section(
            self.scroll,
            "Mídia",
            "Arquivos e capa enviados ao armazenamento local",
            icon="🎬",
        )
        mcard.pack(fill="x", pady=(0, 12))

        widgets.field_label(mbody, "Vídeos Reels (.mp4)").pack(anchor="w")
        row = ctk.CTkFrame(mbody, fg_color="transparent")
        row.pack(fill="x", pady=(4, 4))
        widgets.primary_button(row, "＋  Selecionar vídeos", self._pick_videos, width=180).pack(side="left")
        widgets.ghost_button(row, "Limpar vídeos", self._clear_videos, width=120).pack(side="left", padx=(8, 0))
        self.videos_label = ctk.CTkLabel(
            mbody, text="Nenhum vídeo selecionado", font=(theme.FONT, 12), text_color=theme.DANGER, anchor="w",
        )
        self.videos_label.pack(fill="x", pady=(4, 12))

        widgets.field_label(mbody, "Capa para todos os Reels (.jpg/.png — 9:16)").pack(anchor="w")
        crow = ctk.CTkFrame(mbody, fg_color="transparent")
        crow.pack(fill="x", pady=(4, 4))
        widgets.ghost_button(crow, "Escolher capa (opcional)", self._pick_cover, width=200).pack(side="left")
        widgets.ghost_button(crow, "Remover capa", self._clear_cover, width=120).pack(side="left", padx=(8, 0))
        self.cover_label = ctk.CTkLabel(
            mbody, text="Capa opcional — mesma imagem em todos os vídeos",
            font=(theme.FONT, 12), text_color=theme.MUTED, anchor="w",
        )
        self.cover_label.pack(fill="x", pady=(4, 4))

        # Timing
        tcard, tbody = widgets.section(
            self.scroll,
            "Intervalo e anti-farm",
            "Espalha posts entre contas do mesmo ciclo",
            icon="⏱️",
        )
        tcard.pack(fill="x", pady=(0, 12))

        widgets.field_label(tbody, "Publicar a cada").pack(anchor="w")
        self.interval_var = ctk.StringVar(value="10 minutos")
        self.interval_menu = ctk.CTkOptionMenu(
            tbody,
            values=[x[0] for x in INTERVAL_OPTIONS],
            variable=self.interval_var,
            fg_color=theme.CARD2, button_color=theme.PRIMARY, button_hover_color=theme.PRIMARY_HOVER,
            height=36, corner_radius=10,
        )
        self.interval_menu.pack(fill="x", pady=(4, 12))

        self.stagger_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            tbody,
            text="Espaçamento entre contas (anti-farm)",
            variable=self.stagger_var,
            font=(theme.FONT, 13),
            text_color=theme.TEXT,
            fg_color=theme.PRIMARY, hover_color=theme.PRIMARY_HOVER,
        ).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(
            tbody,
            text="Espalhar posts entre as contas do mesmo ciclo (não postar todas no mesmo minuto)",
            font=(theme.FONT, 11), text_color=theme.MUTED, wraplength=720, justify="left",
        ).pack(anchor="w", pady=(0, 8))

        grid = ctk.CTkFrame(tbody, fg_color="transparent")
        grid.pack(fill="x")
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)
        widgets.field_label(grid, "Mínimo entre contas (min)").grid(row=0, column=0, sticky="w")
        widgets.field_label(grid, "Máximo entre contas (min)").grid(row=0, column=1, sticky="w", padx=(12, 0))
        self.min_entry = widgets.entry(grid, placeholder="2")
        self.min_entry.insert(0, "2")
        self.min_entry.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.max_entry = widgets.entry(grid, placeholder="8")
        self.max_entry.insert(0, "8")
        self.max_entry.grid(row=1, column=1, sticky="ew", pady=(4, 0), padx=(12, 0))
        ctk.CTkLabel(
            tbody,
            text="Ex.: mín 2 e máx 8 → 1ª conta posta já; 2ª espera ~2–8 min; 3ª soma de novo…",
            font=(theme.FONT, 11), text_color=theme.MUTED, wraplength=720, justify="left",
        ).pack(anchor="w", pady=(8, 0))

        # Contas
        acard, abody = widgets.section(
            self.scroll,
            "Contas",
            "Quem recebe as publicações (opcional no rascunho)",
            icon="👥",
        )
        acard.pack(fill="x", pady=(0, 12))
        self.accounts_body = abody
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

        widgets.primary_button(
            self.scroll, "Criar automação", self._create, height=48,
        ).pack(fill="x", pady=(4, 20))

    def _build_list(self):
        lcard, lbody = widgets.section(
            self.scroll,
            "Automações criadas",
            "Ative, pause ou remova",
            icon="📋",
        )
        lcard.pack(fill="x", pady=(0, 20))
        self.list_body = lbody

    # ---------- picks ----------
    def _pick_videos(self):
        paths = filedialog.askopenfilenames(
            title="Selecionar Reels",
            filetypes=[("Vídeo", "*.mp4 *.mov *.m4v *.webm"), ("Todos", "*.*")],
        )
        if not paths:
            return

        def work():
            saved = []
            for p in paths:
                if Path(p).suffix.lower() not in VIDEO_EXTENSIONS:
                    continue
                saved.append(service.import_video(p))
            return saved

        def done(saved):
            self.videos.extend(saved)
            self._refresh_videos_label()
            self.app.toast(f"{len(saved)} vídeo(s) adicionado(s)", "success")

        self.app.run_async(work, on_done=done)

    def _clear_videos(self):
        self.videos = []
        self._refresh_videos_label()

    def _refresh_videos_label(self):
        n = len(self.videos)
        if n == 0:
            self.videos_label.configure(text="Nenhum vídeo selecionado — escolha um ou mais .mp4", text_color=theme.DANGER)
        else:
            names = ", ".join(Path(v).name for v in self.videos[:3])
            extra = f" (+{n - 3})" if n > 3 else ""
            self.videos_label.configure(text=f"{n} vídeo(s): {names}{extra}", text_color=theme.SUCCESS)

    def _pick_cover(self):
        path = filedialog.askopenfilename(
            title="Capa para todos os Reels",
            filetypes=[("Imagem", "*.jpg *.jpeg *.png *.webp"), ("Todos", "*.*")],
        )
        if not path:
            return
        if Path(path).suffix.lower() not in IMAGE_EXTENSIONS:
            self.app.toast("Use jpg/png/webp", "error")
            return

        def work():
            return service.import_image(path)

        def done(saved):
            self.cover_path = saved
            self.cover_label.configure(text=f"Capa: {Path(saved).name}", text_color=theme.SUCCESS)

        self.app.run_async(work, on_done=done)

    def _clear_cover(self):
        self.cover_path = ""
        self.cover_label.configure(text="Capa opcional — mesma imagem em todos os vídeos", text_color=theme.MUTED)

    # ---------- accounts ----------
    def _reload_accounts(self):
        for w in self.accounts_list.winfo_children():
            w.destroy()
        self._account_vars.clear()
        accounts = service.list_accounts()
        if not accounts:
            ctk.CTkLabel(
                self.accounts_list, text="Nenhuma conta cadastrada. Vá em Contas e conecte.",
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
            cb = ctk.CTkCheckBox(
                row,
                text=f"{acc.get('name') or 'Conta'}  @{acc.get('username') or '—'}",
                variable=var,
                font=(theme.FONT, 12),
                text_color=theme.TEXT,
                fg_color=theme.PRIMARY,
                command=self._update_account_count,
            )
            cb.pack(side="left", padx=12, pady=10)
            ctk.CTkLabel(row, text=label, font=(theme.FONT, 11, "bold"), text_color=color).pack(
                side="right", padx=12
            )
        self._update_account_count()

    def _selected_account_ids(self) -> list[int]:
        return [aid for aid, var in self._account_vars.items() if var.get()]

    def _update_account_count(self):
        n = len(self._selected_account_ids())
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

    # ---------- create / list ----------
    def _interval_minutes(self) -> int:
        label = self.interval_var.get()
        for name, mins in INTERVAL_OPTIONS:
            if name == label:
                return mins
        return 10

    def _create(self):
        caption = self.caption.get("1.0", "end").strip()
        if not caption:
            self.app.toast("Legenda obrigatória", "error")
            return
        if not self.videos:
            self.app.toast("Selecione pelo menos um vídeo", "error")
            return
        try:
            smin = int(self.min_entry.get().strip() or "2")
            smax = int(self.max_entry.get().strip() or "8")
        except ValueError:
            self.app.toast("Mín/máx entre contas devem ser números", "error")
            return

        payload = dict(
            name=self.name_entry.get().strip(),
            caption=caption,
            videos=list(self.videos),
            cover_path=self.cover_path,
            account_ids=self._selected_account_ids(),
            interval_minutes=self._interval_minutes(),
            stagger_enabled=bool(self.stagger_var.get()),
            stagger_min_minutes=smin,
            stagger_max_minutes=smax,
        )

        def work():
            return auto_svc.create_automation(**payload)

        def done(result):
            if not result.get("ok"):
                self.app.toast(result.get("message") or "Erro", "error")
                return
            self.app.toast(result.get("message") or "Criada", "success")
            self.caption.delete("1.0", "end")
            self.name_entry.delete(0, "end")
            self._clear_videos()
            self._clear_cover()
            self._clear_accounts()
            self._reload_list()

        self.app.run_async(work, on_done=done)

    def _reload_list(self):
        for w in self.list_body.winfo_children():
            w.destroy()
        items = auto_svc.list_automations()
        if not items:
            ctk.CTkLabel(
                self.list_body, text="Nenhuma automação ainda.",
                font=(theme.FONT, 12), text_color=theme.MUTED,
            ).pack(anchor="w")
            return
        for item in items:
            self._render_item(item)

    def _render_item(self, item: dict):
        row = widgets.card(self.list_body)
        row.pack(fill="x", pady=6)
        top = ctk.CTkFrame(row, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(12, 4))
        ctk.CTkLabel(
            top, text=item.get("name") or f"Automação #{item['id']}",
            font=(theme.FONT, 14, "bold"), text_color=theme.TEXT,
        ).pack(side="left")
        status = item.get("status") or "draft"
        status_colors = {
            "active": theme.SUCCESS,
            "paused": theme.WARNING,
            "done": theme.MUTED,
            "draft": theme.MUTED,
            "error": theme.DANGER,
        }
        ctk.CTkLabel(
            top, text=status.upper(), font=(theme.FONT, 11, "bold"),
            text_color=status_colors.get(status, theme.MUTED),
        ).pack(side="right")

        meta = (
            f"{item.get('video_count', 0)} vídeo(s) · "
            f"{len(item.get('account_ids') or [])} conta(s) · "
            f"a cada {item.get('interval_minutes')} min · "
            f"fila {item.get('jobs_posted', 0)} ok / {item.get('jobs_pending', 0)} pendente / {item.get('jobs_error', 0)} erro"
        )
        ctk.CTkLabel(row, text=meta, font=(theme.FONT, 11), text_color=theme.MUTED, anchor="w").pack(
            fill="x", padx=14, pady=(0, 4)
        )
        if item.get("last_error"):
            ctk.CTkLabel(
                row, text=item["last_error"][:180], font=(theme.FONT, 11),
                text_color=theme.DANGER, anchor="w", wraplength=700, justify="left",
            ).pack(fill="x", padx=14, pady=(0, 4))

        actions = ctk.CTkFrame(row, fg_color="transparent")
        actions.pack(fill="x", padx=14, pady=(4, 12))
        aid = item["id"]
        if status != "active":
            widgets.primary_button(
                actions, "Ativar", lambda i=aid: self._activate(i), width=100, height=34,
            ).pack(side="left")
        else:
            widgets.ghost_button(
                actions, "Pausar", lambda i=aid: self._pause(i), width=100, height=34,
            ).pack(side="left")
        widgets.ghost_button(
            actions, "Excluir", lambda i=aid: self._delete(i), width=100, height=34,
        ).pack(side="left", padx=(8, 0))

    def _activate(self, automation_id: int):
        def work():
            return auto_svc.activate_automation(automation_id)

        def done(result):
            self.app.toast(result.get("message") or "", "success" if result.get("ok") else "error")
            self._reload_list()

        self.app.run_async(work, on_done=done)

    def _pause(self, automation_id: int):
        def work():
            return auto_svc.pause_automation(automation_id)

        def done(result):
            self.app.toast(result.get("message") or "", "success" if result.get("ok") else "error")
            self._reload_list()

        self.app.run_async(work, on_done=done)

    def _delete(self, automation_id: int):
        def work():
            return auto_svc.delete_automation(automation_id)

        def done(result):
            self.app.toast(result.get("message") or "", "success" if result.get("ok") else "error")
            self._reload_list()

        self.app.run_async(work, on_done=done)

    def on_show(self):
        self._reload_accounts()
        self._reload_list()

    def refresh(self):
        self._reload_list()
