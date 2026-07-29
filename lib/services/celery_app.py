#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Celery task queue configuration with local eager fallback."""

from __future__ import annotations

import socket
from datetime import datetime
from typing import Any, Dict
from urllib.parse import urlparse

import structlog
from celery import Celery
from celery.signals import task_failure, task_postrun, task_prerun

from ..config import get_settings
from ..database import ProcessingTask, SessionLocal


logger = structlog.get_logger(__name__)
settings = get_settings()


def _redis_is_reachable(redis_url: str, timeout_seconds: float = 0.25) -> bool:
    parsed = urlparse(redis_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 6379
    try:
        with socket.create_connection((host, port), timeout_seconds):
            return True
    except OSError:
        return False


def _resolve_async_mode() -> str:
    configured = (settings.ASYNC_TASKS_MODE or "auto").strip().lower()
    if configured in {"local", "eager"}:
        return "local_eager"
    if configured == "redis":
        return "redis"
    return "redis" if _redis_is_reachable(settings.REDIS_URL) else "local_eager"


ASYNC_RUNTIME_MODE = _resolve_async_mode()

celery_app = Celery(
    "cad_translation_worker",
    broker="memory://" if ASYNC_RUNTIME_MODE == "local_eager" else settings.REDIS_URL,
    backend="cache+memory://" if ASYNC_RUNTIME_MODE == "local_eager" else settings.REDIS_URL,
    include=[
        "app.services.tasks.cad_tasks",
        "app.services.tasks.translation_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=settings.CELERY_TASK_TIMEOUT,
    task_soft_time_limit=settings.CELERY_TASK_TIMEOUT - 60,
    result_expires=settings.CELERY_RESULT_EXPIRES,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_disable_rate_limits=False,
    task_compression="gzip",
    result_compression="gzip",
    task_routes={
        "app.services.tasks.cad_tasks.*": {"queue": "cad_processing"},
        "app.services.tasks.translation_tasks.*": {"queue": "translation"},
    },
    task_default_queue="default",
    task_create_missing_queues=True,
    task_always_eager=ASYNC_RUNTIME_MODE == "local_eager",
    task_store_eager_result=ASYNC_RUNTIME_MODE == "local_eager",
)


def is_local_async_mode() -> bool:
    return ASYNC_RUNTIME_MODE == "local_eager"


def update_task_status(
    task_id: str,
    status: str,
    progress: float = None,
    message: str = None,
    error_message: str = None,
) -> None:
    """Persist task status to the database when a record exists."""

    try:
        db = SessionLocal()
        task = db.query(ProcessingTask).filter(ProcessingTask.task_id == task_id).first()
        if task:
            task.status = status
            if progress is not None:
                task.progress = progress
            if message is not None:
                task.message = message
            if error_message is not None:
                task.error_message = error_message

            if status == "running" and not task.started_at:
                task.started_at = datetime.utcnow()
            elif status in ["success", "failure"]:
                task.completed_at = datetime.utcnow()

            db.commit()
            logger.info("task_status_updated", task_id=task_id, status=status, progress=progress)
        db.close()
    except Exception as exc:
        logger.error("task_status_update_failed", task_id=task_id, error=str(exc))


@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, **kwds):
    logger.info("task_started", task_id=task_id, task_name=getattr(task, "name", None))
    update_task_status(task_id, "running", 0.0, "task started")


@task_postrun.connect
def task_postrun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, retval=None, state=None, **kwds):
    logger.info("task_finished", task_id=task_id, task_name=getattr(task, "name", None), state=state)
    if state == "SUCCESS":
        update_task_status(task_id, "success", 1.0, "task completed")
    elif state == "FAILURE":
        update_task_status(task_id, "failure", None, None, "task failed")


@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, traceback=None, einfo=None, **kwds):
    logger.error("task_failed", task_id=task_id, exception=str(exception))
    update_task_status(task_id, "failure", None, None, str(exception))


class CADTask(celery_app.Task):
    """Base class for CAD processing tasks."""

    def on_success(self, retval, task_id, args, kwargs):
        logger.info("cad_task_success", task_id=task_id)
        update_task_status(task_id, "success", 1.0, "task completed", None)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error("cad_task_failure", task_id=task_id, exception=str(exc))
        update_task_status(task_id, "failure", None, None, str(exc))

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        logger.warning("cad_task_retry", task_id=task_id, exception=str(exc))
        update_task_status(task_id, "running", None, f"retrying: {exc}", None)


def update_progress(task_id: str, progress: float, message: str = None) -> None:
    update_task_status(task_id, "running", progress, message)


def check_celery_health() -> Dict[str, Any]:
    """Return async runtime health information."""

    if is_local_async_mode():
        return {
            "status": "healthy",
            "mode": "local_eager",
            "worker_count": 0,
            "active_tasks": 0,
            "workers": [],
            "message": "running in-process without Redis/Celery worker",
        }

    try:
        inspect = celery_app.control.inspect()
        stats = inspect.stats()
        active = inspect.active()
        if stats and active is not None:
            worker_count = len(stats)
            active_tasks = sum(len(tasks) for tasks in active.values()) if active else 0
            return {
                "status": "healthy",
                "mode": "redis",
                "worker_count": worker_count,
                "active_tasks": active_tasks,
                "workers": list(stats.keys()),
            }
        return {
            "status": "unhealthy",
            "mode": "redis",
            "error": "unable to connect to celery workers",
        }
    except Exception as exc:
        logger.error("celery_health_check_failed", error=str(exc))
        return {
            "status": "unhealthy",
            "mode": "redis",
            "error": str(exc),
        }


if __name__ == "__main__":
    celery_app.start()
