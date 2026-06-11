from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path


def _find_lib_dir() -> Path:
    """Walk up from this file to find the project root containing lib/config.py."""
    current = Path(__file__).resolve().parent
    for _ in range(10):
        candidate = current / "lib" / "config.py"
        if candidate.exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    raise RuntimeError(
        "Cannot locate lib/ directory. "
        "Ensure cli/ and lib/ are siblings under the same project root."
    )


def ensure_lib_path() -> Path:
    root = _find_lib_dir()
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return root


@lru_cache(maxsize=1)
def get_settings():
    ensure_lib_path()
    from lib.config import get_settings as _get_settings
    return _get_settings()


@lru_cache(maxsize=1)
def get_text_extractor():
    ensure_lib_path()
    from lib.functions.text_extractor import TextExtractor
    return TextExtractor()


@lru_cache(maxsize=1)
def get_dwg_converter():
    ensure_lib_path()
    from lib.functions.dwg_converter import DWGConverter
    settings = get_settings()
    return DWGConverter(
        converter_backend=settings.DWG_CONVERTER_BACKEND,
        dwg_auto_backends=settings.DWG_AUTO_BACKENDS,
        dwg_disabled_backends=settings.DWG_DISABLED_BACKENDS,
        oda_path=settings.ODA_FILE_CONVERTER_PATH,
        oda_output_version=settings.ODA_OUTPUT_VERSION,
        oda_output_format=settings.ODA_OUTPUT_FORMAT,
        cad_converter_timeout=settings.CAD_CONVERTER_TIMEOUT,
        libredwg_dwg2dxf_path=settings.LIBREDWG_DWG2DXF_PATH,
        libredwg_install_dir=settings.LIBREDWG_INSTALL_DIR,
        libredwg_download_url=settings.LIBREDWG_DOWNLOAD_URL,
        libredwg_auto_download=settings.LIBREDWG_AUTO_DOWNLOAD,
    )


@lru_cache(maxsize=1)
def get_text_applier():
    ensure_lib_path()
    from lib.functions.text_applier import TextApplier
    return TextApplier()


@lru_cache(maxsize=1)
def get_translator():
    ensure_lib_path()
    from lib.functions.translator import Translator
    return Translator()


@lru_cache(maxsize=1)
def get_pipeline():
    ensure_lib_path()
    from lib.workflow.pipeline import get_pipeline as _get_pipeline
    return _get_pipeline()


@lru_cache(maxsize=1)
def get_runtime_config_service():
    ensure_lib_path()
    from lib.services.runtime_config_service import runtime_config_service
    return runtime_config_service


@lru_cache(maxsize=1)
def get_llm_excel_processor():
    ensure_lib_path()
    from lib.services.llm.translation_service import llm_excel_processor
    return llm_excel_processor


@lru_cache(maxsize=1)
def get_llm_translation_service():
    ensure_lib_path()
    from lib.services.llm.translation_service import llm_translation_service
    return llm_translation_service
