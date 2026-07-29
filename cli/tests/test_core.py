import json
from importlib.util import find_spec
from pathlib import Path

from click.testing import CliRunner


def test_namespace_package_importable():
    spec = find_spec("cli")
    assert spec is not None


def test_create_project_data_defaults():
    from cli.core.project import create_project_data

    data = create_project_data("demo")

    assert data["name"] == "demo"
    assert data["status"] == "idle"
    assert data["source_files"] == []


def test_scan_cad_files_filters_extensions(tmp_path: Path):
    from cli.core.files import scan_cad_files

    (tmp_path / "a.dwg").write_text("x", encoding="utf-8")
    (tmp_path / "b.dxf").write_text("x", encoding="utf-8")
    (tmp_path / "c.txt").write_text("x", encoding="utf-8")

    result = scan_cad_files(tmp_path)

    assert result["total_dwg"] == 1
    assert result["total_dxf"] == 1


def test_session_tracks_dirty_state():
    from cli.core.session import Session

    session = Session()

    assert session.is_modified() is False
    session.mark_modified()
    assert session.is_modified() is True


def test_build_context_merges_defaults():
    from cli.core.pipeline import build_context

    project = {"target_language": "en", "converter_backend": "auto"}

    context = build_context(project_data=project, input_file="a.dxf", output_dir="out")

    assert context["input_file"] == "a.dxf"
    assert context["target_language"] == "en"
    assert context["converter_backend"] == "auto"


def test_summarize_task_metadata_extracts_core_fields():
    from cli.core.tasks import summarize_task_metadata

    metadata = {
        "task_id": "abc12345",
        "original_filename": "a.dwg",
        "text_count": 3,
        "translation_count": 2,
    }

    summary = summarize_task_metadata(metadata)

    assert summary["task_id"] == "abc12345"
    assert summary["text_count"] == 3


def test_help_command():
    from cli.cad_cli import cli

    result = CliRunner().invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "project" in result.output


def test_safe_console_text_replaces_unencodable_chars(monkeypatch):
    import cli.cad_cli as cad_cli

    class DummyStdout:
        encoding = "gbk"

    monkeypatch.setattr(cad_cli.sys, "stdout", DummyStdout())

    rendered = cad_cli._safe_console_text("孔径 ∅20")

    assert "?" in rendered


def test_project_new_json():
    from cli.cad_cli import cli

    result = CliRunner().invoke(cli, ["--json", "project", "new", "--name", "demo"])

    assert result.exit_code == 0
    assert '"project": "demo"' in result.output


def test_pipeline_convert_help_exists():
    from cli.cad_cli import cli

    result = CliRunner().invoke(cli, ["pipeline", "convert", "--help"])

    assert result.exit_code == 0
    assert "--input" in result.output


def test_pipeline_translate_excel_help_exists():
    from cli.cad_cli import cli

    result = CliRunner().invoke(cli, ["pipeline", "translate-excel", "--help"])

    assert result.exit_code == 0
    assert "--target-language" in result.output


def test_release_build_help_exists():
    from cli.cad_cli import cli

    result = CliRunner().invoke(cli, ["release", "build", "--help"])

    assert result.exit_code == 0
    assert "Build local package artifacts" in result.output


def test_release_smoke_help_exists():
    from cli.cad_cli import cli

    result = CliRunner().invoke(cli, ["release", "smoke", "--help"])

    assert result.exit_code == 0
    assert "Run beginner-friendly smoke checks" in result.output


def test_release_package_info_json():
    from cli.cad_cli import cli

    result = CliRunner().invoke(cli, ["--json", "release", "package-info"])

    assert result.exit_code == 0
    assert '"package_name": "cad-translate"' in result.output
    assert '"entry_point": "cad-translate"' in result.output


