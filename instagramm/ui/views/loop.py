"""Tela Loop contínuo: posta vídeos de uma lista em intervalos definidos."""
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from core import service
from ui import theme, widgets
from ui.views.base import BaseView


class LoopView(BaseView):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.accounts = []
        self.videos = []  # list[{video_path, cover_path, caption}]

        widgets.title(self, "Loop de publicação", size=24).pack(anchor="w")
        widgets.subtitle(self, "Publica os vídeos da lista em sequência (contínuo) ou em lotes (recorrente)").pack(anchor="w", pady=(0, 12))

        # container rolável — garante que tudo apareça mesmo em telas pequenas
        scroll = widgets.soft_scrollable(self)
        scroll.pack(fill="both", expand=True)

        self.running_card, self.running_body = widgets.section(
            scroll,
            "Contas rodando agora",
            "Loops, aquecimento e fila escalonada ativos",
            icon="▶",
        )
        self.running_card.pack(fill="x", pady=(0, 12))

        top = widgets.card(scroll)
        top.pack(fill="x")
        inner = ctk.CTkFrame(top, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=18)
        inner.grid_columnconfigure(0, weight=1)
        inner.grid_columnconfigure(1, weight=0)

        left = ctk.CTkFrame(inner, fg_color="transparent")
        left.grid(row=0, column=0, sticky="ew")
        widgets.field_label(left, "Conta").pack(anchor="w", pady=(0, 2))
        self.account_menu = ctk.CTkOptionMenu(left, values=["Carregando..."], command=lambda _v: self._load_loop(),
                                              fg_color=theme.CARD2, button_color=theme.PRIMARY,
                                              button_hover_color=theme.PRIMARY_HOVER, dropdown_fg_color=theme.CARD2, height=40)
        self.account_menu.pack(fill="x")

        right = ctk.CTkFrame(inner, fg_color="transparent")
        right.grid(row=0, column=1, sticky="e", padx=(16, 0))
        widgets.field_label(right, "Intervalo (segundos)").pack(anchor="w", pady=(0, 2))
        self.interval_entry = widgets.entry(right, "120", width=120)
        self.interval_entry.insert(0, "120")
        self.interval_entry.pack()

        # modo do loop + opções de lote
        modes = ctk.CTkFrame(inner, fg_color="transparent")
        modes.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        widgets.field_label(modes, "Modo").pack(anchor="w", pady=(0, 2))
        self.mode_seg = ctk.CTkSegmentedButton(
            modes, values=["Contínuo", "Recorrente"], command=lambda _v: self._on_mode_change(),
            fg_color=theme.CARD2, selected_color=theme.PRIMARY, selected_hover_color=theme.PRIMARY_HOVER,
            unselected_color=theme.CARD2, text_color=theme.TEXT,
        )
        self.mode_seg.set("Contínuo")
        self.mode_seg.pack(anchor="w")

        self.batch_frame = ctk.CTkFrame(inner, fg_color="transparent")
        self.batch_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        bcol = ctk.CTkFrame(self.batch_frame, fg_color="transparent")
        bcol.pack(side="left")
        widgets.field_label(bcol, "Vídeos por lote").pack(anchor="w", pady=(0, 2))
        self.batch_size_entry = widgets.entry(bcol, "3", width=120)
        self.batch_size_entry.insert(0, "3")
        self.batch_size_entry.pack()
        icol = ctk.CTkFrame(self.batch_frame, fg_color="transparent")
        icol.pack(side="left", padx=(12, 0))
        widgets.field_label(icol, "Intervalo entre lotes (min)").pack(anchor="w", pady=(0, 2))
        self.batch_interval_entry = widgets.entry(icol, "360", width=160)
        self.batch_interval_entry.insert(0, "360")
        self.batch_interval_entry.pack()
        self.batch_frame.grid_remove()  # só aparece no modo recorrente

        # capa única aplicada a todos os vídeos
        self.cover_path = ""
        cover_row = ctk.CTkFrame(inner, fg_color="transparent")
        cover_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        widgets.field_label(cover_row, "Capa para todos os vídeos (opcional)").pack(anchor="w", pady=(0, 2))
        cover_ctrls = ctk.CTkFrame(cover_row, fg_color="transparent")
        cover_ctrls.pack(fill="x")
        widgets.ghost_button(cover_ctrls, "🖼  Escolher capa", self._choose_cover).pack(side="left")
        self.cover_clear_btn = widgets.danger_button(cover_ctrls, "Remover capa", self._clear_cover)
        self.cover_label = ctk.CTkLabel(cover_ctrls, text="Nenhuma capa selecionada", font=(theme.FONT, 12), text_color=theme.MUTED)
        self.cover_label.pack(side="left", padx=12)

        widgets.field_label(inner, "Legenda padrão do loop").grid(row=4, column=0, columnspan=2, sticky="w", pady=(12, 2))
        self.caption_box = ctk.CTkTextbox(inner, height=60, fg_color=theme.CARD2, border_color=theme.BORDER, border_width=1, corner_radius=10, text_color=theme.TEXT)
        self.caption_box.grid(row=5, column=0, columnspan=2, sticky="ew")

        # botões de vídeo (sempre visíveis, logo abaixo da legenda)
        vbtns = ctk.CTkFrame(scroll, fg_color="transparent")
        vbtns.pack(fill="x", pady=(12, 0))
        widgets.primary_button(vbtns, "+ Adicionar vídeos", self._add_videos, height=40).pack(side="left")
        widgets.ghost_button(vbtns, "Limpar lista", self._clear_videos, height=40).pack(side="left", padx=(8, 0))

        # status + controles
        ctrl = ctk.CTkFrame(scroll, fg_color="transparent")
        ctrl.pack(fill="x", pady=12)
        self.status_label = ctk.CTkLabel(ctrl, text="Loop parado", font=(theme.FONT, 13, "bold"), text_color=theme.MUTED)
        self.status_label.pack(side="left")
        self.stop_all_btn = widgets.danger_button(ctrl, "⏹ Parar TODOS os loops", self._stop_all, height=40)
        self.stop_all_btn.pack(side="right", padx=(8, 0))
        self.stop_btn = widgets.danger_button(ctrl, "⏹ Parar loop", self._stop, height=40)
        self.stop_btn.pack(side="right", padx=(8, 0))
        self.start_btn = widgets.primary_button(ctrl, "▶ Iniciar loop", self._start, height=40)
        self.start_btn.pack(side="right")

        # lista de vídeos
        listcard = widgets.card(scroll)
        listcard.pack(fill="both", expand=True)
        lhead = ctk.CTkFrame(listcard, fg_color="transparent")
        lhead.pack(fill="x", padx=18, pady=(14, 6))
        widgets.title(lhead, "Vídeos do loop", size=15).pack(side="left")
        self.videos_frame = widgets.soft_scrollable(listcard, height=220)
        self.videos_frame.pack(fill="both", expand=True, padx=10, pady=(0, 12))

    def on_show(self):
        self.app.run_async(service.list_accounts, on_done=self._fill_accounts)
        self._update_running_panel()

    def _update_running_panel(self):
        def done(count):
            if count > 0:
                self.stop_all_btn.configure(text=f"⏹ Parar TODOS ({count})")
            else:
                self.stop_all_btn.configure(text="⏹ Parar TODOS os loops")

        self.app.run_async(service.count_running_loops, on_done=done)
        self.app.run_async(service.list_running_tasks, on_done=self._render_running_panel)

    def _render_running_panel(self, tasks):
        widgets.render_running_tasks(
            self.running_body, tasks,
            empty_text="Nenhuma conta rodando no momento",
            on_stop=self._stop_account,
        )

    def _stop_account(self, account_id):
        if not account_id:
            return
        self.app.run_async(
            lambda: service.set_loop_running(account_id, False),
            on_done=lambda _r: (
                self.app.toast("Loop desta conta parado", "info"),
                self._load_loop(), self._update_running_panel(),
            ),
        )

    def refresh(self):
        self._load_loop()
        self._update_running_panel()

    def _fill_accounts(self, accounts):
        self.accounts = accounts
        if not accounts:
            self.account_menu.configure(values=["Nenhuma conta"])
            self.account_menu.set("Nenhuma conta")
            return
        labels = [f"{a['name']} (@{a['username']})" for a in accounts]
        self.account_menu.configure(values=labels)
        if self.account_menu.get() not in labels:
            self.account_menu.set(labels[0])
        self._load_loop()

    def _selected_account_id(self):
        label = self.account_menu.get()
        for a in self.accounts:
            if f"{a['name']} (@{a['username']})" == label:
                return a["id"]
        return None

    def _load_loop(self):
        acc_id = self._selected_account_id()
        if not acc_id:
            return
        self.app.run_async(lambda: service.get_loop(acc_id), on_done=self._render_loop)

    def _on_mode_change(self):
        if self.mode_seg.get() == "Recorrente":
            self.batch_frame.grid()
        else:
            self.batch_frame.grid_remove()

    def _update_cover_label(self):
        if self.cover_path:
            self.cover_label.configure(text=Path(self.cover_path).name, text_color=theme.TEXT)
            self.cover_clear_btn.pack(side="left", padx=(8, 0))
        else:
            self.cover_label.configure(text="Nenhuma capa selecionada", text_color=theme.MUTED)
            self.cover_clear_btn.pack_forget()

    def _choose_cover(self):
        path = filedialog.askopenfilename(title="Escolher capa", filetypes=[("Imagens", "*.jpg *.jpeg *.png *.webp")])
        if not path:
            return
        self.app.toast("Importando capa...", "info")

        def task():
            return service.import_image(path)

        def done(local):
            self.cover_path = local
            self._update_cover_label()
            self._save_silent()
            self.app.toast("Capa definida para todos os vídeos", "success")

        self.app.run_async(task, on_done=done)

    def _clear_cover(self):
        self.cover_path = ""
        self._update_cover_label()
        self._save_silent()

    def _render_loop(self, loop):
        self.videos = loop.get("videos", [])
        self.cover_path = next((v.get("cover_path") for v in self.videos if v.get("cover_path")), "")
        self._update_cover_label()
        self.interval_entry.delete(0, "end")
        self.interval_entry.insert(0, str(loop.get("interval_seconds", 120)))
        self.batch_size_entry.delete(0, "end")
        self.batch_size_entry.insert(0, str(loop.get("batch_size", 3)))
        self.batch_interval_entry.delete(0, "end")
        self.batch_interval_entry.insert(0, str(loop.get("batch_interval_minutes", 360)))
        self.mode_seg.set("Recorrente" if loop.get("mode") == "recorrente" else "Contínuo")
        self._on_mode_change()
        self.caption_box.delete("1.0", "end")
        self.caption_box.insert("1.0", loop.get("caption", ""))
        running = loop.get("is_running")
        if running:
            modo = "recorrente" if loop.get("mode") == "recorrente" else "contínuo"
            txt = f"● Loop {modo} rodando — {loop.get('total_posts', 0)} posts"
            if loop.get("last_error"):
                txt += f" | {loop['last_error']}"
            self.status_label.configure(text=txt, text_color=theme.SUCCESS)
        else:
            self.status_label.configure(text="Loop parado", text_color=theme.MUTED)
        self._render_videos()

    def _render_videos(self):
        for c in self.videos_frame.winfo_children():
            c.destroy()
        if not self.videos:
            ctk.CTkLabel(self.videos_frame, text="Nenhum vídeo. Clique em + Adicionar vídeos.", text_color=theme.MUTED).pack(pady=24)
            return
        for i, v in enumerate(self.videos):
            row = ctk.CTkFrame(self.videos_frame, fg_color=theme.CARD2, corner_radius=10)
            row.pack(fill="x", padx=6, pady=4)
            ctk.CTkLabel(row, text=f"{i+1}", width=28, text_color=theme.MUTED, font=(theme.FONT, 12, "bold")).pack(side="left", padx=(10, 4), pady=8)
            ctk.CTkLabel(row, text=Path(v["video_path"]).name, text_color=theme.TEXT, font=(theme.FONT, 12), anchor="w").pack(side="left", fill="x", expand=True)
            ctk.CTkButton(row, text="✕", width=30, height=28, fg_color="transparent", hover_color=theme.DANGER_HOVER,
                          text_color=theme.DANGER, command=lambda idx=i: self._remove_video(idx)).pack(side="right", padx=8)

    def _add_videos(self):
        paths = filedialog.askopenfilenames(title="Escolher vídeos", filetypes=[("Vídeos", "*.mp4 *.mov *.m4v *.webm *.avi")])
        if not paths:
            return
        self.app.toast("Importando vídeos...", "info")

        def task():
            added = []
            for p in paths:
                local = service.import_video(p)
                added.append({"video_path": local, "cover_path": "", "caption": ""})
            return added

        def done(added):
            self.videos.extend(added)
            self._render_videos()
            self._save_silent()
            self.app.toast(f"{len(added)} vídeo(s) adicionado(s)", "success")

        self.app.run_async(task, on_done=done)

    def _remove_video(self, idx):
        if 0 <= idx < len(self.videos):
            self.videos.pop(idx)
            self._render_videos()
            self._save_silent()

    def _clear_videos(self):
        self.videos = []
        self._render_videos()
        self._save_silent()

    def _loop_kwargs(self):
        return {
            "mode": "recorrente" if self.mode_seg.get() == "Recorrente" else "continuo",
            "batch_size": _to_int(self.batch_size_entry.get(), 3, lo=1),
            "batch_interval_minutes": _to_int(self.batch_interval_entry.get(), 360, lo=5),
        }

    def _videos_payload(self):
        """Aplica a capa única a todos os vídeos."""
        return [{**v, "cover_path": self.cover_path} for v in self.videos]

    def _save_silent(self):
        acc_id = self._selected_account_id()
        if not acc_id:
            return
        interval = _to_int(self.interval_entry.get(), 120)
        caption = self.caption_box.get("1.0", "end").strip()
        kw = self._loop_kwargs()
        videos = self._videos_payload()
        self.app.run_async(lambda: service.save_loop(acc_id, videos, interval, caption, **kw))

    def _start(self):
        acc_id = self._selected_account_id()
        if not acc_id:
            self.app.toast("Selecione uma conta", "error")
            return
        if not self.videos:
            self.app.toast("Adicione vídeos antes de iniciar", "error")
            return
        interval = _to_int(self.interval_entry.get(), 120)
        caption = self.caption_box.get("1.0", "end").strip()
        kw = self._loop_kwargs()
        videos = self._videos_payload()

        def task():
            service.save_loop(acc_id, videos, interval, caption, **kw)
            service.set_loop_running(acc_id, True)

        self.app.run_async(task, on_done=lambda _r: (
            self.app.toast("Loop iniciado", "success"), self._load_loop(), self._update_running_panel(),
        ))

    def _stop(self):
        acc_id = self._selected_account_id()
        if not acc_id:
            return
        self.app.run_async(lambda: service.set_loop_running(acc_id, False),
                           on_done=lambda _r: (
                               self.app.toast("Loop parado", "info"), self._load_loop(), self._update_running_panel(),
                           ))

    def _stop_all(self):
        self.app.run_async(service.stop_all_loops, on_done=self._after_stop_all)

    def _after_stop_all(self, count):
        if count:
            self.app.toast(f"{count} loop(s) parado(s)", "success")
        else:
            self.app.toast("Nenhum loop estava rodando", "info")
        self._load_loop()
        self._update_running_panel()


def _to_int(value, default, lo=30):
    try:
        return max(lo, int(str(value).strip() or default))
    except ValueError:
        return default
