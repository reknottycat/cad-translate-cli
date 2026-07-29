from __future__ import annotations

from pathlib import Path

from cli.utils import backend_bridge
from lib.functions.dwg_converter import DWGConverter


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_cli_converter_resolves_lib_layout() -> None:
    converter = DWGConverter()

    assert converter._source_root() == REPOSITORY_ROOT / "lib"
    assert converter._backend_root() == REPOSITORY_ROOT / "lib"
    assert converter._repo_root() == REPOSITORY_ROOT
    assert converter._service_package() == "lib.services"
    assert converter._service_script_path("haochen_optimized_converter.py").is_file()
    assert converter._service_script_path("autocad_converter.py").is_file()


def test_cli_bridge_loads_lib_package() -> None:
    assert backend_bridge._repo_root() == REPOSITORY_ROOT
    assert backend_bridge._backend_dir() == REPOSITORY_ROOT / "lib"
    assert backend_bridge._package_name() == "lib"

    settings = backend_bridge.get_settings()
    converter = backend_bridge.get_dwg_converter()

    assert settings.DWG_AUTO_BACKENDS == "haochen_com,autocad_com,oda"
    assert isinstance(converter, DWGConverter)
