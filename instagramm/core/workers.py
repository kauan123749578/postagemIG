"""Workers de fundo: loop contínuo e agendamentos.

Rodam numa thread separada para não travar a interface.
"""
import json
import threading
import time
from datetime import datetime, timedelta, timezone

from core import service
from core.db import Account, LoopConfig, ScheduledPost, SessionLocal

POLL_SECONDS = 5
RATE_LIMIT_BACKOFF = 600  # 10 min após limite do Instagram


def _now() -> datetime:
    return datetime.now(timezone.utc)


class WorkerManager:
    def __init__(self, on_change=None):
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.on_change = on_change  # callback para a UI atualizar

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
                changed = self._process_loops()
                changed = self._process_scheduled() or changed
                if changed:
                    self._notify()
            except Exception:  # noqa: BLE001
                pass
            self._stop.wait(POLL_SECONDS)

    # ---- loops contínuos ----
    def _process_loops(self) -> bool:
        changed = False
        db = SessionLocal()
        try:
            loops = db.query(LoopConfig).filter(LoopConfig.is_running.is_(True)).all()
            for loop in loops:
                acc = db.get(Account, loop.account_id)
                if not acc or not acc.is_active:
                    continue
                if loop.next_run_at and loop.next_run_at.tzinfo is None:
                    loop.next_run_at = loop.next_run_at.replace(tzinfo=timezone.utc)
                if loop.next_run_at and loop.next_run_at > _now():
                    continue
                videos = json.loads(loop.videos_json or "[]")
                if not videos:
                    loop.is_running = False
                    loop.last_error = "Sem vídeos na lista"
                    db.commit()
                    changed = True
                    continue

                ok, reason = service.can_post(acc.id)
                if not ok:
                    loop.next_run_at = _now() + timedelta(seconds=120)
                    loop.last_error = reason
                    db.commit()
                    changed = True
                    continue

                idx = loop.current_index % len(videos)
                item = videos[idx]
                result = service.post_reel_now(
                    acc.id,
                    item.get("video_path", ""),
                    item.get("caption") or loop.caption,
                    item.get("cover_path") or None,
                )
                if result.get("ok"):
                    loop.total_posts += 1
                    loop.current_index = (loop.current_index + 1) % len(videos)
                    loop.last_error = ""
                    loop.next_run_at = _now() + timedelta(seconds=loop.interval_seconds)
                else:
                    loop.last_error = result.get("message", "Erro")
                    backoff = RATE_LIMIT_BACKOFF if result.get("kind") == "rate_limit" else loop.interval_seconds
                    loop.next_run_at = _now() + timedelta(seconds=backoff)
                db.commit()
                changed = True
        finally:
            db.close()
        return changed

    # ---- agendamentos ----
    def _process_scheduled(self) -> bool:
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
                ok, reason = service.can_post(post.account_id)
                if not ok:
                    continue  # tenta de novo no próximo ciclo
                result = service.post_reel_now(post.account_id, post.video_path, post.caption, post.cover_path or None)
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
