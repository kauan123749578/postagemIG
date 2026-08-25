"""Tela Stories: link com preview arrastável, agendar multi-conta."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from core import service
from core.config import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from ui import theme, widgets
from ui.calendar_picker import MonthCalendar
from ui.views.base import BaseView
from ui.story_preview import StoryLinkPreview


class StoriesView(BaseView):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.media_paths: list[str] = []
        self._account_vars: dict[int, ctk.BooleanVar] = {}
        self._time_entries: list[ctk.CTkEntry] = []
        self.mode = "schedule"

        widgets.title(self, "Stories", size=24).pack(anchor="w")
        widgets.subtitle(
            self,
            "Story com link clicável — arraste o botão no preview e agende em várias contas",
        ).pack(anchor="w", pady=(0, 12))

        self.scroll = widgets.soft_scrollable(self, speed=0.22)
        self.scroll.pack(fill="both", expand=True)

        self._build_media()
        self._build_link_preview()
        self._build_schedule()
        self._build_accounts()
        self._build_action()

    def _build_media(self):
        card, body = widgets.section(self.scroll, "Mídia", "Fotos ou vídeos do Story", icon="🎬")
        card.pack(fill="x", pady=(0, 12))
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", pady=(0, 6))
        widgets.primary_button(row, "＋ Selecionar mídias", self._pick_media, width=180).pack(side="left")
        widgets.ghost_button(row, "Limpar", self._clear_media, width=100).pack(side="left", padx=(8, 0))
        self.media_label = ctk.CTkLabel(
            body, text="Nenhum arquivo selecionado", font=(theme.FONT, 12),
            text_color=theme.DANGER, anchor="w",
        )
        self.media_label.pack(fill="x")

    def _build_link_preview(self):
        card, body = widgets.section(self.scroll, "Link do Story", "URL + texto do botão", icon="🔗")
        card.pack(fill="x", pady=(0, 12))

        grid = ctk.CTkFrame(body, fg_color="transparent")
        grid.pack(fill="x")
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=0)

        left = ctk.CTkFrame(grid, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        widgets.field_label(left, "URL do link").pack(anchor="w")
        self.link_entry = widgets.entry(left, "https://seusite.com")
        self.link_entry.pack(fill="x", pady=(4, 10))
        self.link_entry.bind("<KeyRelease>", lambda _e: self._sync_preview())

        widgets.field_label(left, "Texto do botão (opcional)").pack(anchor="w")
        self.link_text_entry = widgets.entry(left, "Deixe vazio = domínio em maiúsculo")
        self.link_text_entry.pack(fill="x", pady=(4, 0))
        self.link_text_entry.bind("<KeyRelease>", lambda _e: self._sync_preview())

        right = ctk.CTkFrame(grid, fg_color="transparent")
        right.grid(row=0, column=1, sticky="ne", padx=(8, 0))
        self.preview = StoryLinkPreview(right)
        self.preview.pack()

    def _build_schedule(self):
        card, body = widgets.section(
            self.scroll, "Agendamento", "Quando e com que frequência publicar", icon="⏰",
        )
        card.pack(fill="x", pady=(0, 12))

        self.mode_var = ctk.StringVar(value="schedule")
        modes = ctk.CTkFrame(body, fg_color="transparent")
        modes.pack(fill="x", pady=(0, 12))
        for i, (val, label) in enumerate([("schedule", "Agendar por calendário + horário"), ("now", "Postar agora")]):
            ctk.CTkRadioButton(
                modes, text=label, variable=self.mode_var, value=val,
                font=(theme.FONT, 13), text_color=theme.TEXT,
                fg_color=theme.PRIMARY, hover_color=theme.PRIMARY_HOVER,
                command=self._toggle_mode,
            ).pack(side="left", padx=(0 if i == 0 else 16, 0))

        self.schedule_box = ctk.CTkFrame(body, fg_color="transparent")
        self.schedule_box.pack(fill="x")

        widgets.field_label(self.schedule_box, "Dias do mês").pack(anchor="w", pady=(0, 4))
        self.calendar = MonthCalendar(self.schedule_box)
        self.calendar.pack(fill="x", pady=(0, 12))

        widgets.field_label(self.schedule_box, "Horários (HH:MM — um por Story, BRT)").pack(anchor="w")
        ctk.CTkLabel(
            self.schedule_box,
            text="Ex.: mês selecionado + Story 1 às 12:00 e Story 2 às 18:00",
            font=(theme.FONT, 11), text_color=theme.MUTED, anchor="w",
        ).pack(fill="x", pady=(0, 4))
        self.times_frame = ctk.CTkFrame(self.schedule_box, fg_color="transparent")
        self.times_frame.pack(fill="x", pady=(4, 8))
        self._add_time_row(datetime.now().strftime("%H:%M"))
        widgets.ghost_button(self.schedule_box, "＋ Adicionar horário", self._add_time_row, width=160).pack(anchor="w")

    def _build_accounts(self):
        card, body = widgets.section(self.scroll, "Contas", "Quem recebe os Stories", icon="👥")
        card.pack(fill="x", pady=(0, 12))
        self.accounts_count = ctk.CTkLabel(
            body, text="0 selecionada(s)", font=(theme.FONT, 12), text_color=theme.MUTED, anchor="w",
        )
        self.accounts_count.pack(fill="x", pady=(0, 6))
        btns = ctk.CTkFrame(body, fg_color="transparent")
        btns.pack(fill="x", pady=(0, 8))
        widgets.ghost_button(btns, "Selecionar todas", self._select_all, width=140, height=34).pack(side="left")
        widgets.ghost_button(btns, "Só ativas", self._select_healthy, width=110, height=34).pack(side="left", padx=(8, 0))
        widgets.ghost_button(btns, "Limpar", self._clear_accounts, width=90, height=34).pack(side="left", padx=(8, 0))
        self.accounts_list = ctk.CTkFrame(body, fg_color="transparent")
        self.accounts_list.pack(fill="x")

    def _build_action(self):
        self.action_btn = widgets.primary_button(
            self.scroll, "Agendar Stories", self._submit, height=48,
        )
        self.action_btn.pack(fill="x", pady=(4, 28))

    # ---------- media ----------
    def _pick_media(self):
        paths = filedialog.askopenfilenames(
            title="Mídias do Story",
            filetypes=[("Mídia", "*.jpg *.jpeg *.png *.webp *.mp4 *.mov *.m4v *.webm"), ("Todos", "*.*")],
        )
        if not paths:
            return
        valid = [p for p in paths if Path(p).suffix.lower() in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS]
        self.media_paths = list(valid)
        self._refresh_media_label()
        if self.media_paths:
            self.preview.set_media(self.media_paths[0])
            self._sync_preview()

    def _clear_media(self):
        self.media_paths = []
        self.preview.set_media(None)
        self._refresh_media_label()

    def _refresh_media_label(self):
        n = len(self.media_paths)
        if n == 0:
            self.media_label.configure(text="Nenhum arquivo selecionado", text_color=theme.DANGER)
        else:
            names = ", ".join(Path(p).name for p in self.media_paths[:3])
            extra = f" (+{n - 3})" if n > 3 else ""
            self.media_label.configure(text=f"{n} arquivo(s): {names}{extra}", text_color=theme.SUCCESS)

    def _sync_preview(self):
        self.preview.set_link(self.link_entry.get().strip(), self.link_text_entry.get().strip())

    # ---------- schedule ----------
    def _toggle_mode(self):
        self.mode = self.mode_var.get()
        if self.mode == "now":
            self.schedule_box.pack_forget()
            self.action_btn.configure(text="Publicar Stories agora")
        else:
            self.schedule_box.pack(fill="x")
            self.action_btn.configure(text="Agendar Stories")

    def _add_time_row(self, default: str = ""):
        row = ctk.CTkFrame(self.times_frame, fg_color="transparent")
        row.pack(fill="x", pady=2)
        entry = widgets.entry(row, "HH:MM")
        if default:
            entry.insert(0, default)
        entry.pack(side="left", fill="x", expand=True)
        self._time_entries.append(entry)
        if len(self._time_entries) > 1:
            widgets.ghost_button(
                row, "✕", lambda e=entry: self._remove_time(e), width=36, height=34,
            ).pack(side="right", padx=(6, 0))

    def _remove_time(self, entry):
        if entry in self._time_entries:
            self._time_entries.remove(entry)
            entry.master.destroy()

    def _parse_times(self) -> list[datetime]:
        days = self.calendar.selected_dates()
        if not days:
            raise ValueError("Selecione pelo menos um dia no calendário")
        hours: list[tuple[int, int]] = []
        for entry in self._time_entries:
            raw = entry.get().strip()
            if not raw:
                continue
            try:
                t = datetime.strptime(raw, "%H:%M")
                hours.append((t.hour, t.minute))
            except ValueError as exc:
                raise ValueError(f"Horário inválido: {raw} (use HH:MM)") from exc
        if not hours:
            raise ValueError("Adicione pelo menos um horário (HH:MM)")
        times = []
        for d in days:
            for hh, mm in hours:
                local = datetime(d.year, d.month, d.day, hh, mm)
                times.append(local.astimezone().astimezone(timezone.utc))
        return times

    # ---------- accounts ----------
    def _reload_accounts(self):
        for w in self.accounts_list.winfo_children():
            w.destroy()
        self._account_vars.clear()
        accounts = service.list_accounts()
        if not accounts:
            ctk.CTkLabel(
                self.accounts_list, text="Nenhuma conta. Conecte em Contas.",
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
            ctk.CTkLabel(row, text=label, font=(theme.FONT, 11, "bold"), text_color=color).pack(side="right", padx=12)
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

    # ---------- submit ----------
    def _submit(self):
        account_ids = self._selected_account_ids()
        if not account_ids:
            self.app.toast("Selecione pelo menos uma conta", "error")
            return
        if not self.media_paths:
            self.app.toast("Selecione pelo menos uma mídia", "error")
            return

        link_url = self.link_entry.get().strip()
        link_text = self.link_text_entry.get().strip()
        geom = self.preview.get_link_geom()
        payload = dict(
            account_ids=account_ids,
            media_paths=list(self.media_paths),
            caption="",
            link_url=link_url,
            link_text=link_text,
            link_x=geom["x"],
            link_y=geom["y"],
            link_w=geom.get("width", 0.6),
            link_h=geom.get("height", 0.068625),
        )

        if self.mode == "now":
            self.action_btn.configure(state="disabled", text="Publicando...")
            self.app.run_async(
                lambda: service.publish_stories_now(**payload),
                on_done=self._after_submit,
                on_error=lambda e: self._fail(str(e)),
            )
            return

        try:
            times = self._parse_times()
        except ValueError as exc:
            self.app.toast(str(exc), "error")
            return
        if not times:
            self.app.toast("Adicione pelo menos um horário", "error")
            return

        self.action_btn.configure(state="disabled", text="Agendando...")
        self.app.run_async(
            lambda: service.schedule_stories(**payload, schedule_times=times),
            on_done=self._after_submit,
            on_error=lambda e: self._fail(str(e)),
        )

    def _after_submit(self, result):
        self._toggle_mode()
        self.action_btn.configure(state="normal")
        if not result.get("ok"):
            self.app.toast(result.get("message") or "Erro", "error")
            return
        self.app.toast(result.get("message") or "OK", "success")
        self._clear_media()
        self.link_entry.delete(0, "end")
        self.link_text_entry.delete(0, "end")
        self._clear_accounts()

    def _fail(self, msg: str):
        self._toggle_mode()
        self.action_btn.configure(state="normal")
        self.app.toast(msg, "error")

    def on_show(self):
        self._reload_accounts()
        self._sync_preview()

    def refresh(self):
        pass
