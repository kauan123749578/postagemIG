"""Paleta e helpers visuais — tema preto + dourado."""

# fundos pretos em camadas
BG = "#050505"
SIDEBAR = "#0a0a0a"
CARD = "#111111"
CARD2 = "#181818"
CARD3 = "#222222"
BORDER = "#2e2e2e"
BORDER_SOFT = "#1c1c1c"

# dourado como destaque
PRIMARY = "#d4af37"
PRIMARY_HOVER = "#b8962e"
PRIMARY_SOFT = "#2a220e"
PINK = "#e0c15a"
ACCENT = "#e8c547"
ACCENT_2 = "#c9a227"

# textos
TEXT = "#f2f2f2"
TEXT_SOFT = "#b8b8b8"
MUTED = "#6e6e6e"

SUCCESS = "#3d9a55"
SUCCESS_SOFT = "#0f2418"
WARNING = "#d4af37"
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
    "banned": DANGER,
    "warning": WARNING,
    "unknown": MUTED,
}

STATUS_LABELS = {
    "healthy": "Conectada",
    "pending": "Checkpoint",
    "error": "Sessão caída",
    "banned": "Banida",
    "warning": "Atenção",
    "unknown": "Sem sessão",
}
