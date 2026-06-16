import asyncio
import logging

from app.database import SessionLocal
from app.services.loop_stagger import process_stagger_queues

logger = logging.getLogger("loop_stagger_worker")
_worker_task: asyncio.Task | None = None


async def _worker_loop() -> None:
    while True:
        db = SessionLocal()
        try:
            process_stagger_queues(db)
            db.commit()
        except Exception:
            logger.exception("Erro no worker de fila escalonada")
            db.rollback()
        finally:
            db.close()
        await asyncio.sleep(20)


def start_loop_stagger_worker() -> None:
    global _worker_task
    if _worker_task and not _worker_task.done():
        return
    _worker_task = asyncio.create_task(_worker_loop())
    logger.info("Loop stagger worker iniciado")
