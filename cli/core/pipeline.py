from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pandas as pd

from cli.core.tasks import task_dir
from cli.utils.backend_bridge import (
    get_dwg_converter,
    get_llm_excel_processor,
    get_llm_translation_service,
    get_runtime_config_service,
    get_settings,
    get_text_applier,
    get_text_extractor,
    get_translator,
)


def build_context(
    project_data: dict[str, Any] | None,
    input_file: str,
    output_dir: str | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    project_data = project_data or {}
    settings = get_settings()
    cad_defaults = get_runtime_config_service().get_cad_defaults_summary()
    context = {
        "input_file": input_file,
        "output_dir": output_dir or project_data.get("default_output_dir") or cad_defaults.get("default_output_dir") or str(settings.get_output_path()),
        "target_language": project_data.get("target_language", cad_defaults.get("target_language", settings.DEFAULT_TARGET_LANGUAGE)),
        "converter_backend": project_data.get("converter_backend", cad_defaults.get("converter_backend", settings.DWG_CONVERTER_BACKEND)),
        "font_name": project_data.get("font_name", cad_defaults.get("font_name", settings.DEFAULT_FONT_NAME)),
        "font_size_reduction": project_data.get(
            "font_size_reduction", cad_defaults.get("font_size_reduction", settings.DEFAULT_FONT_SIZE_REDUCTION)
        ),
        "translation_mode": project_data.get("translation_mode", cad_defaults.get("translation_mode", settings.DEFAULT_TRANSLATION_MODE)),
    }
    context.update(overrides)
    return context


def _new_task_dir(prefix: str = "cad_cli") -> tuple[str, Path]:
    task_id = uuid.uuid4().hex[:8]
    directory = task_dir(task_id)
    directory.mkdir(parents=True, exist_ok=True)
    return task_id, directory


def run_extract(input_file: str, output_dir: str | None = None) -> dict[str, Any]:
    input_path = Path(input_file)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    if input_path.suffix.lower() != ".dxf":
        raise ValueError("run_extract currently supports DXF input only.")

    task_id, task_directory = _new_task_dir()
    if output_dir:
        task_directory = Path(output_dir)
        task_directory.mkdir(parents=True, exist_ok=True)

    result = get_text_extractor().extract_to_excel(str(input_path), str(task_directory))
    excel_file = result.get("output_file")
    metadata = {
        "task_id": task_id,
        "original_filename": input_path.name,
        "normalized_dxf_filename": input_path.name,
        "text_count": result.get("texts_count", 0),
        "translation_count": 0,
        "excel_filename": Path(excel_file).name if excel_file else None,
        "translated_cad_filename": None,
    }
    (task_directory / "task.json").write_text(__import__("json").dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "success": True,
        "task_id": task_id,
        "task_dir": str(task_directory),
        "input_file": str(input_path),
        "excel_file": excel_file,
        "text_count": result.get("texts_count", 0),
        "texts": result.get("texts", []),
    }


def run_convert(
    input_file: str,
    output_dir: str | None = None,
    backend_override: str | None = None,
) -> dict[str, Any]:
    input_path = Path(input_file)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    if input_path.suffix.lower() != ".dwg":
        raise ValueError("run_convert currently supports DWG input only.")

    task_id, task_directory = _new_task_dir()
    if output_dir:
        task_directory = Path(output_dir)
        task_directory.mkdir(parents=True, exist_ok=True)

    output_file = get_dwg_converter().convert(
        str(input_path),
        task_directory,
        backend_override=backend_override,
    )
    metadata = {
        "task_id": task_id,
        "original_filename": input_path.name,
        "normalized_dxf_filename": Path(output_file).name,
        "text_count": 0,
        "translation_count": 0,
        "excel_filename": None,
        "translated_cad_filename": None,
    }
    (task_directory / "task.json").write_text(__import__("json").dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "success": True,
        "task_id": task_id,
        "task_dir": str(task_directory),
        "input_file": str(input_path),
        "output_file": str(output_file),
    }


def load_translation_map(excel_file: str) -> dict[str, str]:
    return get_translator().build_translation_map_from_excel(excel_file)


def run_apply(
    input_file: str,
    translation_map: dict[str, str] | None = None,
    excel_file: str | None = None,
    output_dir: str | None = None,
    font_name: str | None = None,
    font_size_reduction: int | None = None,
    translation_mode: str | None = None,
) -> dict[str, Any]:
    input_path = Path(input_file)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    if input_path.suffix.lower() != ".dxf":
        raise ValueError("run_apply currently supports DXF input only.")

    if translation_map is None:
        if not excel_file:
            raise ValueError("Either translation_map or excel_file is required.")
        translation_map = load_translation_map(excel_file)
    if not translation_map:
        raise ValueError("Translation map is empty.")

    task_id, task_directory = _new_task_dir()
    if output_dir:
        task_directory = Path(output_dir)
        task_directory.mkdir(parents=True, exist_ok=True)

    settings = get_settings()
    cad_defaults = get_runtime_config_service().get_cad_defaults_summary()
    output_path = task_directory / f"translated_{input_path.name}"
    resolved_translation_mode = translation_mode or cad_defaults.get("translation_mode") or settings.DEFAULT_TRANSLATION_MODE
    resolved_font_name = font_name or cad_defaults.get("font_name") or settings.DEFAULT_FONT_NAME
    resolved_font_size_reduction = (
        font_size_reduction
        if font_size_reduction is not None
        else cad_defaults.get("font_size_reduction", settings.DEFAULT_FONT_SIZE_REDUCTION)
    )
    result = get_text_applier().apply(
        dxf_file_path=str(input_path),
        output_file_path=str(output_path),
        translation_map=translation_map,
        translation_mode=resolved_translation_mode,
        font_name=resolved_font_name,
        font_size_reduction=resolved_font_size_reduction,
    )
    metadata = {
        "task_id": task_id,
        "original_filename": input_path.name,
        "normalized_dxf_filename": input_path.name,
        "text_count": 0,
        "translation_count": len(translation_map),
        "excel_filename": Path(excel_file).name if excel_file else None,
        "translated_cad_filename": output_path.name,
    }
    (task_directory / "task.json").write_text(__import__("json").dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "success": True,
        "task_id": task_id,
        "task_dir": str(task_directory),
        "input_file": str(input_path),
        "output_file": str(output_path),
        "translated_entities": result.get("translated_entities", 0),
        "translation_count": len(translation_map),
        "translation_mode": resolved_translation_mode,
    }


def run_translate_excel(
    input_file: str,
    output_dir: str | None = None,
    source_language: str = "auto",
    target_language: str | None = None,
    translation_mode: str | None = None,
) -> dict[str, Any]:
    input_path = Path(input_file)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    if input_path.suffix.lower() not in {".xlsx", ".xls"}:
        raise ValueError("run_translate_excel currently supports XLSX/XLS input only.")

    settings = get_settings()
    cad_defaults = get_runtime_config_service().get_cad_defaults_summary()
    resolved_target_language = target_language or cad_defaults.get("target_language") or settings.DEFAULT_TARGET_LANGUAGE
    resolved_translation_mode = translation_mode or cad_defaults.get("translation_mode") or "add"

    task_id, task_directory = _new_task_dir()
    if output_dir:
        task_directory = Path(output_dir)
        task_directory.mkdir(parents=True, exist_ok=True)

    output_path = task_directory / f"{input_path.stem}_translated{input_path.suffix}"
    input_df = pd.read_excel(input_path)
    if {"原文", "译文"}.issubset(set(str(col) for col in input_df.columns)):
        texts = input_df["原文"].fillna("").astype(str).tolist()
        translated = get_llm_translation_service().translate_batch(
            texts,
            source_lang=source_language,
            target_lang=resolved_target_language,
        )
        input_df["译文"] = translated
        input_df.to_excel(output_path, index=False)
        translated_cells = sum(
            1
            for original, target in zip(texts, translated)
            if str(original).strip() and str(target).strip() and not str(target).startswith("[translation_error]")
        )
        stats = {
            "translated_cells": translated_cells,
            "total_rows": len(input_df),
        }
    else:
        stats = get_llm_excel_processor().translate_excel_file(
            input_file_path=str(input_path),
            output_file_path=str(output_path),
            source_lang=source_language,
            target_lang=resolved_target_language,
            translation_mode=resolved_translation_mode,
        )
    metadata = {
        "task_id": task_id,
        "original_filename": input_path.name,
        "normalized_dxf_filename": None,
        "text_count": stats.get("translated_cells", 0),
        "translation_count": stats.get("translated_cells", 0),
        "excel_filename": output_path.name,
        "translated_cad_filename": None,
    }
    (task_directory / "task.json").write_text(__import__("json").dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "success": True,
        "task_id": task_id,
        "task_dir": str(task_directory),
        "input_file": str(input_path),
        "output_file": str(output_path),
        "target_language": resolved_target_language,
        "translation_mode": resolved_translation_mode,
        "translated_cells": stats.get("translated_cells", 0),
    }
