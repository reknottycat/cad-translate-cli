from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

import pandas as pd

from cli.core.pipeline import run_apply, run_convert, run_extract


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _sample_dxf() -> Path:
    path = _repo_root() / "241217-11+小样图.dxf"
    if not path.exists():
        raise FileNotFoundError(f"Sample DXF not found: {path}")
    return path


def _sample_dwg() -> Path:
    path = _repo_root() / "1360001401 施工图.dwg"
    if not path.exists():
        raise FileNotFoundError(f"Sample DWG not found: {path}")
    return path


def _resolve_cli(name: str) -> list[str]:
    force = os.environ.get("CLI_ANYTHING_FORCE_INSTALLED", "").strip() == "1"
    path = shutil.which(name)
    if path:
        return [path]
    scripts_dir = Path(sysconfig.get_config_var("userbase") or "") / f"Python{sys.version_info.major}{sys.version_info.minor}" / "Scripts"
    if scripts_dir.exists():
        for candidate in (scripts_dir / f"{name}.exe", scripts_dir / f"{name}-script.py"):
            if candidate.exists():
                if candidate.suffix == ".py":
                    return [sys.executable, str(candidate)]
                return [str(candidate)]
    if force:
        raise RuntimeError(f"{name} not found in PATH. Install with: pip install -e .")
    return [sys.executable, "-m", "cli"]


def test_dxf_extract_apply_roundtrip(tmp_path: Path):
    source = _sample_dxf()

    extract = run_extract(input_file=str(source), output_dir=str(tmp_path / "extract"))
    excel_path = Path(extract["excel_file"])
    assert excel_path.exists()

    df = pd.read_excel(excel_path)
    df["译文"] = df["译文"].astype(object)
    translated_rows = 0
    for idx, value in enumerate(df["原文"].fillna("").astype(str)):
        text = value.strip()
        if text:
            df.loc[idx, "译文"] = f"TEST_{text}"
            translated_rows += 1
        if translated_rows >= 3:
            break
    df.to_excel(excel_path, index=False)

    apply = run_apply(
        input_file=str(source),
        excel_file=str(excel_path),
        output_dir=str(tmp_path / "apply"),
    )
    output_path = Path(apply["output_file"])

    assert output_path.exists()
    assert output_path.stat().st_size > 0
    assert apply["translation_count"] >= 1


def test_dwg_convert_extract_apply_roundtrip(tmp_path: Path):
    source = _sample_dwg()

    convert = run_convert(input_file=str(source), output_dir=str(tmp_path / "convert"))
    converted_dxf = Path(convert["output_file"])
    assert converted_dxf.exists()
    assert converted_dxf.stat().st_size > 0

    extract = run_extract(input_file=str(converted_dxf), output_dir=str(tmp_path / "extract"))
    excel_path = Path(extract["excel_file"])
    assert excel_path.exists()

    df = pd.read_excel(excel_path)
    df["译文"] = df["译文"].astype(object)
    translated_rows = 0
    for idx, value in enumerate(df["原文"].fillna("").astype(str)):
        text = value.strip()
        if text:
            df.loc[idx, "译文"] = f"DWG_{text}"
            translated_rows += 1
        if translated_rows >= 3:
            break
    df.to_excel(excel_path, index=False)

    apply = run_apply(
        input_file=str(converted_dxf),
        excel_file=str(excel_path),
        output_dir=str(tmp_path / "apply"),
    )
    output_path = Path(apply["output_file"])

    assert output_path.exists()
    assert output_path.stat().st_size > 0
    assert apply["translation_count"] >= 1


class TestCLISubprocess:
    CLI_BASE = _resolve_cli("cad-translate")
    ENV = os.environ | {"PYTHONPATH": str(_repo_root() / "agent-harness")}

    def _run(self, args: list[str], check: bool = True):
        return subprocess.run(
            self.CLI_BASE + args,
            capture_output=True,
            text=True,
            check=check,
            env=self.ENV,
        )

    def test_help(self):
        result = self._run(["--help"])
        assert result.returncode == 0
        assert "project" in result.stdout

    def test_project_new_json(self):
        result = self._run(["--json", "project", "new", "--name", "demo"])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["project"] == "demo"
