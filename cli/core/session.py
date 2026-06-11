from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Session:
    project_path: str | None = None
    project_data: dict[str, Any] | None = None
    translation_map: dict[str, str] = field(default_factory=dict)
    recent_task_id: str | None = None
    active_input_file: str | None = None
    _modified: bool = False

    def mark_modified(self) -> None:
        self._modified = True

    def mark_saved(self) -> None:
        self._modified = False

    def is_modified(self) -> bool:
        return self._modified

    def set_project(self, project_data: dict[str, Any], project_path: str | None = None) -> None:
        self.project_data = project_data
        self.project_path = project_path
        self.mark_saved()

    def get_status(self) -> dict[str, Any]:
        return {
            "project_path": self.project_path,
            "project_name": (self.project_data or {}).get("name"),
            "recent_task_id": self.recent_task_id,
            "active_input_file": self.active_input_file,
            "modified": self._modified,
        }
