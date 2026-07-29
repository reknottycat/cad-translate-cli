from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _backend_dir() -> Path:
    return _repo_root() / "backend"


def ensure_backend_path() -> Path:
    backend_dir = _backend_dir()
    backend_str = str(backend_dir)
    if backend_str not in sys.path:
        sys.path.insert(0, backend_str)
    return backend_dir


@lru_cache(maxsize=1)
def get_settings():
    ensure_backend_path()
    from app.config import get_settings as _get_settings

    return _get_settings()


@lru_cache(maxsize=1)
def get_text_extractor():
    ensure_backend_path()
    from app.functions.text_extractor import TextExtractor

    return TextExtractor()


@lru_cache(maxsize=1)
def get_dwg_converter():
    ensure_backend_path()
    from app.functions.dwg_converter import DWGConverter

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
    ensure_backend_path()
    from app.functions.text_applier import TextApplier

    return TextApplier()


@lru_cache(maxsize=1)
def get_translator():
    ensure_backend_path()
    from app.functions.translator import Translator

    return Translator()


@lru_cache(maxsize=1)
def get_cad_pipeline_service():
    ensure_backend_path()
    from app.services.cad_pipeline_service import cad_pipeline_service

    return cad_pipeline_service


@lru_cache(maxsize=1)
def get_pipeline():
    ensure_backend_path()
    from app.workflow.pipeline import get_pipeline as _get_pipeline

    return _get_pipeline()


@lru_cache(maxsize=1)
def get_runtime_config_service():
    ensure_backend_path()
    from app.services.runtime_config_service import runtime_config_service

    return runtime_config_service


@lru_cache(maxsize=1)
def get_llm_excel_processor():
    ensure_backend_path()
    from app.services.llm.translation_service import llm_excel_processor

    return llm_excel_processor


@lru_cache(maxsize=1)
def get_llm_translation_service():
    ensure_backend_path()
    from app.services.llm.translation_service import llm_translation_service

    return llm_translation_service