def test_config_show_reports_detected_backends(monkeypatch):
    import cli.cad_cli as cad_cli
    from cli.cad_cli import cli

    class DummySettings:
        DWG_CONVERTER_BACKEND = "auto"
        DWG_AUTO_BACKENDS = "haochen_com,autocad_com,oda"
        DWG_DISABLED_BACKENDS = "haochen_com"

    class DummyConverter:
        @staticmethod
        def inspect_backends():
            return {"autocad_com": {"detected": True, "disabled": False, "reason": "registered"}}

    class DummyRuntimeService:
        @staticmethod
        def get_cad_defaults_summary():
            return {
                "target_language": "ru",
                "translation_mode": "add",
                "font_name": "Arial",
                "font_size_reduction": 3,
                "default_output_dir": "outputs/custom",
                "config_file": "runtime.json",
            }

        @staticmethod
        def get_effective_config_summary():
            return {
                "paths": {
                    "global_config": "<USER_HOME>/.config/cad-translate/config.json",
                    "project_config": "C:/work/.cad-translaterc",
                },
                "sources": {
                    "cad.target_language": "global",
                },
            }

    monkeypatch.setattr(cad_cli, "get_settings", lambda: DummySettings())
    monkeypatch.setattr(cad_cli, "get_dwg_converter", lambda: DummyConverter())
    monkeypatch.setattr(cad_cli, "get_runtime_config_service", lambda: DummyRuntimeService())

    result = CliRunner().invoke(cli, ["--json", "config", "show"])

    assert result.exit_code == 0
    assert '"dwg_converter_backend": "auto"' in result.output
    assert '"dwg_disabled_backends": "haochen_com"' in result.output
    assert '"detected_backends"' in result.output
    assert '"target_language": "ru"' in result.output
    assert '"translation_mode": "add"' in result.output


def test_config_set_updates_cad_defaults(monkeypatch):
    import cli.cad_cli as cad_cli
    from cli.cad_cli import cli

    captured = {}

    class DummyRuntimeService:
        @staticmethod
        def update_cad_defaults(payload):
            captured["payload"] = payload
            return {"message": "saved", "runtime": payload}

    monkeypatch.setattr(cad_cli, "get_runtime_config_service", lambda: DummyRuntimeService())

    result = CliRunner().invoke(
        cli,
        [
            "--json",
            "config",
            "set",
            "--target-language",
            "ru",
            "--translation-mode",
            "add",
            "--font-name",
            "Arial",
            "--font-size-reduction",
            "3",
        ],
    )

    assert result.exit_code == 0
    assert captured["payload"]["target_language"] == "ru"
    assert captured["payload"]["translation_mode"] == "add"
    assert captured["payload"]["font_name"] == "Arial"
    assert captured["payload"]["font_size_reduction"] == 3


def test_config_set_updates_path_value(monkeypatch):
    import cli.cad_cli as cad_cli
    from cli.cad_cli import cli

    captured = {}

    class DummyRuntimeService:
        @staticmethod
        def set_config_value(path, value):
            captured["path"] = path
            captured["value"] = value
            return {"path": path, "value": value, "config_file": "runtime.json"}

    monkeypatch.setattr(cad_cli, "get_runtime_config_service", lambda: DummyRuntimeService())

    result = CliRunner().invoke(
        cli,
        [
            "--json",
            "config",
            "set",
            "cad.target_language",
            "ru",
        ],
    )

    assert result.exit_code == 0
    assert captured["path"] == "cad.target_language"
    assert captured["value"] == "ru"


