from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a COM CAD converter in a subprocess.")
    parser.add_argument("--module")
    parser.add_argument("--file")
    parser.add_argument("--class", dest="class_name", required=True)
    parser.add_argument("--dwg", required=True)
    parser.add_argument("--output", required=True)
    return parser


def _load_module(module_name: str | None, file_path: str | None):
    if module_name:
        return importlib.import_module(module_name)

    if not file_path:
        raise ValueError("Either --module or --file is required.")

    source_path = Path(file_path).resolve()
    spec = importlib.util.spec_from_file_location(source_path.stem, source_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load converter module from: {source_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    args = _build_parser().parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    try:
        import pythoncom  # type: ignore
    except ImportError:
        pythoncom = None

    if pythoncom is not None:
        pythoncom.CoInitialize()

    converter = None
    try:
        module = _load_module(args.module, args.file)
        converter_class = getattr(module, args.class_name)
        converter = converter_class()

        if not converter.connect_to_cad():
            raise RuntimeError("connect_to_cad() returned False")
        if not converter.open_dwg_file(args.dwg):
            raise RuntimeError("open_dwg_file() returned False")
        if not converter.convert_to_dxf_optimized(args.output):
            raise RuntimeError("convert_to_dxf_optimized() returned False")

        print(json.dumps({"success": True, "module": args.module, "class": args.class_name}))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "success": False,
                    "module": args.module or args.file,
                    "class": args.class_name,
                    "error": str(exc),
                }
            ),
            file=sys.stderr,
        )
        return 1
    finally:
        if converter is not None:
            try:
                converter.close_document()
            except Exception:
                pass
            try:
                converter.disconnect()
            except Exception:
                pass
        if pythoncom is not None:
            pythoncom.CoUninitialize()


if __name__ == "__main__":
    raise SystemExit(main())
