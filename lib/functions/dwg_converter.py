#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DWG to DXF conversion helpers."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from csv import reader as csv_reader
from io import StringIO
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse

import ezdxf
import structlog


logger = structlog.get_logger(__name__)


class DWGConverter:
    """Convert DWG files to DXF using the configured backend."""

    def __init__(
        self,
        converter_backend: str = "dxf_only",
        dwg_auto_backends: str = "haochen_com,autocad_com,oda",
        dwg_disabled_backends: str = "",
        oda_path: str = "",
        oda_output_version: str = "ACAD2018",
        oda_output_format: str = "DXF",
        cad_converter_timeout: int = 120,
        libredwg_dwg2dxf_path: str = "",
        libredwg_install_dir: str = "tools/libredwg/0.13.3-win64",
        libredwg_download_url: str = (
            "https://github.com/LibreDWG/libredwg/releases/download/0.13.3/"
            "libredwg-0.13.3-win64.zip"
        ),
        libredwg_auto_download: bool = True,
    ) -> None:
        self.converter_backend = converter_backend.strip().lower()
        self.dwg_auto_backends = dwg_auto_backends
        self.dwg_disabled_backends = dwg_disabled_backends
        self.oda_path = oda_path
        self.oda_output_version = oda_output_version
        self.oda_output_format = oda_output_format
        self.cad_converter_timeout = cad_converter_timeout
        self.libredwg_dwg2dxf_path = libredwg_dwg2dxf_path
        self.libredwg_install_dir = libredwg_install_dir
        self.libredwg_download_url = libredwg_download_url
        self.libredwg_auto_download = libredwg_auto_download

    def _backend_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def _repo_root(self) -> Path:
        return self._backend_root().parent

    def _resolve_support_path(self, value: str) -> Path:
        """Resolve support files relative to backend/ first, then repo root."""
        path = Path(value)
        if path.is_absolute():
            return path

        backend_candidate = (self._backend_root() / path).resolve()
        if backend_candidate.exists():
            return backend_candidate

        repo_candidate = (self._repo_root() / path).resolve()
        if repo_candidate.exists():
            return repo_candidate

        # Default to backend-relative resolution for clearer error messages.
        return backend_candidate

    def convert(
        self,
        dwg_file_path: str,
        output_dir: Path,
        backend_override: Optional[str] = None,
    ) -> str:
        backend = (backend_override or self.converter_backend).strip().lower()

        if backend == "dxf_only":
            raise ValueError(
                "DWG conversion backend is dxf_only. Upload DXF or configure a real DWG converter backend."
            )

        output_dir.mkdir(parents=True, exist_ok=True)
        output_dxf = output_dir / f"{Path(dwg_file_path).stem}.dxf"

        if backend in {"", "auto"}:
            selected_backends = self._select_auto_backends()
            return self._convert_with_fallback(
                dwg_file_path,
                output_dir,
                str(output_dxf),
                selected_backends,
            )
        if backend == "haochen_com":
            return self._convert_via_haochen_com(dwg_file_path, str(output_dxf))
        if backend == "autocad_com":
            return self._convert_via_autocad_com(dwg_file_path, str(output_dxf))
        if backend == "com":
            return self._convert_with_fallback(
                dwg_file_path,
                output_dir,
                str(output_dxf),
                ["haochen_com", "autocad_com"],
            )
        if backend == "libredwg":
            return self._convert_via_libredwg(dwg_file_path, output_dir, str(output_dxf))
        if backend == "oda":
            return self._convert_via_oda(dwg_file_path, output_dir, str(output_dxf))

        raise ValueError(f"Unsupported DWG conversion backend: {backend}")

    def _service_script_path(self, filename: str) -> Path:
        return self._backend_root() / "app" / "services" / filename

    def _ensure_service_script(self, filename: str) -> Path:
        script_path = self._service_script_path(filename)
        if not script_path.exists():
            raise ValueError(f"Required converter script is missing: {script_path}")
        return script_path

    def _com_attempt_timeout(self) -> int:
        return max(5, min(self.cad_converter_timeout, 20))

    def _subprocess_run_kwargs(self) -> dict[str, object]:
        if os.name != "nt":
            return {}

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        return {
            "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
            "startupinfo": startupinfo,
        }

    def _ascii_safe_stem(self, stem: str, fallback: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
        return cleaned or fallback

    def _prepare_com_paths(
        self,
        dwg_file_path: str,
        output_dxf_path: str,
        backend_slug: str,
    ) -> tuple[Path, Path, Path]:
        final_output = Path(output_dxf_path)
        safe_backend = self._ascii_safe_stem(backend_slug, "com")
        work_dir = final_output.parent / "_com_ascii_tmp" / safe_backend
        work_dir.mkdir(parents=True, exist_ok=True)

        source_path = Path(dwg_file_path)
        input_copy = work_dir / "input.dwg"
        shutil.copy2(source_path, input_copy)

        raw_output = work_dir / "output.dxf"
        raw_output.unlink(missing_ok=True)
        return input_copy, raw_output, final_output

    def _convert_with_fallback(
        self,
        dwg_file_path: str,
        output_dir: Path,
        output_dxf_path: str,
        backends: list[str],
    ) -> str:
        failures: list[str] = []
        for backend in backends:
            try:
                if backend == "haochen_com":
                    return self._convert_via_haochen_com(dwg_file_path, output_dxf_path)
                if backend == "autocad_com":
                    return self._convert_via_autocad_com(dwg_file_path, output_dxf_path)
                if backend == "oda":
                    return self._convert_via_oda(dwg_file_path, output_dir, output_dxf_path)
            except Exception as exc:
                logger.warning("dwg_backend_failed", backend=backend, error=str(exc))
                failures.append(f"{backend}: {exc}")
        raise ValueError("DWG conversion failed. " + " | ".join(failures))

    def _parse_backend_list(self, value: str, default: list[str]) -> list[str]:
        raw = [item.strip().lower() for item in value.split(",")] if value.strip() else default
        normalized: list[str] = []
        for backend in raw:
            if backend and backend not in normalized:
                normalized.append(backend)
        return normalized

    def _configured_auto_backends(self) -> list[str]:
        return self._parse_backend_list(self.dwg_auto_backends, ["haochen_com", "autocad_com", "oda"])

    def _disabled_backends(self) -> set[str]:
        return set(self._parse_backend_list(self.dwg_disabled_backends, []))

    def _backend_prog_ids(self, backend: str) -> list[str]:
        mapping = {
            "haochen_com": [
                "GStarCAD.Application",
                "Gcad.Application",
                "GStarCAD.Application.26",
                "Gcad.Application.26",
                "ZWCAD.Application",
            ],
            "autocad_com": [
                "AutoCAD.Application",
                "AutoCAD.Application.24.1",
                "AutoCAD.Application.24",
                "AutoCAD.Application.23.1",
                "AutoCAD.Application.23",
                "AutoCAD.Application.22",
            ],
        }
        return mapping.get(backend, [])

    def _backend_process_names(self, backend: str) -> set[str]:
        mapping = {
            "haochen_com": {"gcad.exe", "gstarcad.exe", "zwcad.exe"},
            "autocad_com": {"acad.exe"},
        }
        return mapping.get(backend, set())

    def _running_process_names(self) -> set[str]:
        try:
            completed = subprocess.run(
                ["tasklist", "/fo", "csv", "/nh"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                **self._subprocess_run_kwargs(),
            )
        except Exception:
            return set()
        if completed.returncode != 0:
            return set()

        names: set[str] = set()
        for row in csv_reader(StringIO(completed.stdout)):
            if not row:
                continue
            names.add(row[0].strip().lower())
        return names

    def _registered_prog_ids(self) -> set[str]:
        if os.name != "nt":
            return set()
        try:
            import winreg
        except ImportError:
            return set()

        registered: set[str] = set()
        for backend in ("haochen_com", "autocad_com"):
            for prog_id in self._backend_prog_ids(backend):
                try:
                    with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prog_id):
                        registered.add(prog_id.lower())
                except OSError:
                    continue
        return registered

    def inspect_backends(self) -> dict[str, dict[str, object]]:
        processes = self._running_process_names()
        registered_prog_ids = self._registered_prog_ids()
        disabled = self._disabled_backends()
        inspected: dict[str, dict[str, object]] = {}

        for backend in self._configured_auto_backends():
            if backend == "oda":
                oda_candidates = [candidate for candidate in self._candidate_oda_paths() if candidate.exists()]
                inspected[backend] = {
                    "detected": bool(oda_candidates),
                    "disabled": backend in disabled,
                    "reason": "binary_found" if oda_candidates else "binary_missing",
                }
                continue

            script_ok = False
            reason = "unsupported"
            if backend == "haochen_com":
                script_ok = self._service_script_path("haochen_optimized_converter.py").exists()
            elif backend == "autocad_com":
                script_ok = self._service_script_path("autocad_converter.py").exists()

            running = bool(self._backend_process_names(backend) & processes)
            registered = any(prog_id.lower() in registered_prog_ids for prog_id in self._backend_prog_ids(backend))
            detected = script_ok and (running or registered)
            if not script_ok:
                reason = "script_missing"
            elif running:
                reason = "process_running"
            elif registered:
                reason = "registered"
            else:
                reason = "not_detected"

            inspected[backend] = {
                "detected": detected,
                "disabled": backend in disabled,
                "reason": reason,
            }

        return inspected

    def _select_auto_backends(self) -> list[str]:
        # In auto mode we keep the full configured fallback chain in order, filtering only
        # disabled backends. This preserves the intended semantics:
        # haochen_com -> autocad_com -> oda (unless disabled).
        configured = [
            backend
            for backend in self._configured_auto_backends()
            if backend not in self._disabled_backends()
        ]
        inspected = self.inspect_backends()

        selected: list[str] = []
        for backend in configured:
            reason = inspected.get(backend, {}).get("reason")
            # If the Python COM bridge script itself is missing, this backend can never run.
            if backend in {"haochen_com", "autocad_com"} and reason == "script_missing":
                continue
            selected.append(backend)

        if not selected:
            selected = configured

        logger.info(
            "dwg_auto_backends_selected",
            selected=selected,
            strategy="configured_fallback_chain",
        )
        return selected

    def _libredwg_install_root(self) -> Path:
        path = Path(self.libredwg_install_dir)
        if path.is_absolute():
            return path
        return (self._repo_root() / path).resolve()

    def _candidate_libredwg_paths(self) -> Iterable[Path]:
        if self.libredwg_dwg2dxf_path:
            yield self._resolve_support_path(self.libredwg_dwg2dxf_path)

        for binary_name in ("dwg2dxf.exe", "dwg2dxf"):
            discovered = shutil.which(binary_name)
            if discovered:
                yield Path(discovered)

        install_root = self._libredwg_install_root()
        yield install_root / "dwg2dxf.exe"
        yield install_root / "dwg2dxf"

        if install_root.exists():
            yield from sorted(install_root.rglob("dwg2dxf.exe"))
            yield from sorted(install_root.rglob("dwg2dxf"))

    def _resolve_libredwg_binary(self) -> Path:
        seen: set[Path] = set()
        for candidate in self._candidate_libredwg_paths():
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            if resolved.exists():
                return resolved

        if self.libredwg_auto_download:
            return self._download_libredwg()

        raise ValueError(
            "LibreDWG dwg2dxf executable was not found. Configure LIBREDWG_DWG2DXF_PATH "
            "or enable LIBREDWG_AUTO_DOWNLOAD."
        )

    def _download_libredwg(self) -> Path:
        download_url = self.libredwg_download_url.strip()
        if not download_url:
            raise ValueError("LIBREDWG_DOWNLOAD_URL is empty and no local dwg2dxf executable was found.")

        install_root = self._libredwg_install_root()
        install_root.mkdir(parents=True, exist_ok=True)
        archive_name = Path(urlparse(download_url).path).name or "libredwg-win64.zip"
        archive_path = install_root.parent / archive_name

        if not archive_path.exists():
            logger.info("libredwg_download_started", url=download_url, destination=str(archive_path))
            with urllib.request.urlopen(download_url, timeout=self.cad_converter_timeout) as response:
                archive_path.write_bytes(response.read())

        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(install_root)

        for candidate in self._candidate_libredwg_paths():
            resolved = candidate.resolve()
            if resolved.exists():
                logger.info("libredwg_download_succeeded", binary=str(resolved))
                return resolved

        raise ValueError(
            f"LibreDWG download completed but dwg2dxf.exe was not found under: {install_root}"
        )

    def _repair_libredwg_dxf_structure(self, raw_output_path: Path) -> None:
        lines = raw_output_path.read_text(encoding="utf-8", errors="replace").splitlines()
        repaired_lines: list[str] = []
        expect_group_code = True
        merged_lines = 0

        for line in lines:
            stripped = line.strip()
            if expect_group_code:
                if stripped and stripped.lstrip("+-").isdigit():
                    repaired_lines.append(line)
                    expect_group_code = False
                    continue
                if not repaired_lines:
                    raise ValueError(
                        f"LibreDWG emitted an invalid DXF structure at the start of {raw_output_path.name}."
                    )
                repaired_lines[-1] += line
                merged_lines += 1
                continue

            repaired_lines.append(line)
            expect_group_code = True

        raw_output_path.write_text(
            "\n".join(repaired_lines) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        if merged_lines:
            logger.info("libredwg_structure_repaired", merged_lines=merged_lines, file=str(raw_output_path))

    def _sanitize_materials_for_save(self, doc) -> None:
        invalid_names = []
        for name, entry in list(doc.materials.object_dict.items()):
            material = entry
            if isinstance(entry, str):
                material = doc.entitydb.get(entry)
            if material is None or getattr(material, "dxftype", lambda: None)() != "MATERIAL":
                doc.materials.object_dict.discard(name)
                invalid_names.append(name)

        if invalid_names:
            logger.info("dwg_conversion_sanitized_materials", removed=invalid_names)
            doc.header["$CMATERIAL"] = "0"

        doc.materials.create_required_entries()

    def _validate_and_finalize_dxf(self, raw_output_path: Path, final_output_path: Path) -> str:
        doc = ezdxf.readfile(str(raw_output_path))
        self._sanitize_materials_for_save(doc)

        validated_output = final_output_path.with_suffix(".validated.dxf")
        doc.saveas(str(validated_output))
        validated_output.replace(final_output_path)
        return str(final_output_path)

    def _run_com_converter(
        self,
        converter_module: str,
        class_name: str,
        dwg_file_path: str,
        output_dxf_path: str,
    ) -> str:
        repo_root = self._repo_root()
        backend_dir = self._backend_root()
        com_input_path, com_output_path, final_output_path = self._prepare_com_paths(
            dwg_file_path,
            output_dxf_path,
            converter_module.rsplit(".", 1)[-1],
        )
        python_path_parts = [str(backend_dir), str(repo_root)]
        existing = os.environ.get("PYTHONPATH")
        if existing:
            python_path_parts.append(existing)
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(python_path_parts)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        command = [
            sys.executable,
            "-m",
            "app.services.com_converter_cli",
            "--module",
            converter_module,
            "--class",
            class_name,
            "--dwg",
            str(com_input_path),
            "--output",
            str(com_output_path),
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self._com_attempt_timeout(),
                env=env,
                cwd=str(repo_root),
                **self._subprocess_run_kwargs(),
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError(
                f"{class_name} timed out after {self._com_attempt_timeout()}s while opening or converting DWG."
            ) from exc
        if completed.returncode != 0:
            raise ValueError((completed.stderr or completed.stdout or "").strip() or f"exit {completed.returncode}")
        if not com_output_path.exists():
            raise ValueError(f"COM conversion finished but output file is missing: {com_output_path}")
        finalized = self._validate_and_finalize_dxf(com_output_path, final_output_path)
        self._cleanup_com_workspace(com_input_path.parent)
        logger.info("com_conversion_succeeded", converter=class_name, output=finalized)
        return finalized

    def _cleanup_com_workspace(self, workspace_dir: Path) -> None:
        for attempt in range(3):
            try:
                shutil.rmtree(workspace_dir, ignore_errors=False)
                return
            except OSError as exc:
                if attempt == 2:
                    logger.warning("com_workspace_cleanup_failed", workspace=str(workspace_dir), error=str(exc))
                    return
                time.sleep(0.5 * (attempt + 1))

    def _convert_via_haochen_com(self, dwg_file_path: str, output_dxf_path: str) -> str:
        self._ensure_service_script("haochen_optimized_converter.py")
        return self._run_com_converter(
            "app.services.haochen_optimized_converter",
            "OptimizedHaoChenCADConverter",
            dwg_file_path,
            output_dxf_path,
        )

    def _convert_via_autocad_com(self, dwg_file_path: str, output_dxf_path: str) -> str:
        self._ensure_service_script("autocad_converter.py")
        return self._run_com_converter(
            "app.services.autocad_converter",
            "AutoCADConverter",
            dwg_file_path,
            output_dxf_path,
        )

    def _convert_via_libredwg(self, dwg_file_path: str, output_dir: Path, output_dxf_path: str) -> str:
        binary = self._resolve_libredwg_binary()
        raw_output_path = output_dir / "_libredwg_raw_output.dxf"
        command = [str(binary), dwg_file_path, "-o", str(raw_output_path)]

        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=self.cad_converter_timeout,
            **self._subprocess_run_kwargs(),
        )
        if completed.returncode != 0 and not raw_output_path.exists():
            raise ValueError(
                f"LibreDWG conversion failed: {(completed.stderr or completed.stdout).strip()}"
            )
        if not raw_output_path.exists():
            raise ValueError(
                f"LibreDWG conversion finished but output file is missing: {raw_output_path}"
            )
        if completed.returncode != 0:
            logger.warning(
                "libredwg_conversion_completed_with_warnings",
                returncode=completed.returncode,
                stderr=(completed.stderr or "").strip()[:2000],
            )

        self._repair_libredwg_dxf_structure(raw_output_path)
        finalized = self._validate_and_finalize_dxf(raw_output_path, Path(output_dxf_path))
        try:
            raw_output_path.unlink(missing_ok=True)
        except OSError:
            logger.warning("libredwg_raw_cleanup_failed", file=str(raw_output_path))
        logger.info("libredwg_conversion_succeeded", output=finalized)
        return finalized

    def _candidate_oda_paths(self) -> Iterable[Path]:
        if self.oda_path:
            yield self._resolve_support_path(self.oda_path)

        discovered = shutil.which("ODAFileConverter.exe") or shutil.which("ODAFileConverter")
        if discovered:
            yield Path(discovered)

        for root in (
            Path("C:/Program Files/ODA"),
            Path("C:/Program Files (x86)/ODA"),
        ):
            if not root.exists():
                continue
            yield from sorted(root.rglob("ODAFileConverter.exe"))

    def _resolve_oda_path(self) -> Path:
        for candidate in self._candidate_oda_paths():
            resolved = candidate.resolve()
            if resolved.exists():
                return resolved
        raise ValueError(
            "ODA File Converter was not found. Install it from "
            "https://www.opendesign.com/GUESTFILES/ODA_FILE_CONVERTER "
            "or set ODA_FILE_CONVERTER_PATH."
        )

    def _convert_via_oda(self, dwg_file_path: str, output_dir: Path, output_dxf_path: str) -> str:
        oda_exe = self._resolve_oda_path()

        command = [
            str(oda_exe),
            str(Path(dwg_file_path).parent),
            str(output_dir),
            self.oda_output_version,
            self.oda_output_format,
            "0",
            "1",
            Path(dwg_file_path).name,
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=self.cad_converter_timeout,
            **self._subprocess_run_kwargs(),
        )
        if completed.returncode != 0:
            raise ValueError(f"ODA conversion failed: {completed.stderr or completed.stdout}")
        if not Path(output_dxf_path).exists():
            raise ValueError(f"ODA conversion finished but output file is missing: {output_dxf_path}")
        finalized = self._validate_and_finalize_dxf(Path(output_dxf_path), Path(output_dxf_path))
        logger.info("oda_conversion_succeeded", output=finalized)
        return finalized