def test_onboard_global_non_interactive_saves_core_defaults(monkeypatch):
    import cli.cad_cli as cad_cli
    from cli.cad_cli import cli

    captured: dict[str, object] = {}

    class DummyConverter:
        @staticmethod
        def inspect_backends():
            return {
                "haochen_com": {"detected": False, "disabled": False, "reason": "not installed"},
                "autocad_com": {"detected": True, "disabled": False, "reason": "registered"},
                "oda": {"detected": True, "disabled": False, "reason": "binary found"},
            }

    class DummyRuntimeService:
        @staticmethod
        def get_cad_defaults_summary():
            return {
                "target_language": "en",
                "translation_mode": "replace",
                "font_name": "Arial",
                "font_size_reduction": 3,
                "default_output_dir": "outputs/custom",
                "converter_backend": "auto",
            }

        @staticmethod
        def update_cad_defaults(payload):
            captured["cad"] = payload
            return {"message": "cad runtime defaults saved", "runtime": payload, "config_file": "runtime.json"}

        @staticmethod
        def update_runtime_config(payload):
            captured["llm"] = payload
            return {"message": "translation runtime config saved", "runtime": payload, "config_file": "runtime.json"}

        @staticmethod
        def validate_effective_config():
            captured["validate"] = True
            return {"success": True, "valid": True, "errors": [], "config_file": "runtime.json"}

        @staticmethod
        def test_connection(payload):
            captured["test"] = payload
            return {"success": True, "reachable": True, "status_code": 200, "message": "connection ok"}

    monkeypatch.setattr(cad_cli, "get_dwg_converter", lambda: DummyConverter())
    monkeypatch.setattr(cad_cli, "get_runtime_config_service", lambda: DummyRuntimeService())

    result = CliRunner().invoke(
        cli,
        [
            "--json",
            "onboard",
            "--scope",
            "global",
            "--target-language",
            "ru",
            "--translation-mode",
            "add",
            "--converter-backend",
            "auto",
            "--provider",
            "openrouter",
            "--model",
            "stepfun/step-3.5-flash:free",
            "--api-key",
            "sk-demo-secret",
            "--base-url",
            "https://openrouter.ai/api/v1",
            "--system-prompt-mode",
            "cad_specialized",
            "--glossary-file",
            str(Path("backend") / "DocuTranslate.csv"),
            "--non-interactive",
        ],
    )

    assert result.exit_code == 0
    assert captured["cad"]["target_language"] == "ru"
    assert captured["cad"]["translation_mode"] == "add"
    assert captured["cad"]["converter_backend"] == "auto"
    assert captured["llm"]["provider"] == "openrouter"
    assert captured["llm"]["system_prompt_mode"] == "cad_specialized"
    assert captured["validate"] is True
    assert captured["test"]["provider"] == "openrouter"


def test_onboard_project_scope_uses_project_config(monkeypatch, tmp_path):
    import cli.cad_cli as cad_cli
    from cli.cad_cli import cli

    captured: dict[str, object] = {}

    class DummyConverter:
        @staticmethod
        def inspect_backends():
            return {
                "autocad_com": {"detected": True, "disabled": False, "reason": "registered"}
            }

    class DummyRuntimeService:
        @staticmethod
        def get_cad_defaults_summary():
            return {
                "target_language": "en",
                "translation_mode": "replace",
                "font_name": "Arial",
                "font_size_reduction": 3,
                "default_output_dir": "outputs/custom",
                "converter_backend": "auto",
            }

        @staticmethod
        def update_project_config(payload):
            captured["project"] = payload
            return {
                "message": "project config saved",
                "runtime": payload,
                "config_file": str(tmp_path / ".cad-translaterc"),
            }

        @staticmethod
        def validate_effective_config():
            captured["validate"] = True
            return {"success": True, "valid": True, "errors": [], "config_file": "runtime.json"}

    monkeypatch.setattr(cad_cli, "get_dwg_converter", lambda: DummyConverter())
    monkeypatch.setattr(cad_cli, "get_runtime_config_service", lambda: DummyRuntimeService())

    result = CliRunner().invoke(
        cli,
        [
            "--json",
            "onboard",
            "--scope",
            "project",
            "--target-language",
            "en",
            "--translation-mode",
            "replace",
            "--converter-backend",
            "oda",
            "--skip-llm",
            "--skip-converter-check",
            "--non-interactive",
        ],
    )

    assert result.exit_code == 0
    assert captured["project"]["cad"]["target_language"] == "en"
    assert captured["project"]["cad"]["translation_mode"] == "replace"
    assert captured["project"]["cad"]["converter_backend"] == "oda"
    assert captured["validate"] is True


def test_config_get_reads_nested_path(monkeypatch):
    import cli.cad_cli as cad_cli
    from cli.cad_cli import cli

    class DummyRuntimeService:
        @staticmethod
        def get_effective_config_summary():
            return {
                "paths": {
                    "global_config": "<USER_HOME>/.config/cad-translate/config.json",
                    "project_config": "C:/work/.cad-translaterc",
                },
                "cad": {
                    "target_language": "ru",
                    "translation_mode": "add",
                },
            }

        @staticmethod
        def get_config_value(path):
            return {"path": path, "value": "ru"}

    monkeypatch.setattr(cad_cli, "get_runtime_config_service", lambda: DummyRuntimeService())

    result = CliRunner().invoke(cli, ["--json", "config", "get", "cad.target_language"])

    assert result.exit_code == 0
    assert '"path": "cad.target_language"' in result.output
    assert '"value": "ru"' in result.output


