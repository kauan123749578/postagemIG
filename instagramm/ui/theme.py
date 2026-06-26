"""Paleta e helpers visuais do painel (tema escuro premium)."""

BG = "#0a0a12"
SIDEBAR = "#0d0d18"
CARD = "#15151f"
CARD2 = "#1b1b29"
BORDER = "#26263c"
PRIMARY = "#a855f7"
PRIMARY_HOVER = "#9333ea"
PINK = "#ec4899"
ACCENT = "#38bdf8"
TEXT = "#f4f4fa"
MUTED = "#8b8bab"
SUCCESS = "#4ade80"
WARNING = "#fbbf24"
DANGER = "#f87171"
DANGER_HOVER = "#dc2626"

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
