from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cli.utils.backend_bridge import get_runtime_config_service


def create_project_data(name: str) -> dict[str, Any]:
    cad_defaults = get_runtime_config_service().get_cad_defaults_summary()
    return {
        "name": name,
        "status": "idle",
        "source_files": [],
        "default_output_dir": cad_defaults.get("default_output_dir", ""),
        "target_language": cad_defaults.get("target_language", "en"),
        "converter_backend": cad_defaults.get("converter_backend", "auto"),
        "font_name": cad_defaults.get("font_name", "Times New Roman"),
        "font_size_reduction": cad_defaults.get("font_size_reduction", 2),
        "translation_mode": cad_defaults.get("translation_mode", "replace"),
        "recent_task_id": None,
        "recent_excel_file": None,
    }


def save_project(data: dict[str, Any], output_path: str | Path) -> dict[str, Any]:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"success": True, "file": str(path), "project": data.get("name")}


def load_project(project_path: str | Path) -> dict[str, Any]:
    path = Path(project_path)
    if not path.exists():
        raise FileNotFoundError(f"Project file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))
