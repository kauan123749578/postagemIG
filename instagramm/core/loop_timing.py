"""Intervalos do loop com variação aleatória (anti-padrão de robô)."""
import random

JITTER_MAX_SECONDS = 180  # ±3 min no máximo
JITTER_FRACTION = 0.15    # ou ±15% do intervalo


def jitter_seconds(base_seconds: float) -> float:
    base = max(1.0, float(base_seconds))
    spread = min(JITTER_MAX_SECONDS, base * JITTER_FRACTION)
    offset = random.uniform(-spread, spread)
    return max(15.0, base + offset)
