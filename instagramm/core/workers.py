"""Workers de fundo: automações Instablack + agendamentos manuais.

Rodam numa thread separada para não travar a interface.
Loop/aquecimento/escalonada antigos foram desativados.
"""
import logging
import threading
from datetime import datetime, timezone

from core import automations as auto_svc
from core import service
from core.db import ScheduledPost, SessionLocal

POLL_SECONDS = 5

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class WorkerManager:
    def __init__(self, on_change=None):
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.on_change = on_change

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _notify(self) -> None:
        if self.on_change:
            try:
                self.on_change()
            except Exception:  # noqa: BLE001
                pass

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                changed = self._process_automations()
                changed = self._process_scheduled() or changed
                if changed:
                    self._notify()
            except Exception:  # noqa: BLE001
                logger.exception("Erro no worker de fundo")
            self._stop.wait(POLL_SECONDS)

    def _process_automations(self) -> bool:
        changed = False
        for job_id in auto_svc.list_due_automation_job_ids(limit=3):
            if auto_svc.process_automation_job(job_id):
                changed = True
        return changed

    def _process_scheduled(self) -> bool:
        """Agendamentos manuais (tela Agendamentos) — mantidos."""
        changed = False
        db = SessionLocal()
        try:
            due = (
                db.query(ScheduledPost)
                .filter(ScheduledPost.status == "pending")
                .order_by(ScheduledPost.scheduled_at)
                .all()
            )
            for post in due:
                sched = post.scheduled_at
                if sched and sched.tzinfo is None:
                    sched = sched.replace(tzinfo=timezone.utc)
                if sched and sched > _now():
                    continue
                ok, _reason = service.can_post(post.account_id)
                if not ok:
                    continue
                result = service.post_reel_now(
                    post.account_id, post.video_path, post.caption, post.cover_path or None
                )
                if result.get("ok"):
                    post.status = "posted"
                else:
                    post.status = "error"
                    post.error_message = result.get("message", "Erro")
                db.commit()
                changed = True
        finally:
            db.close()
        return changed
