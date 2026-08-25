"""Widgets reutilizáveis do painel (estilo premium)."""
import customtkinter as ctk

from ui import theme


def soft_scrollable(master, **kwargs):
    """CTkScrollableFrame com roda do mouse mais leve (menos 'duro')."""
    opts = dict(
        fg_color="transparent",
        scrollbar_button_color=theme.CARD3,
        scrollbar_button_hover_color=theme.PRIMARY,
    )
    opts.update(kwargs)
    frame = ctk.CTkScrollableFrame(master, **opts)
    canvas = frame._parent_canvas  # noqa: SLF001
    try:
        canvas.configure(yscrollincrement=8)
    except Exception:  # noqa: BLE001
        pass
    try:
        frame._scrollbar.configure(width=14)  # noqa: SLF001
    except Exception:  # noqa: BLE001
        pass

    def _wheel(event):
        # Windows: delta ±120; passos menores = scroll fluido
        steps = int(-1 * (event.delta / 40)) or (-1 if event.delta > 0 else 1)
        canvas.yview_scroll(steps, "units")
        return "break"

    def _enter(_event):
        canvas.bind_all("<MouseWheel>", _wheel)

    def _leave(_event):
        canvas.unbind_all("<MouseWheel>")

    frame.bind("<Enter>", _enter)
    frame.bind("<Leave>", _leave)
    return frame


def card(master, **kwargs):
    opts = dict(fg_color=theme.CARD, corner_radius=16, border_width=1, border_color=theme.BORDER)
    opts.update(kwargs)
    return ctk.CTkFrame(master, **opts)


def section(master, title_text, subtitle_text="", icon="", **kwargs):
    """Card premium com cabeçalho (ícone + título + subtítulo) e corpo.

    Retorna (card, body) — adicione seus widgets em `body`.
    """
    c = card(master, **kwargs)
    head = ctk.CTkFrame(c, fg_color="transparent")
    head.pack(fill="x", padx=20, pady=(16, 4))
    if icon:
        ctk.CTkLabel(head, text=icon, font=(theme.FONT, 20)).pack(side="left", padx=(0, 10))
    titles = ctk.CTkFrame(head, fg_color="transparent")
    titles.pack(side="left", fill="x", expand=True)
    ctk.CTkLabel(titles, text=title_text, font=(theme.FONT, 15, "bold"), text_color=theme.TEXT).pack(anchor="w")
    if subtitle_text:
        ctk.CTkLabel(titles, text=subtitle_text, font=(theme.FONT, 11), text_color=theme.MUTED).pack(anchor="w")
    body = ctk.CTkFrame(c, fg_color="transparent")
    body.pack(fill="both", expand=True, padx=20, pady=(6, 18))
    return c, body


def title(master, text, size=20, **kwargs):
    return ctk.CTkLabel(master, text=text, font=(theme.FONT, size, "bold"), text_color=theme.TEXT, **kwargs)


def subtitle(master, text, **kwargs):
    return ctk.CTkLabel(master, text=text, font=(theme.FONT, 12), text_color=theme.MUTED, **kwargs)


def field_label(master, text):
    return ctk.CTkLabel(master, text=text.upper(), font=(theme.FONT, 11, "bold"), text_color=theme.MUTED, anchor="w")


def entry(master, placeholder="", show=None, **kwargs):
    return ctk.CTkEntry(
        master,
        placeholder_text=placeholder,
        show=show,
        height=40,
        corner_radius=10,
        fg_color=theme.CARD2,
        border_color=theme.BORDER,
        text_color=theme.TEXT,
        **kwargs,
    )


def primary_button(master, text, command, **kwargs):
    kwargs.setdefault("height", 44)
    kwargs.setdefault("corner_radius", 12)
    kwargs.setdefault("font", (theme.FONT, 13, "bold"))
    return ctk.CTkButton(
        master, text=text, command=command,
        fg_color=theme.PRIMARY, hover_color=theme.PRIMARY_HOVER, text_color="#ffffff",
        **kwargs,
    )


def ghost_button(master, text, command, **kwargs):
    kwargs.setdefault("height", 44)
    kwargs.setdefault("corner_radius", 12)
    kwargs.setdefault("font", (theme.FONT, 13))
    return ctk.CTkButton(
        master, text=text, command=command,
        fg_color=theme.CARD2, hover_color=theme.CARD3, text_color=theme.TEXT_SOFT,
        border_width=1, border_color=theme.BORDER,
        **kwargs,
    )


def danger_button(master, text, command, **kwargs):
    kwargs.setdefault("height", 40)
    kwargs.setdefault("corner_radius", 12)
    kwargs.setdefault("font", (theme.FONT, 12, "bold"))
    return ctk.CTkButton(
        master, text=text, command=command,
        fg_color=theme.DANGER_SOFT, hover_color=theme.DANGER_HOVER, text_color=theme.DANGER,
        border_width=1, border_color=theme.BORDER,
        **kwargs,
    )


