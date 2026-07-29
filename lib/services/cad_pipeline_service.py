from __future__ import annotations

import json
import os
import stat
import shutil
import time
import uuid
import zipfile
from pathlib import Path
from tempfile import mkstemp
from typing import Any

import pandas as pd
from fastapi import UploadFile

from app.config import get_settings
from app.services.cad_text_processor import cad_text_processor
from app.services.alibaba_ai_translation_service import alibaba_ai_translation_service
from app.utils.file_utils import get_safe_filename, resolve_within_directory
from app.workflow.pipeline import CADPipeline, get_pipeline
from app.functions.dwg_converter import DWGConverter
from app.functions.text_extractor import TextExtractor
from app.functions.text_applier import TextApplier


class TaskCancelledError(RuntimeError):
    pass


class CADPipelineService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.processor = cad_text_processor
        self._cancelled_task_ids: set[str] = set()
        # 使用模块化工作流管道处理新任务
        self._pipeline = get_pipeline()

    def _tasks_root(self) -> Path:
        tasks_root = self.settings.get_output_path() / "cad_tasks"
        tasks_root.mkdir(parents=True, exist_ok=True)
        return tasks_root

    def _task_dir(self, task_id: str) -> Path:
        return self._tasks_root() / task_id

    def _task_excel_path(self, task_id: str, metadata: dict[str, Any] | None = None) -> Path:
        metadata = metadata or self._load_task(task_id)
        excel_filename = metadata.get("excel_filename")
        if not excel_filename:
            raise FileNotFoundError(f"Excel is missing for task {task_id}")
        return self._task_dir(task_id) / excel_filename

    def _write_translated_excel(self, task_id: str, translation_map: dict[str, str]) -> Path:
        if not translation_map:
            raise ValueError("No translations were provided for Excel backfill.")

        metadata = self._load_task(task_id)
        excel_path = self._task_excel_path(task_id, metadata)
        if not excel_path.exists():
            raise FileNotFoundError(f"Excel is missing for task {task_id}: {excel_path.name}")

        df = pd.read_excel(excel_path)
        if "原文" not in df.columns:
            raise ValueError(f"Excel for task {task_id} does not contain a 原文 column.")

        if "译文" not in df.columns:
            df["译文"] = ""

        def _translate_cell(value: Any) -> str:
            original = str(value or "").strip()
            if not original:
                return ""
            return translation_map.get(original, "")

        df["译文"] = df["原文"].apply(_translate_cell)
        translated_excel_path = excel_path.with_name(f"translated_{excel_path.name}")
        df.to_excel(translated_excel_path, index=False, engine="openpyxl")
        self._update_task(
            task_id,
            translated_excel_filename=translated_excel_path.name,
            last_activity_at=time.time(),
        )
        return translated_excel_path

    def _task_meta_path(self, task_id: str) -> Path:
        return self._task_dir(task_id) / "task.json"

    def _task_log_path(self, task_id: str) -> Path:
        return self._task_dir(task_id) / "task.log"

    def _task_checkpoint_path(self, task_id: str) -> Path:
        return self._task_dir(task_id) / "translations_checkpoint.json"

    def _append_log(self, task_id: str, message: str) -> None:
        log_path = self._task_log_path(task_id)
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")

    def _save_checkpoint(self, task_id: str, translations: list[dict[str, str]]) -> None:
        checkpoint_path = self._task_checkpoint_path(task_id)
        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(translations, f, ensure_ascii=False, indent=2)

    def _load_checkpoint(self, task_id: str) -> list[dict[str, str]]:
        checkpoint_path = self._task_checkpoint_path(task_id)
        if not checkpoint_path.exists():
            return []
        with open(checkpoint_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _packages_root(self) -> Path:
        packages_root = self._tasks_root() / "_packages"
        packages_root.mkdir(parents=True, exist_ok=True)
        return packages_root

    def _archive_name(self, value: str) -> str:
        cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", ".", " "} else "_" for ch in value).strip()
        return cleaned or "task"

    def _handle_remove_readonly(self, func, path: str, exc_info) -> None:
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except OSError:
            raise exc_info[1]

    def _delete_tree(self, path: Path) -> None:
        last_error: OSError | None = None
        for attempt in range(5):
            try:
                shutil.rmtree(path, onerror=self._handle_remove_readonly)
                return
            except OSError as exc:
                last_error = exc
                time.sleep(0.5 * (attempt + 1))

        raise PermissionError(
            f"Task directory is still in use. Close related CAD/ODA windows and retry: {path}"
        ) from last_error

    def _load_task(self, task_id: str) -> dict[str, Any]:
        metadata_path = self._task_meta_path(task_id)
        if not metadata_path.exists():
            raise FileNotFoundError(f"Task not found: {task_id}")
        return json.loads(metadata_path.read_text(encoding="utf-8"))

    def _save_task(self, task_id: str, payload: dict[str, Any]) -> None:
        metadata_path = self._task_meta_path(task_id)
        metadata_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _update_task(self, task_id: str, **patch: Any) -> dict[str, Any]:
        metadata = self._load_task(task_id)
        metadata.update(patch)
        metadata["last_activity_at"] = time.time()
        self._save_task(task_id, metadata)
        return metadata

    def _build_task_summary(self, metadata: dict[str, Any]) -> dict[str, Any]:
        task_id = metadata["task_id"]
        inferred_status = str(metadata.get("status") or "").strip().lower()
        inferred_stage = str(metadata.get("stage") or "").strip().lower()
        last_error = str(metadata.get("last_error") or "").strip().lower()
        failed_count = int(metadata.get("failed_count") or 0)
        if "cancelled by user" in last_error or "stopped by user" in last_error:
            inferred_status = "cancelled"
            inferred_stage = "cancelled"
        if not inferred_status:
            if metadata.get("translated_cad_filename"):
                inferred_status = "done"
            elif metadata.get("excel_filename"):
                inferred_status = "processing"
            else:
                inferred_status = "queued"
        # Infer partial status from failed_count if not already set
        if failed_count > 0 and inferred_status == "done" and inferred_stage == "completed":
            inferred_status = "partial"
        if not inferred_stage:
            if inferred_status == "done":
                inferred_stage = "completed"
            elif inferred_status == "partial":
                inferred_stage = "completed"
            elif inferred_status == "processing":
                inferred_stage = "translating"
            elif inferred_status == "cancelled":
                inferred_stage = "cancelled"
            elif inferred_status == "error":
                inferred_stage = "failed"
            else:
                inferred_stage = "queued"
        return {
            "task_id": task_id,
            "original_filename": metadata["original_filename"],
            "target_language": metadata.get("target_language", "en"),
            "extract_only": metadata.get("extract_only", False),
            "status": inferred_status,
            "stage": inferred_stage,
            "processing_time": metadata.get("processing_time", "0.0s"),
            "text_count": metadata.get("text_count", 0),
            "translatable_count": metadata.get("translatable_count", metadata.get("translation_count", 0)),
            "translation_count": metadata.get("translation_count", 0),
            "translated_count": metadata.get("translated_count", metadata.get("translation_count", 0)),
            "failed_count": failed_count,
            "total_chunks": metadata.get("total_chunks", 0),
            "completed_chunks": metadata.get("completed_chunks", 0),
            "current_chunk": metadata.get("current_chunk", 0),
            "provider": metadata.get("provider", ""),
            "model": metadata.get("model", ""),
            "batch_size": metadata.get("batch_size", 0),
            "retry_count": metadata.get("retry_count", 0),
            "last_error": metadata.get("last_error", ""),
            "last_activity_at": metadata.get("last_activity_at"),
            "created_at": metadata.get("created_at"),
            "files": {
                "excel_file": f"/api/cad/download/{task_id}/excel" if metadata.get("excel_filename") else None,
                "translated_cad_file": (
                    f"/api/cad/download/{task_id}/translated_cad"
                    if metadata.get("translated_cad_filename")
                    else None
                ),
                "log_file": f"/api/cad/download/{task_id}/log",
            },
        }

    def _map_backend(self, backend: str | None) -> str:
        normalized = (backend or "").strip().lower()
        mapping = {
            "": "auto",
            "auto": "auto",
            "haochen_com": "haochen_com",
            "gstar_com": "haochen_com",
            "autocad_com": "autocad_com",
            "oda_cli": "oda",
            "oda": "oda",
            "com": "com",
            "dxf_native": "dxf_only",
        }
        if normalized in mapping:
            return mapping[normalized]
        return normalized

    def extract_upload(
        self,
        uploaded_file: UploadFile,
        target_language: str = "en",
        converter_backend: str | None = None,
    ) -> dict[str, Any]:
        if not uploaded_file.filename:
            raise ValueError("File name is required.")

        started_at = time.perf_counter()
        suffix = Path(uploaded_file.filename).suffix.lower()
        if suffix not in {".dwg", ".dxf"}:
            raise ValueError("Only DWG and DXF files are supported.")

        task_id = uuid.uuid4().hex[:8]
        task_dir = self._task_dir(task_id)
        task_dir.mkdir(parents=True, exist_ok=True)

        safe_filename = get_safe_filename(uploaded_file.filename)
        input_path = task_dir / safe_filename
        with input_path.open("wb") as buffer:
            shutil.copyfileobj(uploaded_file.file, buffer)

        resolved_backend = self._map_backend(converter_backend)
        normalized_dxf_path = input_path
        if suffix == ".dwg":
            if resolved_backend == "dxf_only":
                raise ValueError("DWG upload requires a converter backend.")
            normalized_dxf_path = Path(
                self.processor._convert_dwg_to_dxf(
                    str(input_path),
                    task_dir,
                    backend_override=resolved_backend,
                )
            )

        extract_result = self.processor.extract_texts_to_excel(
            dxf_file_path=str(normalized_dxf_path),
            output_dir=str(task_dir),
        )

        texts = []
        for index, text_info in enumerate(extract_result.get("texts", [])):
            texts.append(
                {
                    "id": f"{task_id}_{index}",
                    "original_text": text_info.get("原文", ""),
                    "translated_text": "",
                    "entity_type": text_info.get("实体类型", ""),
                    "layer": text_info.get("图层", ""),
                    "position": f"({text_info.get('X坐标', 0)}, {text_info.get('Y坐标', 0)})",
                }
            )

        excel_filename = None
        if extract_result.get("output_file"):
            excel_filename = Path(str(extract_result["output_file"])).name

        translatable_count = alibaba_ai_translation_service.count_translatable_texts(
            [t.get("original_text", "") for t in texts]
        )
        metadata = {
            "task_id": task_id,
            "original_filename": safe_filename,
            "normalized_dxf_filename": normalized_dxf_path.name,
            "target_language": target_language,
            "requested_backend": converter_backend or "",
            "resolved_backend": resolved_backend,
            "extract_only": False,
            "status": "processing",
            "stage": "extracting",
            "text_count": len(texts),
            "translatable_count": translatable_count,
            "translation_count": 0,
            "translated_count": 0,
            "excel_filename": excel_filename,
            "translated_cad_filename": None,
            "total_chunks": 0,
            "completed_chunks": 0,
            "current_chunk": 0,
            "provider": "",
            "model": "",
            "batch_size": 0,
            "retry_count": 0,
            "last_error": "",
            "created_at": time.time(),
            "last_activity_at": time.time(),
            "processing_time": f"{time.perf_counter() - started_at:.1f}s",
        }
        self._save_task(task_id, metadata)

        return {
            "task_id": task_id,
            "text_count": len(texts),
            "translatable_count": translatable_count,
            "excel_file_url": f"/api/cad/download/{task_id}/excel" if excel_filename else None,
            "texts": texts,
        }

    def _run_translation_with_logging(
        self,
        task_id: str,
        original_texts: list[str],
        target_language: str,
        runtime_summary: dict[str, Any],
        batch_size: int,
        total_chunks: int,
        ensure_not_cancelled: Callable[[], None],
    ) -> list[dict[str, str]]:
        """Run translation with progress logging and checkpoint saving."""
        self._append_log(task_id, f"开始翻译: {len(original_texts)} 条文本, 批次大小={batch_size}, 并发数={runtime_summary.get('parallel_count', 1)}")

        # Accumulate translations for real-time checkpoint saving
        checkpoint_translations: list[dict[str, str]] = []

        def on_translation_progress(progress: dict[str, Any]) -> None:
            if not task_id:
                return
            ensure_not_cancelled()
            event = progress.get("event", "")
            chunk_index = progress.get("chunk_index", 0)
            completed = progress.get("completed_chunks", 0)
            total = progress.get("total_chunks", 0)
            translated = progress.get("translated_count", 0)
            parallel = progress.get("parallel_count", 1)
            last_error = str(progress.get("last_error") or "").strip()

            if event == "started":
                self._append_log(task_id, f"翻译启动: 共 {total} 个批次, 并发={parallel}")
            elif event == "chunk_started":
                self._append_log(task_id, f"批次 {chunk_index}/{total} 开始...")
            elif event == "chunk_completed":
                log_msg = f"批次 {chunk_index}/{total} 完成 (已翻译 {translated}/{len(original_texts)} 条)"
                if last_error:
                    log_msg += f" [回退: {last_error[:60]}]"
                self._append_log(task_id, log_msg)
                # Real-time checkpoint: save each chunk's translations immediately
                chunk_translations = progress.get("chunk_translations") or {}
                if chunk_translations:
                    for original, translated in chunk_translations.items():
                        if translated and translated.startswith("[translation_error]"):
                            # Preserve failed entries with empty translated so resume can retry them
                            checkpoint_translations.append({"original": original, "translated": ""})
                        elif translated and translated.strip():
                            checkpoint_translations.append({"original": original, "translated": translated})
                        else:
                            # Empty translation - also mark as pending
                            checkpoint_translations.append({"original": original, "translated": ""})
                    # Deduplicate by original text (keep last)
                    seen: dict[str, dict[str, str]] = {}
                    for item in checkpoint_translations:
                        seen[item["original"]] = item
                    checkpoint_translations.clear()
                    checkpoint_translations.extend(seen.values())
                    self._save_checkpoint(task_id, checkpoint_translations)
            elif event == "completed":
                self._append_log(task_id, f"翻译完成: 共翻译 {translated} 条文本")
                # Final checkpoint save
                if checkpoint_translations:
                    self._save_checkpoint(task_id, checkpoint_translations)

            patch: dict[str, Any] = {
                "status": "processing",
                "stage": "translating",
                "provider": progress.get("provider", runtime_summary.get("provider", "")),
                "model": progress.get("model", runtime_summary.get("model", "")),
                "batch_size": int(progress.get("batch_size") or batch_size),
                "retry_count": int(progress.get("retry_count") or runtime_summary.get("retry_count") or 0),
                "total_chunks": int(progress.get("total_chunks") or total_chunks),
                "completed_chunks": completed,
                "current_chunk": int(progress.get("chunk_index") or 0),
                "translated_count": translated,
            }
            if last_error:
                patch["last_error"] = last_error
            self._update_task(task_id, **patch)

        translated_texts = alibaba_ai_translation_service.translate_batch(
            texts=original_texts,
            target_lang=target_language,
            progress_callback=on_translation_progress,
            should_cancel=lambda: bool(task_id and task_id in self._cancelled_task_ids),
        )
        ensure_not_cancelled()
        translations: list[dict[str, str]] = []
        failed_count = 0
        for original, translated in zip(original_texts, translated_texts):
            if not original or not original.strip():
                continue
            if translated and translated.startswith("[translation_error]"):
                translations.append({"original": original, "translated": ""})
                failed_count += 1
            elif translated and translated.strip():
                translations.append({"original": original, "translated": translated})
            else:
                translations.append({"original": original, "translated": ""})
                failed_count += 1
        # Deduplicate by original text (keep last)
        seen: dict[str, dict[str, str]] = {}
        for item in translations:
            seen[item["original"]] = item
        translations = list(seen.values())
        # Final save (in case some translations were not captured via callback)
        self._save_checkpoint(task_id, translations)
        successful = len([t for t in translations if t.get("translated")])
        self._append_log(task_id, f"翻译结果已保存: {successful} 条成功, {failed_count} 条失败")
        return translations

    def process_upload(
        self,
        uploaded_file: UploadFile,
        target_language: str = "en",
        converter_backend: str | None = None,
        extract_only: bool = False,
        translation_mode: str = "replace",
        font_name: str | None = None,
        font_size_reduction: int = 2,
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        task_id: str | None = None
        try:
            def ensure_not_cancelled() -> None:
                if task_id and task_id in self._cancelled_task_ids:
                    raise TaskCancelledError("Task cancelled by user.")

            extract_result = self.extract_upload(
                uploaded_file=uploaded_file,
                target_language=target_language,
                converter_backend=converter_backend,
            )
            task_id = extract_result["task_id"]
            self._append_log(task_id, f"任务创建: {extract_result.get('text_count', 0)} 条文本已提取")
            ensure_not_cancelled()
            self._update_task(
                task_id,
                extract_only=extract_only,
                status="processing",
                stage="extracted",
                last_error="",
                processing_time=f"{time.perf_counter() - started_at:.1f}s",
            )

            if extract_only:
                self._update_task(
                    task_id,
                    status="done",
                    stage="completed",
                    processing_time=f"{time.perf_counter() - started_at:.1f}s",
                )
                self._append_log(task_id, "仅提取模式，任务完成")
                return {
                    **extract_result,
                    "translation_count": 0,
                    "translated_cad_file": None,
                }

            texts = extract_result.get("texts", [])
            original_texts = [
                (entry.get("original_text") or "").strip()
                for entry in texts
                if (entry.get("original_text") or "").strip()
            ]
            if not original_texts:
                self._update_task(
                    task_id,
                    status="done",
                    stage="completed",
                    processing_time=f"{time.perf_counter() - started_at:.1f}s",
                )
                self._append_log(task_id, "无有效文本，任务完成")
                return {
                    **extract_result,
                    "translation_count": 0,
                    "translated_cad_file": None,
                }

            runtime_summary = alibaba_ai_translation_service.get_runtime_summary()
            batch_size = max(1, int(runtime_summary.get("batch_size") or 1))
            translatable_count = alibaba_ai_translation_service.count_translatable_texts(original_texts)
            total_chunks = (translatable_count + batch_size - 1) // batch_size if translatable_count else 0
            self._update_task(
                task_id,
                status="processing",
                stage="translating",
                provider=runtime_summary.get("provider", ""),
                model=runtime_summary.get("model", ""),
                batch_size=batch_size,
                retry_count=int(runtime_summary.get("retry_count") or 0),
                total_chunks=total_chunks,
                completed_chunks=0,
                current_chunk=0,
                translated_count=0,
                last_error="",
            )

            translations = self._run_translation_with_logging(
                task_id=task_id,
                original_texts=original_texts,
                target_language=target_language,
                runtime_summary=runtime_summary,
                batch_size=batch_size,
                total_chunks=total_chunks,
                ensure_not_cancelled=ensure_not_cancelled,
            )

            successful_count = len([t for t in translations if t.get("translated")])
            failed_count = len([t for t in translations if not t.get("translated")])
            has_failures = failed_count > 0

            self._update_task(
                task_id,
                status="processing",
                stage="applying",
                completed_chunks=total_chunks,
                current_chunk=total_chunks,
                translated_count=successful_count,
                translation_count=successful_count,
                failed_count=failed_count,
                processing_time=f"{time.perf_counter() - started_at:.1f}s",
            )
            self._append_log(task_id, f"开始回写翻译: {successful_count} 条成功, {failed_count} 条失败")
            apply_result = self.apply_translation(
                task_id=extract_result["task_id"],
                translations=translations,
                translation_mode=translation_mode,
                font_name=font_name,
                font_size_reduction=font_size_reduction,
            )
            ensure_not_cancelled()
            final_status = "partial" if has_failures else "done"
            self._update_task(
                task_id,
                status=final_status,
                stage="completed",
                completed_chunks=total_chunks,
                current_chunk=total_chunks,
                translated_count=apply_result["translation_count"],
                translation_count=apply_result["translation_count"],
                failed_count=failed_count,
                translated_cad_filename=self._load_task(task_id).get("translated_cad_filename"),
                processing_time=f"{time.perf_counter() - started_at:.1f}s",
            )
            if has_failures:
                self._append_log(task_id, f"任务部分完成: {successful_count} 条成功, {failed_count} 条失败，可点击「继续翻译」重试")
            else:
                self._append_log(task_id, f"任务完成: 翻译 {apply_result['translation_count']} 条")
            return {
                **extract_result,
                "translation_count": apply_result["translation_count"],
                "failed_count": failed_count,
                "translated_cad_file": apply_result["translated_cad_file"],
                "status": final_status,
            }
        except TaskCancelledError as exc:
            if task_id:
                self._update_task(
                    task_id,
                    status="cancelled",
                    stage="cancelled",
                    last_error=str(exc),
                    processing_time=f"{time.perf_counter() - started_at:.1f}s",
                )
                self._append_log(task_id, f"任务已取消: {exc}")
                self._cancelled_task_ids.discard(task_id)
            raise
        except Exception as exc:
            cancelled = "cancelled by user" in str(exc).lower() or "stopped by user" in str(exc).lower()
            if task_id:
                self._update_task(
                    task_id,
                    status="cancelled" if cancelled else "error",
                    stage="cancelled" if cancelled else "failed",
                    last_error=str(exc),
                    processing_time=f"{time.perf_counter() - started_at:.1f}s",
                )
                self._append_log(task_id, f"任务失败: {exc}")
            raise
        finally:
            if task_id:
                self._cancelled_task_ids.discard(task_id)

    def resume_task(
        self,
        task_id: str,
        target_language: str = "en",
        translation_mode: str = "replace",
        font_name: str | None = None,
        font_size_reduction: int = 2,
    ) -> dict[str, Any]:
        """Resume an interrupted or failed task from its last checkpoint."""
        started_at = time.perf_counter()
        metadata = self._load_task(task_id)
        task_dir = self._task_dir(task_id)

        text_count = metadata.get("text_count", 0)
        translated_count = metadata.get("translated_count", 0)
        is_done = metadata.get("status") == "done" and metadata.get("stage") == "completed"
        has_untranslated = translated_count < text_count
        if is_done and not has_untranslated:
            raise ValueError("Task is already completed. Use 'Restart' instead.")

        self._append_log(task_id, "=" * 40)
        self._append_log(task_id, f"任务恢复: stage={metadata.get('stage')}, status={metadata.get('status')}")

        def ensure_not_cancelled() -> None:
            if task_id in self._cancelled_task_ids:
                raise TaskCancelledError("Task cancelled by user.")

        # Stage 1: If extraction was not done, we can't resume (need original file re-upload)
        stage = metadata.get("stage", "")
        if stage in ("", "queued") or not metadata.get("excel_filename"):
            raise ValueError("Task has not been extracted yet. Please restart with the original file.")

        # Load existing translations checkpoint if available
        checkpoint = self._load_checkpoint(task_id)
        translations = checkpoint[:]

        try:
            # If we have a translated CAD file already, task is effectively done
            if metadata.get("translated_cad_filename"):
                self._update_task(
                    task_id,
                    status="done",
                    stage="completed",
                    last_error="",
                    processing_time=f"{time.perf_counter() - started_at:.1f}s",
                )
                self._append_log(task_id, "任务已包含翻译结果，标记为完成")
                return {
                    "task_id": task_id,
                    "translation_count": len(translations),
                    "translated_cad_file": f"/api/cad/download/{task_id}/translated_cad",
                }

            # If we are before applying stage, ensure we have translations
            if stage in ("extracted", "extracting", "translating", "failed") or not translations:
                # Need to re-translate if no checkpoint
                if not translations:
                    self._append_log(task_id, "未找到翻译断点，重新执行翻译")
                    # Re-read original texts from excel
                    excel_path = self._task_excel_path(task_id, metadata)
                    df = pd.read_excel(excel_path)
                    original_texts = []
                    if "原文" in df.columns:
                        original_texts = [str(v).strip() for v in df["原文"].fillna("").astype(str).tolist() if str(v).strip()]
                    elif len(df.columns) > 0:
                        original_texts = [str(v).strip() for v in df.iloc[:, 0].fillna("").astype(str).tolist() if str(v).strip()]

                    if not original_texts:
                        self._update_task(
                            task_id,
                            status="done",
                            stage="completed",
                            processing_time=f"{time.perf_counter() - started_at:.1f}s",
                        )
                        self._append_log(task_id, "Excel 中无有效文本，任务完成")
                        return {
                            "task_id": task_id,
                            "translation_count": 0,
                            "translated_cad_file": None,
                        }

                    runtime_summary = alibaba_ai_translation_service.get_runtime_summary()
                    batch_size = max(1, int(runtime_summary.get("batch_size") or 1))
                    translatable_count = alibaba_ai_translation_service.count_translatable_texts(original_texts)
                    total_chunks = (translatable_count + batch_size - 1) // batch_size if translatable_count else 0

                    self._update_task(
                        task_id,
                        status="processing",
                        stage="translating",
                        provider=runtime_summary.get("provider", ""),
                        model=runtime_summary.get("model", ""),
                        batch_size=batch_size,
                        retry_count=int(runtime_summary.get("retry_count") or 0),
                        total_chunks=total_chunks,
                        completed_chunks=0,
                        current_chunk=0,
                        translated_count=0,
                        last_error="",
                    )

                    translations = self._run_translation_with_logging(
                        task_id=task_id,
                        original_texts=original_texts,
                        target_language=target_language,
                        runtime_summary=runtime_summary,
                        batch_size=batch_size,
                        total_chunks=total_chunks,
                        ensure_not_cancelled=ensure_not_cancelled,
                    )
                else:
                    successful = [t for t in translations if t.get("translated")]
                    failed = [t for t in translations if not t.get("translated")]
                    if failed:
                        self._append_log(task_id, f"从断点恢复: {len(successful)} 条已翻译, {len(failed)} 条待重新翻译")
                        failed_texts = [t["original"] for t in failed]
                        runtime_summary = alibaba_ai_translation_service.get_runtime_summary()
                        batch_size = max(1, int(runtime_summary.get("batch_size") or 1))
                        translatable_count = alibaba_ai_translation_service.count_translatable_texts(failed_texts)
                        total_chunks = (translatable_count + batch_size - 1) // batch_size if translatable_count else 0
                        self._update_task(
                            task_id,
                            status="processing",
                            stage="translating",
                            provider=runtime_summary.get("provider", ""),
                            model=runtime_summary.get("model", ""),
                            batch_size=batch_size,
                            retry_count=int(runtime_summary.get("retry_count") or 0),
                            total_chunks=total_chunks,
                            completed_chunks=0,
                            current_chunk=0,
                            translated_count=0,
                            last_error="",
                        )
                        new_translations = self._run_translation_with_logging(
                            task_id=task_id,
                            original_texts=failed_texts,
                            target_language=target_language,
                            runtime_summary=runtime_summary,
                            batch_size=batch_size,
                            total_chunks=total_chunks,
                            ensure_not_cancelled=ensure_not_cancelled,
                        )
                        # Merge new translations into checkpoint, keeping successful ones
                        new_map = {t["original"]: t["translated"] for t in new_translations}
                        merged: list[dict[str, str]] = []
                        for t in successful:
                            merged.append(t)
                        for t in failed:
                            updated = new_map.get(t["original"], "")
                            merged.append({"original": t["original"], "translated": updated})
                        translations = merged
                        self._save_checkpoint(task_id, translations)
                    else:
                        self._append_log(task_id, f"从断点恢复: {len(translations)} 条已翻译")
                    self._update_task(
                        task_id,
                        status="processing",
                        stage="applying",
                        last_error="",
                    )

            # Stage: apply translation
            self._append_log(task_id, f"开始回写翻译: {len(translations)} 条")
            apply_result = self.apply_translation(
                task_id=task_id,
                translations=translations,
                translation_mode=translation_mode,
                font_name=font_name,
                font_size_reduction=font_size_reduction,
            )
            ensure_not_cancelled()
            failed_count = len([t for t in translations if not t.get("translated")])
            final_status = "partial" if failed_count > 0 else "done"
            self._update_task(
                task_id,
                status=final_status,
                stage="completed",
                completed_chunks=metadata.get("total_chunks", 0),
                current_chunk=metadata.get("total_chunks", 0),
                translated_count=apply_result["translation_count"],
                translation_count=apply_result["translation_count"],
                failed_count=failed_count,
                translated_cad_filename=self._load_task(task_id).get("translated_cad_filename"),
                processing_time=f"{time.perf_counter() - started_at:.1f}s",
                last_error="",
            )
            if failed_count > 0:
                self._append_log(task_id, f"任务恢复部分完成: {apply_result['translation_count']} 条成功, {failed_count} 条失败，可点击「继续翻译」重试")
            else:
                self._append_log(task_id, f"任务恢复完成: 翻译 {apply_result['translation_count']} 条")
            return {
                "task_id": task_id,
                "translation_count": apply_result["translation_count"],
                "failed_count": failed_count,
                "translated_cad_file": apply_result["translated_cad_file"],
                "status": final_status,
            }

        except TaskCancelledError as exc:
            self._update_task(
                task_id,
                status="cancelled",
                stage="cancelled",
                last_error=str(exc),
                processing_time=f"{time.perf_counter() - started_at:.1f}s",
            )
            self._append_log(task_id, f"恢复任务已取消: {exc}")
            self._cancelled_task_ids.discard(task_id)
            raise
        except Exception as exc:
            cancelled = "cancelled by user" in str(exc).lower() or "stopped by user" in str(exc).lower()
            self._update_task(
                task_id,
                status="cancelled" if cancelled else "error",
                stage="cancelled" if cancelled else "failed",
                last_error=str(exc),
                processing_time=f"{time.perf_counter() - started_at:.1f}s",
            )
            self._append_log(task_id, f"恢复任务失败: {exc}")
            raise
        finally:
            self._cancelled_task_ids.discard(task_id)

    def get_task_logs(self, task_id: str) -> str:
        log_path = self._task_log_path(task_id)
        if log_path.exists():
            return log_path.read_text(encoding="utf-8")
        # Fallback: return task metadata as pseudo-log for old tasks
        meta_path = self._task_meta_path(task_id)
        if meta_path.exists():
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            lines = [f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(metadata.get('created_at', 0)))}] 任务创建"]
            lines.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(metadata.get('last_activity_at', 0)))}] 最后活动: stage={metadata.get('stage')}, status={metadata.get('status')}")
            if metadata.get("last_error"):
                lines.append(f"错误: {metadata['last_error']}")
            return "\n".join(lines)
        raise FileNotFoundError(f"Task not found: {task_id}")

    def apply_translation(
        self,
        task_id: str,
        translations: list[dict[str, str]],
        translation_mode: str = "replace",
        font_name: str | None = None,
        font_size_reduction: int = 2,
    ) -> dict[str, Any]:
        """
        将用户提供的翻译应用到 DXF 文件。

        Args:
            task_id:             任务 ID
            translations:        [{"original": ..., "translated": ...}] 列表
            translation_mode:    "replace" 替换原文 | "add" 在下方追加翻译（默认 "replace"）
            font_name:           输出字体名称（默认使用配置中的 DEFAULT_FONT_NAME）
            font_size_reduction: 字号缩小量（默认 2）
        """
        metadata = self._load_task(task_id)
        task_dir = self._task_dir(task_id)
        normalized_dxf_path = task_dir / metadata["normalized_dxf_filename"]
        if not normalized_dxf_path.exists():
            raise FileNotFoundError(f"Normalized DXF is missing for task {task_id}")

        translation_map: dict[str, str] = {}
        for item in translations:
            original = (item.get("original") or "").strip()
            translated = (item.get("translated") or "").strip()
            if original and translated:
                translation_map[original] = translated

        if not translation_map:
            raise ValueError("No non-empty translations were provided.")

        resolved_font = font_name or self.settings.DEFAULT_FONT_NAME
        translated_filename = f"translated_{normalized_dxf_path.name}"
        translated_output = task_dir / translated_filename

        # 使用新的 TextApplier 功能模块（通过 pipeline 调用）
        self._pipeline.run_apply_only(
            dxf_file=str(normalized_dxf_path),
            task_dir=str(task_dir),
            translation_map=translation_map,
            translation_mode=translation_mode,
            font_name=resolved_font,
            font_size_reduction=font_size_reduction,
        )
        translated_excel_path = self._write_translated_excel(task_id, translation_map)

        metadata["translation_count"] = len(translation_map)
        metadata["translated_count"] = len(translation_map)
        metadata["translated_cad_filename"] = translated_filename
        metadata["translated_excel_filename"] = translated_excel_path.name
        metadata["translation_mode"] = translation_mode
        metadata["font_name"] = resolved_font
        metadata["font_size_reduction"] = font_size_reduction
        self._save_task(task_id, metadata)

        return {
            "task_id": task_id,
            "translation_count": len(translation_map),
            "translation_mode": translation_mode,
            "font_name": resolved_font,
            "font_size_reduction": font_size_reduction,
            "translated_cad_file": f"/api/cad/download/{task_id}/translated_cad",
        }

    def list_tasks(self) -> list[dict[str, Any]]:
        tasks: list[dict[str, Any]] = []
        for metadata_path in self._tasks_root().glob("*/task.json"):
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            tasks.append(self._build_task_summary(metadata))
        status_rank = {"processing": 0, "error": 1, "queued": 2, "cancelled": 3, "done": 4}
        tasks.sort(
            key=lambda item: (
                status_rank.get(str(item.get("status") or "queued").lower(), 9),
                -(item.get("last_activity_at") or item.get("created_at") or 0),
            )
        )
        return tasks

    def clear_all_tasks(self) -> None:
        """Clear all tasks by removing the root tasks directory."""
        tasks_root = self._tasks_root()
        self._cancelled_task_ids.clear()
        if tasks_root.exists():
            self._delete_tree(tasks_root)
        # Recreate the root directory to ensure it exists for future tasks
        tasks_root.mkdir(parents=True, exist_ok=True)

    def delete_task(self, task_id: str) -> None:
        task_dir = self._task_dir(task_id)
        if not task_dir.exists():
            raise FileNotFoundError(f"Task not found: {task_id}")
        self._cancelled_task_ids.discard(task_id)
        self._delete_tree(task_dir)

    def stop_all_tasks(self) -> dict[str, Any]:
        cancelled_task_ids: list[str] = []
        for metadata_path in self._tasks_root().glob("*/task.json"):
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            task_id = str(metadata.get("task_id") or "").strip()
            status = str(metadata.get("status") or "").strip().lower()
            if not task_id or status not in {"processing", "queued"}:
                continue
            self._cancelled_task_ids.add(task_id)
            metadata["status"] = "cancelled"
            metadata["stage"] = "cancelled"
            metadata["last_error"] = "Task cancelled by user."
            metadata["last_activity_at"] = time.time()
            self._save_task(task_id, metadata)
            cancelled_task_ids.append(task_id)
        return {
            "cancelled_task_ids": cancelled_task_ids,
            "cancelled_count": len(cancelled_task_ids),
        }

    def resolve_download(self, task_id: str, file_type: str) -> tuple[Path, str]:
        metadata = self._load_task(task_id)
        task_dir = self._task_dir(task_id)

        if file_type == "excel":
            filename = metadata.get("translated_excel_filename") or metadata.get("excel_filename")
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        elif file_type in {"cad", "translated_cad"}:
            filename = metadata.get("translated_cad_filename")
            media_type = "application/octet-stream"
        elif file_type == "log":
            # Prefer real task.log if exists, fallback to task.json for old tasks
            log_path = task_dir / "task.log"
            if log_path.exists():
                filename = "task.log"
                media_type = "text/plain; charset=utf-8"
            else:
                filename = "task.json"
                media_type = "application/json"
        else:
            raise ValueError(f"Unsupported file type: {file_type}")

        if not filename:
            raise FileNotFoundError(f"{file_type} is not available for task {task_id}")

        file_path = resolve_within_directory(task_dir, filename)
        if not file_path.exists():
            raise FileNotFoundError(f"Missing artifact for task {task_id}: {filename}")
        return file_path, media_type

    def build_download_package(self, task_ids: list[str]) -> tuple[Path, str]:
        normalized_ids: list[str] = []
        seen: set[str] = set()
        for task_id in task_ids:
            cleaned = str(task_id or "").strip()
            if cleaned and cleaned not in seen:
                normalized_ids.append(cleaned)
                seen.add(cleaned)

        if not normalized_ids:
            raise ValueError("No task IDs were provided for packaging.")

        files_to_add: list[tuple[Path, str]] = []
        for task_id in normalized_ids:
            metadata = self._load_task(task_id)
            task_dir = self._task_dir(task_id)
            folder_name = self._archive_name(
                f"{Path(get_safe_filename(metadata.get('original_filename') or task_id)).stem}_{task_id}"
            )

            excel_filename = metadata.get("translated_excel_filename") or metadata.get("excel_filename")
            if excel_filename:
                excel_path = task_dir / excel_filename
                if excel_path.exists():
                    files_to_add.append((excel_path, f"{folder_name}/excel/{excel_path.name}"))

            translated_cad_filename = metadata.get("translated_cad_filename")
            if translated_cad_filename:
                cad_path = task_dir / translated_cad_filename
                if cad_path.exists():
                    files_to_add.append((cad_path, f"{folder_name}/cad/{cad_path.name}"))

        if not files_to_add:
            raise FileNotFoundError("No downloadable CAD task outputs were found for the selected tasks.")

        fd, temp_path = mkstemp(
            prefix="cad-package-",
            suffix=".zip",
            dir=str(self._packages_root()),
        )
        os.close(fd)
        zip_path = Path(temp_path)

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for source_path, archive_name in files_to_add:
                archive.write(source_path, archive_name)

        return zip_path, "application/zip"


cad_pipeline_service = CADPipelineService()
