"""Paleta e helpers visuais do painel (tema azul / branco / preto)."""

BG = "#070b12"
SIDEBAR = "#0b1019"
CARD = "#101723"
CARD2 = "#18212f"
BORDER = "#243044"
PRIMARY = "#2f81f7"
PRIMARY_HOVER = "#2563eb"
PINK = "#38bdf8"
ACCENT = "#38bdf8"
TEXT = "#f5f8ff"
MUTED = "#8b98ac"
SUCCESS = "#3fb950"
WARNING = "#d29922"
DANGER = "#f85149"
DANGER_HOVER = "#b62324"

FONT = "Segoe UI"

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
