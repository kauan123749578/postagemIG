"""Paleta e helpers visuais do painel (tema dark premium: preto / azul / branco)."""

# fundos quase pretos, com camadas sutis
BG = "#04060a"
SIDEBAR = "#070910"
CARD = "#0b0e16"
CARD2 = "#10141e"
CARD3 = "#161c29"
BORDER = "#1c2433"
BORDER_SOFT = "#141a26"

# azul como cor de destaque (+ tom suave para realces)
PRIMARY = "#2f6bff"
PRIMARY_HOVER = "#2456d6"
PRIMARY_SOFT = "#13203c"
PINK = "#3b82f6"
ACCENT = "#4f9bff"
ACCENT_2 = "#22d3ee"

# textos
TEXT = "#e7ecf5"
TEXT_SOFT = "#aab3c5"
MUTED = "#5e6878"

SUCCESS = "#2ea043"
SUCCESS_SOFT = "#0f2418"
WARNING = "#d29a1e"
WARNING_SOFT = "#2a2110"
DANGER = "#e5484d"
DANGER_HOVER = "#a01f23"
DANGER_SOFT = "#2a1416"

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
