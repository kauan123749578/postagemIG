"""Workers de fundo: automações + agendamentos (stories/reels)."""
import logging
import threading

from core import automations as auto_svc
from core import service

POLL_SECONDS = 5

logger = logging.getLogger(__name__)


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
        changed = False
        for post_id in service.list_due_scheduled_ids(limit=3):
            if service.process_scheduled_post(post_id):
                changed = True
        return changed
