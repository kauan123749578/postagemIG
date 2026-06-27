"""Workers de fundo: loop contínuo e agendamentos.

Rodam numa thread separada para não travar a interface.
"""
import json
import threading
import time
from datetime import datetime, timedelta, timezone

from core import service
from core.db import Account, LoopConfig, ScheduledPost, SessionLocal, StaggerItem, WarmConfig

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
                changed = self._process_stagger()
                changed = self._process_loops() or changed
                changed = self._process_scheduled() or changed
                changed = self._process_warming() or changed
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

                recorrente = (loop.mode or "continuo") == "recorrente"
                # início de um novo lote
                if recorrente and (loop.batch_remaining or 0) <= 0:
                    loop.batch_remaining = max(1, loop.batch_size or 1)

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
                    if recorrente:
                        loop.batch_remaining = max(0, (loop.batch_remaining or 1) - 1)
                        if loop.batch_remaining > 0:
                            # próximo vídeo do mesmo lote
                            loop.next_run_at = _now() + timedelta(seconds=loop.interval_seconds)
                        else:
                            # lote concluído — espera o intervalo recorrente
                            loop.next_run_at = _now() + timedelta(minutes=loop.batch_interval_minutes or 360)
                    else:
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

    # ---- fila escalonada ----
    def _process_stagger(self) -> bool:
        account_ids = []
        db = SessionLocal()
        try:
            items = db.query(StaggerItem).filter(StaggerItem.status == "pending").all()
            for it in items:
                act = it.activate_at
                if act and act.tzinfo is None:
                    act = act.replace(tzinfo=timezone.utc)
                if act and act > _now():
                    continue
                it.status = "activated"
                account_ids.append(it.account_id)
            if account_ids:
                db.commit()
        finally:
            db.close()

        for acc_id in account_ids:
            service.set_loop_running(acc_id, True)
        return bool(account_ids)

    # ---- aquecimento ----
    def _process_warming(self) -> bool:
        import random

        changed = False
        db = SessionLocal()
        due_ids = []
        try:
            warms = db.query(WarmConfig).filter(WarmConfig.is_running.is_(True)).all()
            for w in warms:
                acc = db.get(Account, w.account_id)
                if not acc or not acc.is_active or acc.status != "healthy":
                    continue
                # respeita a janela de horário (pausa automática fora dela)
                start = w.active_start_hour if w.active_start_hour is not None else 8
                end = w.active_end_hour if w.active_end_hour is not None else 23
                if not service.within_active_window(start, end):
                    continue
                nxt = w.next_run_at
                if nxt and nxt.tzinfo is None:
                    nxt = nxt.replace(tzinfo=timezone.utc)
                if nxt and nxt > _now():
                    continue
                due_ids.append((w.account_id, w.interval_minutes))
        finally:
            db.close()

        for account_id, interval in due_ids:
            service.run_warm_once(account_id)
            # agenda o próximo com variação de ±30%
            jitter = random.uniform(0.7, 1.3)
            nxt = _now() + timedelta(minutes=max(5, interval) * jitter)
            db = SessionLocal()
            try:
                w = db.query(WarmConfig).filter(WarmConfig.account_id == account_id).first()
                if w and w.is_running:
                    w.next_run_at = nxt
                    db.commit()
            finally:
                db.close()
            changed = True
        return changed
