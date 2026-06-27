"""Paleta e helpers visuais do painel (tema dark profundo: preto / azul / branco)."""

# fundos quase pretos, com camadas sutis
BG = "#04060a"
SIDEBAR = "#060810"
CARD = "#0a0d15"
CARD2 = "#0f131d"
CARD3 = "#141926"
BORDER = "#1a2030"

# azul como cor de destaque
PRIMARY = "#2f6bff"
PRIMARY_HOVER = "#2456d6"
PINK = "#3b82f6"
ACCENT = "#4f9bff"

# textos mais sóbrios (menos estourados que branco puro)
TEXT = "#d4dae6"
TEXT_SOFT = "#aab3c5"
MUTED = "#5e6878"

SUCCESS = "#2ea043"
WARNING = "#c08a1e"
DANGER = "#e5484d"
DANGER_HOVER = "#a01f23"

FONT = "Segoe UI"
FONT_MONO = "Consolas"

STATUS_COLORS = {
    "healthy": SUCCESS,
    "pending": ACCENT,
    "error": DANGER,
    "warning": WARNING,
    "unknown": MUTED,
}

STATUS_LABELS = {
    "healthy": "Conectada",
    "pending": "Aguardando 2FA",
    "error": "Erro",
    "warning": "Atenção",
    "unknown": "Sem sessão",
}