def test_config_validate_reports_valid_schema(monkeypatch):
    import cli.cad_cli as cad_cli
    from cli.cad_cli import cli

    class DummyRuntimeService:
        @staticmethod
        def validate_effective_config():
            return {
                "success": True,
                "valid": True,
                "errors": [],
                "config_file": "<USER_HOME>/.config/cad-translate/config.json",
            }

    monkeypatch.setattr(cad_cli, "get_runtime_config_service", lambda: DummyRuntimeService())

    result = CliRunner().invoke(cli, ["--json", "config", "validate"])

    assert result.exit_code == 0
    assert '"valid": true' in result.output
    assert '"errors": []' in result.output


def test_config_show_reports_fixed_global_and_project_paths(monkeypatch):
    import cli.cad_cli as cad_cli
    from cli.cad_cli import cli

    class DummySettings:
        DWG_CONVERTER_BACKEND = "auto"
        DWG_AUTO_BACKENDS = "haochen_com,autocad_com,oda"
        DWG_DISABLED_BACKENDS = ""

    class DummyConverter:
        @staticmethod
        def inspect_backends():
            return {}

    class DummyRuntimeService:
        @staticmethod
        def get_cad_defaults_summary():
            return {"target_language": "en", "translation_mode": "replace"}

        @staticmethod
        def get_effective_config_summary():
            return {
                "paths": {
                    "global_config": "<USER_HOME>/.config/cad-translate/config.json",
                    "project_config": "C:/work/.cad-translaterc",
                },
                "sources": {
                    "target_language": "project",
                },
            }

    monkeypatch.setattr(cad_cli, "get_settings", lambda: DummySettings())
    monkeypatch.setattr(cad_cli, "get_dwg_converter", lambda: DummyConverter())
    monkeypatch.setattr(cad_cli, "get_runtime_config_service", lambda: DummyRuntimeService())

    result = CliRunner().invoke(cli, ["--json", "config", "show"])

    assert result.exit_code == 0
    assert "cad-translate/config.json" in result.output
    assert ".cad-translaterc" in result.output
    assert '"sources"' in result.output


def test_config_llm_show_reports_runtime_summary(monkeypatch):
    import cli.cad_cli as cad_cli
    from cli.cad_cli import cli

    class DummyRuntimeService:
        @staticmethod
        def get_public_runtime_summary():
            return {"provider": "openrouter", "model": "demo-model", "api_key_configured": True}

    monkeypatch.setattr(cad_cli, "get_runtime_config_service", lambda: DummyRuntimeService())

    result = CliRunner().invoke(cli, ["--json", "config", "llm", "show"])

    assert result.exit_code == 0
    assert '"provider": "openrouter"' in result.output
    assert '"model": "demo-model"' in result.output


def test_config_llm_test_runs_connection_check(monkeypatch):
    import cli.cad_cli as cad_cli
    from cli.cad_cli import cli

    captured = {}

    class DummyRuntimeService:
        @staticmethod
        def get_public_runtime_summary():
            return {"provider": "openrouter", "model": "stepfun/step-3.5-flash:free", "base_url": "https://openrouter.ai/api/v1"}

        @staticmethod
        def test_connection(payload):
            captured["payload"] = payload
            return {"success": True, "provider": payload["provider"], "model": payload["model"]}

    monkeypatch.setattr(cad_cli, "get_runtime_config_service", lambda: DummyRuntimeService())

    result = CliRunner().invoke(
        cli,
        [
            "--json",
            "config",
            "llm",
            "test",
            "--provider",
            "openrouter",
            "--model",
            "demo-model",
            "--api-key",
            "sk-demo",
        ],
    )

    assert result.exit_code == 0
    assert captured["payload"]["provider"] == "openrouter"
    assert captured["payload"]["model"] == "demo-model"
    assert captured["payload"]["api_key"] == "sk-demo"


