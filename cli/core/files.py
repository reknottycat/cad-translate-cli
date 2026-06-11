from __future__ import annotations

from pathlib import Path


def normalize_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def validate_input_file(path: str | Path) -> Path:
    resolved = normalize_path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"Input file not found: {resolved}")
    if resolved.suffix.lower() not in {".dwg", ".dxf", ".xlsx"}:
        raise ValueError(f"Unsupported file type: {resolved.suffix}")
    return resolved


def scan_cad_files(path: str | Path) -> dict[str, object]:
    directory = normalize_path(path)
    if not directory.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")
    dwg_files = sorted(p.name for p in directory.glob("*.dwg"))
    dxf_files = sorted(p.name for p in directory.glob("*.dxf"))
    xlsx_files = sorted(p.name for p in directory.glob("*.xlsx"))
    return {
        "directory": str(directory),
        "dwg_files": dwg_files,
        "dxf_files": dxf_files,
        "xlsx_files": xlsx_files,
        "total_dwg": len(dwg_files),
        "total_dxf": len(dxf_files),
        "total_xlsx": len(xlsx_files),
    }
