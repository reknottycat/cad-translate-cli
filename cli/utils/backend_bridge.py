from __future__ import annotations

import sys
import importlib
from functools import lru_cache
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _backend_dir() -> Path:
    root = _repo_root()
    backend_app = root / "backend" / "app"
    if backend_app.is_dir():
        return backend_app
    cli_lib = root / "lib"
    if cli_lib.is_dir():
        return cli_lib
    raise RuntimeError(f"Unable to locate backend package under: {root}")


def _import_root() -> Path:
    return _backend_dir().parent


def _package_name() -> str:
    return _backend_dir().name


def _import_module(module_name: str):
    return importlib.import_module(f"{_package_name()}.{module_name}")


def ensure_backend_path() -> Path:
    import_root = _import_root()
    import_root_str = str(import_root)
    if import_root_str not in sys.path:
        sys.path.insert(0, import_root_str)
    return _backend_dir()


@lru_cache(maxsize=1)
def get_settings():
    ensure_backend_path()
    return _import_module("config").get_settings()


@lru_cache(maxsize=1)
def get_text_extractor():
    ensure_backend_path()
    return _import_module("functions.text_extractor").TextExtractor()


@lru_cache(maxsize=1)
def get_dwg_converter():
    ensure_backend_path()
    DWGConverter = _import_module("functions.dwg_converter").DWGConverter

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
    return _import_module("functions.text_applier").TextApplier()


@lru_cache(maxsize=1)
def get_translator():
    ensure_backend_path()
    return _import_module("functions.translator").Translator()


@lru_cache(maxsize=1)
def get_cad_pipeline_service():
    ensure_backend_path()
    return _import_module("services.cad_pipeline_service").cad_pipeline_service


@lru_cache(maxsize=1)
def get_pipeline():
    ensure_backend_path()
    return _import_module("workflow.pipeline").get_pipeline()


@lru_cache(maxsize=1)
def get_runtime_config_service():
    ensure_backend_path()
    return _import_module("services.runtime_config_service").runtime_config_service


@lru_cache(maxsize=1)
def get_llm_excel_processor():
    ensure_backend_path()
    return _import_module("services.llm.translation_service").llm_excel_processor


@lru_cache(maxsize=1)
def get_llm_translation_service():
    ensure_backend_path()
    return _import_module("services.llm.translation_service").llm_translation_service
