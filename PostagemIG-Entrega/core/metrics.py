"""Contadores diários para os gráficos do dashboard."""
from datetime import datetime, timedelta

from core.db import DailyMetric, SessionLocal


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def bump(key: str, n: int = 1) -> None:
    """Incrementa o contador do dia para uma chave (post, like, comment, ...)."""
    if not n:
        return
    db = SessionLocal()
    try:
        day = _today()
        row = db.query(DailyMetric).filter(DailyMetric.day == day, DailyMetric.key == key).first()
        if row is None:
            row = DailyMetric(day=day, key=key, value=0)
            db.add(row)
        row.value += int(n)
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    finally:
        db.close()


def bump_many(counts: dict) -> None:
    for key, n in counts.items():
        bump(key, n)


def series(key: str, days: int = 7) -> list[dict]:
    """Série diária de uma chave nos últimos N dias (preenche zeros)."""
    today = datetime.now().date()
    span = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]
    day_strs = [d.strftime("%Y-%m-%d") for d in span]

    db = SessionLocal()
    try:
        rows = (
            db.query(DailyMetric)
            .filter(DailyMetric.key == key, DailyMetric.day.in_(day_strs))
            .all()
        )
        found = {r.day: r.value for r in rows}
    finally:
        db.close()
    return [{"day": d.strftime("%d/%m"), "value": found.get(d.strftime("%Y-%m-%d"), 0)} for d in span]


def series_sum(keys: list[str], days: int = 7) -> list[dict]:
    """Soma de várias chaves por dia (ex.: todas as ações de aquecimento)."""
    base = None
    for key in keys:
        s = series(key, days)
        if base is None:
            base = [{"day": x["day"], "value": x["value"]} for x in s]
        else:
            for i, x in enumerate(s):
                base[i]["value"] += x["value"]
    return base or []


def totals(keys: list[str], days: int = 7) -> dict:
    """Total acumulado de cada chave nos últimos N dias."""
    today = datetime.now().date()
    day_strs = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
    db = SessionLocal()
    try:
        rows = (
            db.query(DailyMetric)
            .filter(DailyMetric.key.in_(keys), DailyMetric.day.in_(day_strs))
            .all()
        )
        out = {k: 0 for k in keys}
        for r in rows:
            out[r.key] = out.get(r.key, 0) + r.value
        return out
    finally:
        db.close()
