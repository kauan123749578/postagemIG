"""Widgets reutilizáveis do painel."""
import customtkinter as ctk

from ui import theme


def card(master, **kwargs):
    opts = dict(fg_color=theme.CARD, corner_radius=16, border_width=1, border_color=theme.BORDER)
    opts.update(kwargs)
    return ctk.CTkFrame(master, **opts)


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
    return ctk.CTkButton(
        master,
        text=text,
        command=command,
        height=42,
        corner_radius=10,
        fg_color=theme.PRIMARY,
        hover_color=theme.PRIMARY_HOVER,
        text_color="#ffffff",
        font=(theme.FONT, 13, "bold"),
        **kwargs,
    )


def ghost_button(master, text, command, **kwargs):
    return ctk.CTkButton(
        master,
        text=text,
        command=command,
        height=42,
        corner_radius=10,
        fg_color="transparent",
        hover_color=theme.CARD2,
        text_color=theme.MUTED,
        border_width=1,
        border_color=theme.BORDER,
        font=(theme.FONT, 13),
        **kwargs,
    )


def danger_button(master, text, command, **kwargs):
    return ctk.CTkButton(
        master,
        text=text,
        command=command,
        height=38,
        corner_radius=10,
        fg_color="transparent",
        hover_color=theme.DANGER_HOVER,
        text_color=theme.DANGER,
        border_width=1,
        border_color=theme.BORDER,
        font=(theme.FONT, 12, "bold"),
        **kwargs,
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
