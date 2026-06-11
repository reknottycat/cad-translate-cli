from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from cli.utils.backend_bridge import get_settings


def tasks_root() -> Path:
    root = get_settings().get_output_path() / "cad_tasks"
    root.mkdir(parents=True, exist_ok=True)
    return root


def task_dir(task_id: str) -> Path:
    return tasks_root() / task_id


def task_meta_path(task_id: str) -> Path:
    return task_dir(task_id) / "task.json"


def load_task(task_id: str) -> dict[str, Any]:
    path = task_meta_path(task_id)
    if not path.exists():
        raise FileNotFoundError(f"Task not found: {task_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_task_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": metadata["task_id"],
        "original_filename": metadata["original_filename"],
        "text_count": metadata.get("text_count", 0),
        "translation_count": metadata.get("translation_count", 0),
        "excel_filename": metadata.get("excel_filename"),
        "translated_cad_filename": metadata.get("translated_cad_filename"),
    }


def list_tasks() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in sorted(tasks_root().glob("*/task.json"), reverse=True):
        metadata = json.loads(path.read_text(encoding="utf-8"))
        items.append(summarize_task_metadata(metadata))
    return items


def delete_task(task_id: str) -> None:
    directory = task_dir(task_id)
    if not directory.exists():
        raise FileNotFoundError(f"Task not found: {task_id}")
    shutil.rmtree(directory)


def clear_tasks() -> None:
    root = tasks_root()
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
