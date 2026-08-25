"""Calendário mensal para selecionar dias (Stories)."""
from __future__ import annotations

import calendar
from datetime import date

import customtkinter as ctk

from ui import theme


class MonthCalendar(ctk.CTkFrame):
    """Grade do mês; clique nos dias para selecionar/desmarcar."""

    WEEKDAYS = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]

    def __init__(self, master, on_change=None, **kwargs):
        super().__init__(master, fg_color=theme.CARD2, corner_radius=12, border_width=1, border_color=theme.BORDER, **kwargs)
        self.on_change = on_change
        today = date.today()
        self.year = today.year
        self.month = today.month
        self.selected: set[date] = {today}

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=10, pady=(10, 4))
        ctk.CTkButton(
            head, text="‹", width=36, height=32, corner_radius=8,
            fg_color=theme.CARD3, hover_color=theme.PRIMARY, text_color=theme.TEXT,
            command=self._prev_month,
        ).pack(side="left")
        self.title_lbl = ctk.CTkLabel(
            head, text="", font=(theme.FONT, 13, "bold"), text_color=theme.TEXT,
        )
        self.title_lbl.pack(side="left", expand=True)
        ctk.CTkButton(
            head, text="›", width=36, height=32, corner_radius=8,
            fg_color=theme.CARD3, hover_color=theme.PRIMARY, text_color=theme.TEXT,
            command=self._next_month,
        ).pack(side="right")

        tools = ctk.CTkFrame(self, fg_color="transparent")
        tools.pack(fill="x", padx=10, pady=(0, 6))
        ctk.CTkButton(
            tools, text="Selecionar todos", height=28, corner_radius=8, width=120,
            fg_color=theme.CARD3, hover_color=theme.PRIMARY_SOFT, text_color=theme.TEXT,
            font=(theme.FONT, 11), command=self._select_all_month,
        ).pack(side="left")
        ctk.CTkButton(
            tools, text="Limpar", height=28, corner_radius=8, width=70,
            fg_color=theme.CARD3, hover_color=theme.CARD, text_color=theme.MUTED,
            font=(theme.FONT, 11), command=self._clear,
        ).pack(side="left", padx=(8, 0))
        self.count_lbl = ctk.CTkLabel(tools, text="0 dias", font=(theme.FONT, 11), text_color=theme.MUTED)
        self.count_lbl.pack(side="right")

        self.grid_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.grid_frame.pack(fill="x", padx=8, pady=(0, 10))
        self._day_btns: dict[int, ctk.CTkButton] = {}
        self._rebuild()

    def selected_dates(self) -> list[date]:
        return sorted(self.selected)

    def _notify(self):
        self.count_lbl.configure(text=f"{len(self.selected)} dia(s) selecionado(s)")
        if self.on_change:
            try:
                self.on_change()
            except Exception:  # noqa: BLE001
                pass

    def _prev_month(self):
        if self.month == 1:
            self.month, self.year = 12, self.year - 1
        else:
            self.month -= 1
        self._rebuild()

    def _next_month(self):
        if self.month == 12:
            self.month, self.year = 1, self.year + 1
        else:
            self.month += 1
        self._rebuild()

    def _select_all_month(self):
        _, last = calendar.monthrange(self.year, self.month)
        for d in range(1, last + 1):
            self.selected.add(date(self.year, self.month, d))
        self._rebuild()

    def _clear(self):
        self.selected.clear()
        self._rebuild()

    def _toggle(self, day: int):
        d = date(self.year, self.month, day)
        if d in self.selected:
            self.selected.discard(d)
        else:
            self.selected.add(d)
        self._style_day(day)
        self._notify()

    def _style_day(self, day: int):
        btn = self._day_btns.get(day)
        if not btn:
            return
        d = date(self.year, self.month, day)
        on = d in self.selected
        btn.configure(
            fg_color=theme.PRIMARY_SOFT if on else theme.CARD3,
            text_color=theme.PRIMARY if on else theme.TEXT,
            border_color=theme.PRIMARY if on else theme.BORDER,
            border_width=1 if on else 0,
        )

    def _rebuild(self):
        for w in self.grid_frame.winfo_children():
            w.destroy()
        self._day_btns.clear()
        months = [
            "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
            "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
        ]
        self.title_lbl.configure(text=f"{months[self.month]} {self.year}")

        for i, name in enumerate(self.WEEKDAYS):
            ctk.CTkLabel(
                self.grid_frame, text=name, width=36, font=(theme.FONT, 10, "bold"),
                text_color=theme.MUTED,
            ).grid(row=0, column=i, padx=2, pady=2)

        # calendar: Monday=0 by default; we want Sunday first
        cal = calendar.Calendar(firstweekday=6)
        row = 1
        for week in cal.monthdayscalendar(self.year, self.month):
            for col, day in enumerate(week):
                if day == 0:
                    ctk.CTkLabel(self.grid_frame, text="", width=36, height=32).grid(
                        row=row, column=col, padx=2, pady=2,
                    )
                    continue
                btn = ctk.CTkButton(
                    self.grid_frame, text=str(day), width=36, height=32, corner_radius=8,
                    fg_color=theme.CARD3, hover_color=theme.PRIMARY_SOFT,
                    text_color=theme.TEXT, font=(theme.FONT, 12, "bold"),
                    command=lambda d=day: self._toggle(d),
                )
                btn.grid(row=row, column=col, padx=2, pady=2)
                self._day_btns[day] = btn
                self._style_day(day)
            row += 1
        self._notify()