def test_config_llm_test_accepts_explicit_format(monkeypatch):
    import cli.cad_cli as cad_cli
    from cli.cad_cli import cli

    captured = {}

    class DummyRuntimeService:
        @staticmethod
        def get_public_runtime_summary():
            return {
                "provider": "custom",
                "format": "openai_compatible",
                "model": "demo-model",
                "base_url": "https://gateway.example.com/v1",
            }

        @staticmethod
        def test_connection(payload):
            captured["payload"] = payload
            return {"success": True, "provider": payload["provider"], "format": payload["format"]}

    monkeypatch.setattr(cad_cli, "get_runtime_config_service", lambda: DummyRuntimeService())

    result = CliRunner().invoke(
        cli,
        [
            "--json",
            "config",
            "llm",
            "test",
            "--format",
            "anthropic",
            "--provider",
            "anthropic",
            "--model",
            "claude-3-5-haiku-latest",
            "--api-key",
            "sk-ant-demo",
        ],
    )

    assert result.exit_code == 0
    assert captured["payload"]["format"] == "anthropic"
    assert captured["payload"]["provider"] == "anthropic"


def test_config_llm_init_tests_then_saves(monkeypatch):
    import cli.cad_cli as cad_cli
    from cli.cad_cli import cli

    calls = []

    class DummyRuntimeService:
        @staticmethod
        def get_public_runtime_summary():
            return {"provider": "openrouter", "model": "stepfun/step-3.5-flash:free", "base_url": "https://openrouter.ai/api/v1"}

        @staticmethod
        def test_connection(payload):
            calls.append(("test", payload))
            return {"success": True}

        @staticmethod
        def update_runtime_config(payload):
            calls.append(("save", payload))
            return {"message": "saved", "runtime": {"provider": payload["provider"], "model": payload["model"]}}

    monkeypatch.setattr(cad_cli, "get_runtime_config_service", lambda: DummyRuntimeService())

    result = CliRunner().invoke(
        cli,
        [
            "--json",
            "config",
            "llm",
            "init",
            "--provider",
            "openrouter",
            "--model",
            "demo-model",
            "--api-key",
            "sk-demo",
            "--base-url",
            "https://openrouter.ai/api/v1",
        ],
    )

    assert result.exit_code == 0
    assert calls[0][0] == "test"
    assert calls[1][0] == "save"
    assert calls[1][1]["provider"] == "openrouter"


def test_config_llm_init_saves_format(monkeypatch):
    import cli.cad_cli as cad_cli
    from cli.cad_cli import cli

    calls = []

    class DummyRuntimeService:
        @staticmethod
        def get_public_runtime_summary():
            return {
                "provider": "custom",
                "format": "openai_compatible",
                "model": "demo-model",
                "base_url": "http://127.0.0.1:11434",
            }

        @staticmethod
        def test_connection(payload):
            calls.append(("test", payload))
            return {"success": True}

        @staticmethod
        def update_runtime_config(payload):
            calls.append(("save", payload))
            return {
                "message": "saved",
                "runtime": {
                    "provider": payload["provider"],
                    "format": payload["format"],
                    "model": payload["model"],
                },
            }

    monkeypatch.setattr(cad_cli, "get_runtime_config_service", lambda: DummyRuntimeService())

    result = CliRunner().invoke(
        cli,
        [
            "--json",
            "config",
            "llm",
            "init",
            "--format",
            "ollama",
            "--provider",
            "ollama",
            "--model",
            "qwen2.5:7b",
            "--base-url",
            "http://127.0.0.1:11434",
            "--non-interactive",
        ],
    )

    assert result.exit_code == 0
    assert calls[0][1]["format"] == "ollama"
    assert calls[1][1]["format"] == "ollama"