def chip(master, text, color=theme.ACCENT, soft=theme.PRIMARY_SOFT):
    return ctk.CTkLabel(
        master,
        text=f"  {text}  ",
        font=(theme.FONT, 11, "bold"),
        text_color=color,
        fg_color=soft,
        corner_radius=8,
        height=24,
    )


def status_pill(master, status):
    color = theme.STATUS_COLORS.get(status, theme.MUTED)
    label = theme.STATUS_LABELS.get(status, status or "—")
    return ctk.CTkLabel(
        master,
        text=f"● {label}",
        font=(theme.FONT, 11, "bold"),
        text_color=color,
    )


def render_running_tasks(container, tasks, *, empty_text="Nenhuma automação rodando no momento", on_stop=None):
    """Preenche um frame com a lista de contas/automações ativas.

    Se `on_stop` for passado, mostra um botão "Parar" por conta de loop,
    chamado como on_stop(account_id).
    """
    for child in container.winfo_children():
        child.destroy()
    if not tasks:
        ctk.CTkLabel(
            container, text=empty_text, text_color=theme.MUTED, font=(theme.FONT, 12),
        ).pack(anchor="w", pady=8)
        return
    for task in tasks:
        row = ctk.CTkFrame(container, fg_color=theme.CARD2, corner_radius=10)
        row.pack(fill="x", pady=4)
        ctk.CTkLabel(row, text=task.get("icon", "●"), font=(theme.FONT, 16)).pack(
            side="left", padx=(12, 6), pady=10,
        )
        text_frame = ctk.CTkFrame(row, fg_color="transparent")
        text_frame.pack(side="left", fill="x", expand=True, pady=8)
        ctk.CTkLabel(
            text_frame, text=task["title"], font=(theme.FONT, 13, "bold"),
            text_color=theme.TEXT, anchor="w",
        ).pack(anchor="w")
        sub = task.get("activity", "")
        if task.get("detail"):
            sub = f"{sub} · {task['detail']}"
        ctk.CTkLabel(
            text_frame, text=sub, font=(theme.FONT, 11),
            text_color=theme.SUCCESS, anchor="w",
        ).pack(anchor="w")
        if on_stop is not None and task.get("type") in ("loop", "automation"):
            stop_id = task.get("automation_id") if task.get("type") == "automation" else task.get("account_id")
            danger_button(
                row, "⏹ Pausar" if task.get("type") == "automation" else "⏹ Parar",
                lambda i=stop_id: on_stop(i), height=32, width=90,
            ).pack(side="right", padx=(6, 12), pady=10)
        chip(row, "RODANDO", color=theme.SUCCESS, soft=theme.SUCCESS_SOFT).pack(
            side="right", padx=(12, 6), pady=10,
        )


class Stepper(ctk.CTkFrame):
    """Campo numérico premium com botões – e +."""

    def __init__(self, master, default=0, lo=0, hi=999, width=150):
        super().__init__(master, fg_color=theme.CARD2, corner_radius=10, border_width=1, border_color=theme.BORDER)
        self.lo, self.hi = lo, hi
        self.minus = ctk.CTkButton(self, text="–", width=36, height=36, corner_radius=8,
                                   fg_color=theme.CARD3, hover_color=theme.PRIMARY, text_color=theme.TEXT,
                                   font=(theme.FONT, 18, "bold"), command=lambda: self._step(-1))
        self.minus.pack(side="left", padx=3, pady=3)
        self._entry = ctk.CTkEntry(self, width=max(40, width - 90), height=36, justify="center",
                                   fg_color="transparent", border_width=0, text_color=theme.TEXT,
                                   font=(theme.FONT, 15, "bold"))
        self._entry.pack(side="left", fill="x", expand=True)
        self.plus = ctk.CTkButton(self, text="+", width=36, height=36, corner_radius=8,
                                  fg_color=theme.CARD3, hover_color=theme.PRIMARY, text_color=theme.TEXT,
                                  font=(theme.FONT, 16, "bold"), command=lambda: self._step(1))
        self.plus.pack(side="left", padx=3, pady=3)
        self.set(default)

    def _step(self, delta):
        self.set(self.get() + delta)

    def get(self):
        try:
            return max(self.lo, min(self.hi, int(str(self._entry.get()).strip() or 0)))
        except ValueError:
            return self.lo

    def set(self, value):
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = self.lo
        value = max(self.lo, min(self.hi, value))
        self._entry.delete(0, "end")
        self._entry.insert(0, str(value))