def test_config_llm_init_saves_prompt_mode_and_glossary(monkeypatch):
    import cli.cad_cli as cad_cli
    from cli.cad_cli import cli

    calls = []

    class DummyRuntimeService:
        @staticmethod
        def get_public_runtime_summary():
            return {
                "provider": "custom",
                "format": "openai_compatible",
                "model": "demo-model",
                "base_url": "https://gateway.example.com/v1",
                "system_prompt_mode": "default",
            }

        @staticmethod
        def test_connection(payload):
            calls.append(("test", payload))
            return {"success": True}

        @staticmethod
        def update_runtime_config(payload):
            calls.append(("save", payload))
            return {"message": "saved", "runtime": payload}

    monkeypatch.setattr(cad_cli, "get_runtime_config_service", lambda: DummyRuntimeService())

    result = CliRunner().invoke(
        cli,
        [
            "--json",
            "config",
            "llm",
            "init",
            "--format",
            "openai_compatible",
            "--provider",
            "openrouter",
            "--model",
            "demo-model",
            "--api-key",
            "sk-demo",
            "--base-url",
            "https://openrouter.ai/api/v1",
            "--system-prompt-mode",
            "custom",
            "--custom-system-prompt",
            "Translate CAD labels conservatively.",
            "--glossary-file",
            "C:\\temp\\terms.xlsx",
            "--reasoning-enabled",
            "--non-interactive",
        ],
    )

    assert result.exit_code == 0
    assert calls[1][1]["system_prompt_mode"] == "custom"
    assert calls[1][1]["custom_system_prompt"] == "Translate CAD labels conservatively."
    assert calls[1][1]["glossary_file"] == "C:\\temp\\terms.xlsx"
    assert calls[1][1]["reasoning_enabled"] is True


def test_config_llm_init_accepts_nvidia_provider(monkeypatch):
    import cli.cad_cli as cad_cli
    from cli.cad_cli import cli

    calls = []

    class DummyRuntimeService:
        @staticmethod
        def get_public_runtime_summary():
            return {
                "provider": "openrouter",
                "format": "openai_compatible",
                "model": "stepfun/step-3.5-flash:free",
                "base_url": "https://openrouter.ai/api/v1",
                "system_prompt_mode": "default",
            }

        @staticmethod
        def test_connection(payload):
            calls.append(("test", payload))
            return {"success": True}

        @staticmethod
        def update_runtime_config(payload):
            calls.append(("save", payload))
            return {"message": "saved", "runtime": payload}

    monkeypatch.setattr(cad_cli, "get_runtime_config_service", lambda: DummyRuntimeService())

    result = CliRunner().invoke(
        cli,
        [
            "--json",
            "config",
            "llm",
            "init",
            "--format",
            "openai_compatible",
            "--provider",
            "nvidia",
            "--model",
            "moonshotai/kimi-k2.5",
            "--api-key",
            "nvapi-demo",
            "--base-url",
            "https://integrate.api.nvidia.com/v1",
            "--reasoning-enabled",
            "--non-interactive",
        ],
    )

    assert result.exit_code == 0
    assert calls[1][1]["provider"] == "nvidia"
    assert calls[1][1]["reasoning_enabled"] is True


def test_config_llm_init_accepts_fallback_model(monkeypatch):
    import cli.cad_cli as cad_cli
    from cli.cad_cli import cli

    calls = []

    class DummyRuntimeService:
        @staticmethod
        def get_public_runtime_summary():
            return {
                "provider": "openrouter",
                "format": "openai_compatible",
                "model": "primary-model",
                "base_url": "https://openrouter.ai/api/v1",
            }

        @staticmethod
        def test_connection(payload):
            calls.append(("test", payload))
            return {"success": True}

        @staticmethod
        def update_runtime_config(payload):
            calls.append(("save", payload))
            return {"message": "saved", "runtime": payload}

    monkeypatch.setattr(cad_cli, "get_runtime_config_service", lambda: DummyRuntimeService())

    result = CliRunner().invoke(
        cli,
        [
            "--json",
            "config",
            "llm",
            "init",
            "--format",
            "openai_compatible",
            "--provider",
            "openrouter",
            "--model",
            "primary-model",
            "--api-key",
            "sk-primary",
            "--base-url",
            "https://openrouter.ai/api/v1",
            "--fallback-provider",
            "nvidia",
            "--fallback-model",
            "moonshotai/kimi-k2.5",
            "--fallback-api-key",
            "nvapi-fallback",
            "--fallback-base-url",
            "https://integrate.api.nvidia.com/v1",
            "--fallback-reasoning-enabled",
            "--non-interactive",
        ],
    )

    assert result.exit_code == 0
    assert calls[0][1]["fallback_models"][0]["provider"] == "nvidia"
    assert calls[0][1]["fallback_models"][0]["model"] == "moonshotai/kimi-k2.5"
    assert calls[0][1]["fallback_models"][0]["reasoning_enabled"] is True
    assert calls[1][1]["fallback_models"][0]["base_url"] == "https://integrate.api.nvidia.com/v1"


def test_pipeline_apply_accepts_translation_mode(monkeypatch, tmp_path: Path):
    import cli.cad_cli as cad_cli
    from cli.cad_cli import cli

    input_file = tmp_path / "a.dxf"
    excel_file = tmp_path / "a.xlsx"
    input_file.write_text("x", encoding="utf-8")
    excel_file.write_text("x", encoding="utf-8")
    captured = {}

    def fake_run_apply(**kwargs):
        captured.update(kwargs)
        return {"success": True, "task_id": "abc12345"}

    monkeypatch.setattr(cad_cli, "run_apply", fake_run_apply)

    result = CliRunner().invoke(
        cli,
        [
            "--json",
            "pipeline",
            "apply",
            "-i",
            str(input_file),
            "-e",
            str(excel_file),
            "--translation-mode",
            "add",
        ],
    )

    assert result.exit_code == 0
    assert captured["translation_mode"] == "add"


def test_run_translate_excel_populates_cad_extract_translation_column(monkeypatch, tmp_path: Path):
    import pandas as pd
    from cli.core.pipeline import run_translate_excel

    input_file = tmp_path / "extract.xlsx"
    pd.DataFrame(
        [
            {"序号": 1, "原文": "阀门", "译文": ""},
            {"序号": 2, "原文": "阀体", "译文": ""},
        ]
    ).to_excel(input_file, index=False)

    class DummyRuntimeService:
        @staticmethod
        def get_cad_defaults_summary():
            return {"target_language": "ru", "translation_mode": "add"}

    class DummySettings:
        DEFAULT_TARGET_LANGUAGE = "en"

        @staticmethod
        def get_output_path():
            return tmp_path / "default_out"

    class DummyTranslator:
        @staticmethod
        def translate_batch(texts, source_lang="auto", target_lang="en"):
            assert target_lang == "ru"
            return ["клапан", "корпус"]

    monkeypatch.setattr("cli.core.pipeline.get_runtime_config_service", lambda: DummyRuntimeService())
    monkeypatch.setattr("cli.core.pipeline.get_settings", lambda: DummySettings())
    monkeypatch.setattr("cli.core.pipeline.get_llm_translation_service", lambda: DummyTranslator())
    monkeypatch.setattr("cli.core.pipeline._new_task_dir", lambda prefix="cad_cli": ("abc12345", tmp_path / "generated"))

    result = run_translate_excel(str(input_file), output_dir=str(tmp_path / "out"))

    output_df = pd.read_excel(result["output_file"])

    assert result["target_language"] == "ru"
    assert list(output_df["译文"]) == ["клапан", "корпус"]


def test_release_build_produces_artifacts(tmp_path: Path):
    from cli.core.release import build_distributions

    result = build_distributions(output_dir=tmp_path / "dist")

    assert result["success"] is True
    assert any(path.endswith(".whl") for path in result["artifacts"])
    assert any(path.endswith(".tar.gz") for path in result["artifacts"])


def test_save_and_load_project_roundtrip(tmp_path: Path):
    from cli.core.project import create_project_data, load_project, save_project

    project_path = tmp_path / "demo.cad.json"
    original = create_project_data("demo")

    save_project(original, project_path)
    loaded = load_project(project_path)

    assert loaded["name"] == "demo"
    assert loaded["status"] == "idle"


def test_validate_input_file_rejects_unsupported_extension(tmp_path: Path):
    from cli.core.files import validate_input_file

    path = tmp_path / "bad.txt"
    path.write_text("x", encoding="utf-8")

    try:
        validate_input_file(path)
    except ValueError as exc:
        assert "Unsupported file type" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError for unsupported extension")


def test_delete_task_raises_for_missing_task():
    from cli.core.tasks import delete_task

    try:
        delete_task("missing-task-id")
    except FileNotFoundError as exc:
        assert "Task not found" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected FileNotFoundError for missing task")
