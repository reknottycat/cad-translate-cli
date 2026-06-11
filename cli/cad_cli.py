#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import click

from cli.core.files import scan_cad_files
from cli.core.pipeline import run_apply, run_convert, run_extract, run_translate_excel
from cli.core.project import create_project_data, load_project, save_project
from cli.core.release import build_distributions, package_info, run_smoke_checks
from cli.core.session import Session
from cli.core.tasks import clear_tasks, delete_task, list_tasks, load_task
from cli.utils.backend_bridge import (
    get_dwg_converter,
    get_runtime_config_service,
    get_settings,
)


_session: Session | None = None
_json_output = False
_repl_mode = False


def get_session() -> Session:
    global _session
    if _session is None:
        _session = Session()
    return _session


def _safe_console_text(value: Any) -> str:
    text = str(value)
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def emit(data: Any, message: str = "") -> None:
    if _json_output:
        click.echo(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        return
    if message:
        click.echo(_safe_console_text(message))
    if isinstance(data, dict):
        for key, value in data.items():
            click.echo(_safe_console_text(f"{key}: {value}"))
    elif isinstance(data, list):
        for item in data:
            click.echo(_safe_console_text(item))
    elif data is not None:
        click.echo(_safe_console_text(data))


def _error_payload(error_type: str, message: str) -> dict[str, Any]:
    return {
        "success": False,
        "error_type": error_type,
        "message": message,
    }


def _coerce_config_value(raw: str) -> Any:
    text = str(raw).strip()
    if not text:
        return ""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        lowered = text.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        if lowered == "null":
            return None
        return raw


def _prompt_or_default(
    value: Any,
    label: str,
    default: Any,
    *,
    non_interactive: bool,
    hide_input: bool = False,
    choice: click.Choice | None = None,
    value_type: type | None = None,
) -> Any:
    if value is not None:
        return value
    if non_interactive:
        return default
    kwargs: dict[str, Any] = {
        "default": default,
        "show_default": True,
    }
    if hide_input:
        kwargs["hide_input"] = True
    if choice is not None:
        kwargs["type"] = choice
    elif value_type is not None:
        kwargs["type"] = value_type
    return click.prompt(label, **kwargs)


def _build_onboard_cad_payload(
    *,
    target_language: str,
    translation_mode: str,
    font_name: str,
    font_size_reduction: int,
    converter_backend: str,
    default_output_dir: str,
) -> dict[str, Any]:
    return {
        "target_language": target_language,
        "translation_mode": translation_mode,
        "font_name": font_name,
        "font_size_reduction": font_size_reduction,
        "default_output_dir": default_output_dir,
        "converter_backend": converter_backend,
    }


def _build_onboard_llm_payload(
    *,
    provider: str,
    api_format: str,
    model: str,
    base_url: str,
    api_key: str,
    system_prompt_mode: str,
    custom_system_prompt: str,
    glossary_file: str,
    reasoning_enabled: bool,
    timeout_seconds: int,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "format": api_format,
        "model": model,
        "base_url": base_url,
        "api_key": api_key,
        "system_prompt_mode": system_prompt_mode,
        "custom_system_prompt": custom_system_prompt,
        "glossary_file": glossary_file,
        "reasoning_enabled": reasoning_enabled,
        "timeout_seconds": timeout_seconds,
    }


def handle_error(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except FileNotFoundError as exc:
            payload = _error_payload("artifact_error", str(exc))
        except ValueError as exc:
            payload = _error_payload("usage_error", str(exc))
        except RuntimeError as exc:
            payload = _error_payload("dependency_error", str(exc))
        except Exception as exc:  # pragma: no cover
            payload = _error_payload("processing_error", str(exc))

        if _json_output:
            click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            click.echo(_safe_console_text(f"Error: {payload['message']}"), err=True)
        if not _repl_mode:
            raise SystemExit(1)

    wrapper.__name__ = func.__name__
    return wrapper


@click.group(invoke_without_command=True)
@click.option("--json", "json_mode", is_flag=True, help="Output as JSON.")
@click.option("--project", "project_path", type=click.Path(), default=None, help="Project file path.")
@click.pass_context
def cli(ctx: click.Context, json_mode: bool, project_path: str | None) -> None:
    """Stateful CAD CLI harness.

    If you are new, start with:

      cad-translate onboard

    If you run the CLI without subcommands, it enters REPL mode.
    """
    global _json_output
    ctx.ensure_object(dict)
    _json_output = json_mode
    ctx.obj["json"] = json_mode
    if project_path:
        session = get_session()
        session.set_project(load_project(project_path), project_path)
    if ctx.invoked_subcommand is None:
        ctx.invoke(repl)


@cli.group("project")
def project_group() -> None:
    """Project commands."""


@project_group.command("new")
@click.option("--name", default="untitled", help="Project name.")
@click.option("--output", "-o", type=click.Path(), default=None, help="Optional project file path.")
@handle_error
def project_new(name: str, output: str | None) -> None:
    data = create_project_data(name)
    session = get_session()
    session.set_project(data, output)
    if output:
        emit(save_project(data, output), f"Created project: {name}")
        return
    emit({"success": True, "project": name, "data": data}, f"Created project: {name}")


@project_group.command("open")
@click.argument("project_path", type=click.Path(exists=True))
@handle_error
def project_open(project_path: str) -> None:
    data = load_project(project_path)
    get_session().set_project(data, project_path)
    emit({"success": True, "project": data.get("name"), "file": project_path}, f"Opened: {project_path}")


@project_group.command("save")
@click.argument("project_path", required=False, type=click.Path())
@handle_error
def project_save(project_path: str | None) -> None:
    session = get_session()
    if session.project_data is None:
        raise ValueError("No active project loaded.")
    target = project_path or session.project_path
    if not target:
        raise ValueError("No project path specified.")
    result = save_project(session.project_data, target)
    session.project_path = target
    session.mark_saved()
    emit(result, f"Saved: {target}")


@project_group.command("info")
@handle_error
def project_info() -> None:
    session = get_session()
    emit(session.get_status())


@cli.group("files")
def files_group() -> None:
    """File inspection commands."""


@files_group.command("list")
@click.option("--path", default=".", type=click.Path(exists=True), help="Directory to scan.")
@handle_error
def files_list(path: str) -> None:
    emit(scan_cad_files(path), f"Files in {path}")


@files_group.command("set-input")
@click.argument("input_file", type=click.Path(exists=True))
@handle_error
def files_set_input(input_file: str) -> None:
    session = get_session()
    session.active_input_file = str(Path(input_file))
    session.mark_modified()
    emit({"success": True, "input_file": session.active_input_file}, "Active input updated")


@cli.group("pipeline")
def pipeline_group() -> None:
    """CAD pipeline commands."""


@pipeline_group.command("extract")
@click.option("--input", "input_file", "-i", type=click.Path(exists=True), required=True)
@click.option("--output-dir", "-o", type=click.Path(), default=None)
@handle_error
def pipeline_extract(input_file: str, output_dir: str | None) -> None:
    result = run_extract(input_file=input_file, output_dir=output_dir)
    session = get_session()
    session.recent_task_id = result["task_id"]
    emit(result, f"Extracted text from {input_file}")


@pipeline_group.command("convert")
@click.option("--input", "input_file", "-i", type=click.Path(exists=True), required=True)
@click.option("--output-dir", "-o", type=click.Path(), default=None)
@click.option("--backend", type=str, default=None, help="Optional backend override.")
@handle_error
def pipeline_convert(input_file: str, output_dir: str | None, backend: str | None) -> None:
    result = run_convert(input_file=input_file, output_dir=output_dir, backend_override=backend)
    session = get_session()
    session.recent_task_id = result["task_id"]
    emit(result, f"Converted {input_file}")


@pipeline_group.command("apply")
@click.option("--input", "input_file", "-i", type=click.Path(exists=True), required=True)
@click.option("--excel", "excel_file", "-e", type=click.Path(exists=True), required=True)
@click.option("--output-dir", "-o", type=click.Path(), default=None)
@click.option("--translation-mode", type=click.Choice(["add", "replace"], case_sensitive=False), default=None)
@click.option("--font-name", type=str, default=None)
@click.option("--font-size-reduction", type=int, default=None)
@handle_error
def pipeline_apply(
    input_file: str,
    excel_file: str,
    output_dir: str | None,
    translation_mode: str | None,
    font_name: str | None,
    font_size_reduction: int | None,
) -> None:
    result = run_apply(
        input_file=input_file,
        excel_file=excel_file,
        output_dir=output_dir,
        translation_mode=translation_mode,
        font_name=font_name,
        font_size_reduction=font_size_reduction,
    )
    session = get_session()
    session.recent_task_id = result["task_id"]
    emit(result, f"Applied translations to {input_file}")


@pipeline_group.command("translate-excel")
@click.option("--input", "input_file", "-i", type=click.Path(exists=True), required=True)
@click.option("--output-dir", "-o", type=click.Path(), default=None)
@click.option("--source-language", type=str, default="auto")
@click.option("--target-language", type=str, default=None)
@click.option("--translation-mode", type=click.Choice(["add", "replace"], case_sensitive=False), default=None)
@handle_error
def pipeline_translate_excel(
    input_file: str,
    output_dir: str | None,
    source_language: str,
    target_language: str | None,
    translation_mode: str | None,
) -> None:
    result = run_translate_excel(
        input_file=input_file,
        output_dir=output_dir,
        source_language=source_language,
        target_language=target_language,
        translation_mode=translation_mode,
    )
    session = get_session()
    session.recent_task_id = result["task_id"]
    emit(result, f"Translated Excel file {input_file}")


@cli.command("onboard", help="First-run guided setup.")
@click.option(
    "--scope",
    type=click.Choice(["global", "project"], case_sensitive=False),
    default="global",
    help="Where to save onboarding config.",
)
@click.option("--target-language", type=str, default=None, help="Default translation language.")
@click.option(
    "--translation-mode",
    type=click.Choice(["add", "replace"], case_sensitive=False),
    default=None,
    help="Default CAD translation mode.",
)
@click.option("--font-name", type=str, default=None, help="Default CAD font name.")
@click.option("--font-size-reduction", type=int, default=None, help="Default font size reduction.")
@click.option(
    "--converter-backend",
    type=click.Choice(["auto", "haochen_com", "autocad_com", "oda"], case_sensitive=False),
    default=None,
    help="Default DWG converter backend.",
)
@click.option("--provider", type=str, default=None, help="LLM provider id.")
@click.option(
    "--format",
    "api_format",
    type=click.Choice(["openai_compatible", "anthropic", "google", "ollama", "lmstudio"], case_sensitive=False),
    default=None,
    help="LLM API format.",
)
@click.option("--model", type=str, default=None, help="LLM model name.")
@click.option("--base-url", type=str, default=None, help="LLM base URL.")
@click.option("--api-key", type=str, default=None, help="LLM API key.")
@click.option(
    "--system-prompt-mode",
    type=click.Choice(["default", "cad_specialized", "custom"], case_sensitive=False),
    default=None,
    help="System prompt mode.",
)
@click.option("--custom-system-prompt", type=str, default=None, help="Custom system prompt.")
@click.option("--glossary-file", type=str, default=None, help="Glossary file path.")
@click.option("--reasoning-enabled/--no-reasoning-enabled", default=None)
@click.option("--timeout-seconds", type=int, default=None)
@click.option("--skip-llm", is_flag=True, help="Skip LLM configuration.")
@click.option("--skip-glossary", is_flag=True, help="Do not auto-use glossary.")
@click.option("--skip-converter-check", is_flag=True, help="Skip backend converter probe.")
@click.option("--non-interactive", is_flag=True, help="Use defaults instead of prompting.")
@handle_error
def onboard(
    scope: str,
    target_language: str | None,
    translation_mode: str | None,
    font_name: str | None,
    font_size_reduction: int | None,
    converter_backend: str | None,
    provider: str | None,
    api_format: str | None,
    model: str | None,
    base_url: str | None,
    api_key: str | None,
    system_prompt_mode: str | None,
    custom_system_prompt: str | None,
    glossary_file: str | None,
    reasoning_enabled: bool | None,
    timeout_seconds: int | None,
    skip_llm: bool,
    skip_glossary: bool,
    skip_converter_check: bool,
    non_interactive: bool,
) -> None:
    """First-run guided setup.

    Writes the preserved core variables (language, mode, DWG backend, LLM config,
    glossary, system prompt mode) into the unified config. Use `--non-interactive`
    to accept recommended defaults.
    """
    settings = get_settings()
    runtime_service = get_runtime_config_service()

    default_glossary = str(settings.BASE_DIR / "DocuTranslate.csv")
    glossary_default = default_glossary if Path(default_glossary).exists() else ""
    cad_summary = runtime_service.get_cad_defaults_summary()

    resolved_target_language = _prompt_or_default(
        target_language,
        "Default target language",
        "ru",
        non_interactive=non_interactive,
    )
    resolved_translation_mode = _prompt_or_default(
        translation_mode,
        "Default translation mode",
        "add",
        non_interactive=non_interactive,
        choice=click.Choice(["add", "replace"], case_sensitive=False),
    )
    resolved_font_name = _prompt_or_default(
        font_name,
        "Default font name",
        cad_summary.get("font_name") or settings.DEFAULT_FONT_NAME,
        non_interactive=non_interactive,
    )
    resolved_font_size_reduction = _prompt_or_default(
        font_size_reduction,
        "Default font size reduction",
        cad_summary.get("font_size_reduction") or settings.DEFAULT_FONT_SIZE_REDUCTION,
        non_interactive=non_interactive,
        value_type=int,
    )
    resolved_converter_backend = _prompt_or_default(
        converter_backend,
        "Default DWG converter backend",
        settings.DWG_CONVERTER_BACKEND,
        non_interactive=non_interactive,
        choice=click.Choice(["auto", "haochen_com", "autocad_com", "oda"], case_sensitive=False),
    )

    backend_probe: dict[str, Any] = {}
    if not skip_converter_check:
        backend_probe = get_dwg_converter().inspect_backends()

    cad_payload = _build_onboard_cad_payload(
        target_language=str(resolved_target_language).strip(),
        translation_mode=str(resolved_translation_mode).strip().lower(),
        font_name=str(resolved_font_name).strip(),
        font_size_reduction=int(resolved_font_size_reduction),
        converter_backend=str(resolved_converter_backend).strip().lower(),
        default_output_dir=str(cad_summary.get("default_output_dir") or settings.get_output_path()),
    )

    llm_payload: dict[str, Any] | None = None
    llm_save_payload: dict[str, Any] | None = None
    if not skip_llm:
        provider_default = provider or settings.TRANSLATION_PROVIDER
        api_format_default = api_format or settings.LLM_API_FORMAT
        model_default = model or settings.LLM_MODEL
        base_url_default = base_url or settings.LLM_BASE_URL
        api_key_default = api_key or settings.LLM_API_KEY
        system_prompt_mode_default = system_prompt_mode or "cad_specialized"
        custom_system_prompt_default = custom_system_prompt or settings.LLM_CUSTOM_SYSTEM_PROMPT
        glossary_default_value = "" if skip_glossary else (glossary_file or glossary_default)
        reasoning_default = settings.LLM_REASONING_ENABLED if reasoning_enabled is None else reasoning_enabled
        timeout_default = timeout_seconds or settings.LLM_TIMEOUT_SECONDS

        resolved_provider = _prompt_or_default(
            provider_default,
            "LLM provider",
            provider_default,
            non_interactive=non_interactive,
        )
        resolved_api_format = _prompt_or_default(
            api_format_default,
            "LLM API format",
            api_format_default,
            non_interactive=non_interactive,
            choice=click.Choice(["openai_compatible", "anthropic", "google", "ollama", "lmstudio"], case_sensitive=False),
        )
        resolved_model = _prompt_or_default(
            model_default,
            "LLM model",
            model_default,
            non_interactive=non_interactive,
        )
        resolved_base_url = _prompt_or_default(
            base_url_default,
            "LLM base URL",
            base_url_default,
            non_interactive=non_interactive,
        )
        resolved_api_key = _prompt_or_default(
            api_key_default,
            "LLM API key",
            api_key_default,
            non_interactive=non_interactive,
            hide_input=True,
        )
        resolved_system_prompt_mode = _prompt_or_default(
            system_prompt_mode_default,
            "System prompt mode",
            system_prompt_mode_default,
            non_interactive=non_interactive,
            choice=click.Choice(["default", "cad_specialized", "custom"], case_sensitive=False),
        )
        resolved_custom_system_prompt = _prompt_or_default(
            custom_system_prompt_default,
            "Custom system prompt",
            custom_system_prompt_default,
            non_interactive=non_interactive,
        )
        resolved_glossary_file = _prompt_or_default(
            glossary_default_value,
            "Glossary file",
            glossary_default_value,
            non_interactive=non_interactive,
        )
        resolved_reasoning_enabled = _prompt_or_default(
            reasoning_default,
            "Enable reasoning",
            reasoning_default,
            non_interactive=non_interactive,
            value_type=bool,
        )
        resolved_timeout_seconds = _prompt_or_default(
            timeout_default,
            "LLM timeout seconds",
            timeout_default,
            non_interactive=non_interactive,
            value_type=int,
        )

        llm_payload = _build_onboard_llm_payload(
            provider=str(resolved_provider).strip().lower(),
            api_format=str(resolved_api_format).strip().lower(),
            model=str(resolved_model).strip(),
            base_url=str(resolved_base_url).strip().rstrip("/"),
            api_key=str(resolved_api_key).strip(),
            system_prompt_mode=str(resolved_system_prompt_mode).strip().lower(),
            custom_system_prompt=str(resolved_custom_system_prompt).strip(),
            glossary_file="" if skip_glossary else str(resolved_glossary_file).strip(),
            reasoning_enabled=bool(resolved_reasoning_enabled),
            timeout_seconds=int(resolved_timeout_seconds),
        )

        test_result = runtime_service.test_connection(llm_payload)
        if not test_result.get("success"):
            raise ValueError(test_result.get("message") or "LLM connection test failed")
        llm_save_payload = llm_payload

    if scope.lower() == "project":
        project_patch: dict[str, Any] = {"cad": cad_payload}
        if llm_save_payload is not None:
            project_patch["llm"] = {
                "primary": llm_save_payload,
                "system_prompt_mode": llm_save_payload["system_prompt_mode"],
                "custom_system_prompt": llm_save_payload["custom_system_prompt"],
                "glossary_file": llm_save_payload["glossary_file"],
            }
        save_result = runtime_service.update_project_config(project_patch)
    else:
        save_result = runtime_service.update_cad_defaults(cad_payload)
        if llm_save_payload is not None:
            runtime_service.update_runtime_config(llm_save_payload)

    validation = runtime_service.validate_effective_config()
    emit(
        {
            "success": True,
            "scope": scope.lower(),
            "cad": cad_payload,
            "llm": llm_save_payload,
            "detected_backends": backend_probe,
            "validation": validation,
            "save_result": save_result,
        },
        "Onboarding completed",
    )


@cli.group("tasks")
def tasks_group() -> None:
    """Task management commands."""


@tasks_group.command("list")
@handle_error
def tasks_list() -> None:
    emit({"tasks": list_tasks()})


@tasks_group.command("show")
@click.argument("task_id")
@handle_error
def tasks_show(task_id: str) -> None:
    emit(load_task(task_id))


@tasks_group.command("delete")
@click.argument("task_id")
@handle_error
def tasks_delete(task_id: str) -> None:
    delete_task(task_id)
    emit({"success": True, "task_id": task_id}, f"Deleted task {task_id}")


@tasks_group.command("clear")
@handle_error
def tasks_clear() -> None:
    clear_tasks()
    emit({"success": True}, "Cleared all tasks")


@cli.group("config")
def config_group() -> None:
    """Configuration commands."""


@config_group.command("show")
@handle_error
def config_show() -> None:
    session = get_session()
    settings = get_settings()
    converter = get_dwg_converter()
    runtime_service = get_runtime_config_service()
    cad_defaults = get_runtime_config_service().get_cad_defaults_summary()
    effective = runtime_service.get_effective_config_summary()
    emit(
        {
            "project_path": session.project_path,
            "recent_task_id": session.recent_task_id,
            "active_input_file": session.active_input_file,
            "dwg_converter_backend": settings.DWG_CONVERTER_BACKEND,
            "dwg_auto_backends": settings.DWG_AUTO_BACKENDS,
            "dwg_disabled_backends": settings.DWG_DISABLED_BACKENDS,
            "detected_backends": converter.inspect_backends(),
            "target_language": cad_defaults.get("target_language"),
            "translation_mode": cad_defaults.get("translation_mode"),
            "font_name": cad_defaults.get("font_name"),
            "font_size_reduction": cad_defaults.get("font_size_reduction"),
            "default_output_dir": cad_defaults.get("default_output_dir"),
            "config_file": cad_defaults.get("config_file"),
            "global_config": effective.get("paths", {}).get("global_config"),
            "project_config": effective.get("paths", {}).get("project_config"),
            "sources": effective.get("sources", {}),
        }
    )


@config_group.command("get")
@click.argument("config_path", type=str)
@handle_error
def config_get(config_path: str) -> None:
    emit(get_runtime_config_service().get_config_value(config_path))


@config_group.command("set")
@click.argument("config_path", required=False, type=str)
@click.argument("config_value", required=False, type=str)
@click.option("--target-language", type=str, default=None)
@click.option("--translation-mode", type=click.Choice(["add", "replace"], case_sensitive=False), default=None)
@click.option("--font-name", type=str, default=None)
@click.option("--font-size-reduction", type=int, default=None)
@click.option("--default-output-dir", type=click.Path(), default=None)
@click.option("--converter-backend", type=str, default=None)
@handle_error
def config_set(
    config_path: str | None,
    config_value: str | None,
    target_language: str | None,
    translation_mode: str | None,
    font_name: str | None,
    font_size_reduction: int | None,
    default_output_dir: str | None,
    converter_backend: str | None,
) -> None:
    if config_path is not None:
        if any(
            option is not None
            for option in [
                target_language,
                translation_mode,
                font_name,
                font_size_reduction,
                default_output_dir,
                converter_backend,
            ]
        ):
            raise ValueError("Use either path/value arguments or explicit --options, not both.")
        if config_value is None:
            raise ValueError("config value is required when using a config path.")
        emit(
            get_runtime_config_service().set_config_value(config_path, _coerce_config_value(config_value)),
            "Config value saved",
        )
        return

    payload: dict[str, Any] = {}
    if target_language is not None:
        payload["target_language"] = target_language
    if translation_mode is not None:
        payload["translation_mode"] = translation_mode
    if font_name is not None:
        payload["font_name"] = font_name
    if font_size_reduction is not None:
        payload["font_size_reduction"] = font_size_reduction
    if default_output_dir is not None:
        payload["default_output_dir"] = default_output_dir
    if converter_backend is not None:
        payload["converter_backend"] = converter_backend
    if not payload:
        raise ValueError("At least one config option is required.")
    emit(get_runtime_config_service().update_cad_defaults(payload), "CAD runtime defaults saved")


@config_group.command("validate")
@handle_error
def config_validate() -> None:
    emit(get_runtime_config_service().validate_effective_config())


@config_group.group("llm")
def config_llm_group() -> None:
    """LLM runtime setup commands."""


@config_llm_group.command("show")
@handle_error
def config_llm_show() -> None:
    emit(get_runtime_config_service().get_public_runtime_summary())


def _prompt_if_missing(value: str | None, label: str, *, hide_input: bool = False) -> str:
    if value is not None and str(value).strip():
        return str(value).strip()
    return str(click.prompt(label, hide_input=hide_input)).strip()


def _build_llm_payload(
    api_format: str | None,
    provider: str | None,
    model: str | None,
    api_key: str | None,
    base_url: str | None,
    system_prompt_mode: str | None,
    custom_system_prompt: str | None,
    glossary_file: str | None,
    reasoning_enabled: bool | None,
    timeout_seconds: int | None,
    temperature: float | None,
    max_tokens: int | None,
    batch_size: int | None,
    batch_json: bool | None,
    fallback_format: str | None,
    fallback_provider: str | None,
    fallback_model: str | None,
    fallback_api_key: str | None,
    fallback_base_url: str | None,
    fallback_reasoning_enabled: bool | None,
    prompt_for_missing: bool,
) -> dict[str, Any]:
    runtime_service = get_runtime_config_service()
    current = runtime_service.get_public_runtime_summary()
    resolved_format = (api_format or current.get("format") or "openai_compatible").strip().lower()
    resolved_provider = (provider or current.get("provider") or "openrouter").strip().lower()
    resolved_model = model
    resolved_api_key = api_key
    resolved_base_url = base_url
    resolved_system_prompt_mode = (
        system_prompt_mode or current.get("system_prompt_mode") or "default"
    ).strip().lower()
    resolved_custom_system_prompt = custom_system_prompt
    resolved_glossary_file = glossary_file
    resolved_reasoning_enabled = reasoning_enabled

    if prompt_for_missing:
        resolved_format = _prompt_if_missing(resolved_format, "LLM format")
        resolved_provider = _prompt_if_missing(resolved_provider, "LLM provider")
        resolved_model = _prompt_if_missing(resolved_model or current.get("model"), "Model name")
        resolved_base_url = _prompt_if_missing(
            resolved_base_url or current.get("base_url"),
            "Base URL",
        )
        if resolved_format not in {"ollama", "lmstudio"}:
            resolved_api_key = _prompt_if_missing(resolved_api_key, "API key", hide_input=True)
        resolved_system_prompt_mode = _prompt_if_missing(resolved_system_prompt_mode, "System prompt mode")
        if resolved_system_prompt_mode == "custom":
            resolved_custom_system_prompt = _prompt_if_missing(
                resolved_custom_system_prompt or current.get("custom_system_prompt"),
                "Custom system prompt",
            )
    elif resolved_system_prompt_mode == "custom" and not str(resolved_custom_system_prompt or "").strip():
        raise ValueError("custom_system_prompt is required when system_prompt_mode is custom")

    payload: dict[str, Any] = {"format": resolved_format, "provider": resolved_provider}
    if resolved_model:
        payload["model"] = resolved_model
    if resolved_api_key:
        payload["api_key"] = resolved_api_key
    if resolved_base_url:
        payload["base_url"] = resolved_base_url
    if resolved_system_prompt_mode:
        payload["system_prompt_mode"] = resolved_system_prompt_mode
    if resolved_custom_system_prompt:
        payload["custom_system_prompt"] = resolved_custom_system_prompt
    if resolved_glossary_file:
        payload["glossary_file"] = resolved_glossary_file
    if resolved_reasoning_enabled is not None:
        payload["reasoning_enabled"] = resolved_reasoning_enabled
    if timeout_seconds is not None:
        payload["timeout_seconds"] = timeout_seconds
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if batch_size is not None:
        payload["batch_size"] = batch_size
    if batch_json is not None:
        payload["batch_json"] = batch_json
    if any(
        value is not None and str(value).strip()
        for value in (fallback_format, fallback_provider, fallback_model, fallback_api_key, fallback_base_url)
    ) or fallback_reasoning_enabled is not None:
        fallback_entry: dict[str, Any] = {}
        if fallback_format:
            fallback_entry["format"] = fallback_format.strip().lower()
        if fallback_provider:
            fallback_entry["provider"] = fallback_provider.strip().lower()
        if fallback_model:
            fallback_entry["model"] = fallback_model.strip()
        if fallback_api_key:
            fallback_entry["api_key"] = fallback_api_key.strip()
        if fallback_base_url:
            fallback_entry["base_url"] = fallback_base_url.strip()
        if fallback_reasoning_enabled is not None:
            fallback_entry["reasoning_enabled"] = fallback_reasoning_enabled
        if not fallback_entry.get("provider"):
            raise ValueError("fallback_provider is required when fallback model options are provided")
        payload["fallback_models"] = [fallback_entry]
    return payload


@config_llm_group.command("test")
@click.option(
    "--format",
    "api_format",
    type=click.Choice(["openai_compatible", "anthropic", "google", "ollama", "lmstudio"], case_sensitive=False),
    default=None,
)
@click.option("--provider", type=str, default=None)
@click.option("--model", type=str, default=None)
@click.option("--api-key", type=str, default=None)
@click.option("--base-url", type=str, default=None)
@click.option(
    "--system-prompt-mode",
    type=click.Choice(["default", "cad_specialized", "custom"], case_sensitive=False),
    default=None,
)
@click.option("--custom-system-prompt", type=str, default=None)
@click.option("--glossary-file", type=str, default=None)
@click.option("--reasoning-enabled/--no-reasoning-enabled", default=None)
@click.option("--timeout-seconds", type=int, default=None)
@click.option(
    "--fallback-format",
    type=click.Choice(["openai_compatible", "anthropic", "google", "ollama", "lmstudio"], case_sensitive=False),
    default=None,
)
@click.option("--fallback-provider", type=str, default=None)
@click.option("--fallback-model", type=str, default=None)
@click.option("--fallback-api-key", type=str, default=None)
@click.option("--fallback-base-url", type=str, default=None)
@click.option("--fallback-reasoning-enabled/--no-fallback-reasoning-enabled", default=None)
@handle_error
def config_llm_test(
    api_format: str | None,
    provider: str | None,
    model: str | None,
    api_key: str | None,
    base_url: str | None,
    system_prompt_mode: str | None,
    custom_system_prompt: str | None,
    glossary_file: str | None,
    reasoning_enabled: bool | None,
    timeout_seconds: int | None,
    fallback_format: str | None,
    fallback_provider: str | None,
    fallback_model: str | None,
    fallback_api_key: str | None,
    fallback_base_url: str | None,
    fallback_reasoning_enabled: bool | None,
) -> None:
    payload = _build_llm_payload(
        api_format=api_format,
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        system_prompt_mode=system_prompt_mode,
        custom_system_prompt=custom_system_prompt,
        glossary_file=glossary_file,
        reasoning_enabled=reasoning_enabled,
        timeout_seconds=timeout_seconds,
        temperature=None,
        max_tokens=None,
        batch_size=None,
        batch_json=None,
        fallback_format=fallback_format,
        fallback_provider=fallback_provider,
        fallback_model=fallback_model,
        fallback_api_key=fallback_api_key,
        fallback_base_url=fallback_base_url,
        fallback_reasoning_enabled=fallback_reasoning_enabled,
        prompt_for_missing=False,
    )
    emit(get_runtime_config_service().test_connection(payload), "LLM connection test completed")


@config_llm_group.command("init")
@click.option(
    "--format",
    "api_format",
    type=click.Choice(["openai_compatible", "anthropic", "google", "ollama", "lmstudio"], case_sensitive=False),
    default=None,
)
@click.option("--provider", type=str, default=None)
@click.option("--model", type=str, default=None)
@click.option("--api-key", type=str, default=None)
@click.option("--base-url", type=str, default=None)
@click.option(
    "--system-prompt-mode",
    type=click.Choice(["default", "cad_specialized", "custom"], case_sensitive=False),
    default=None,
)
@click.option("--custom-system-prompt", type=str, default=None)
@click.option("--glossary-file", type=str, default=None)
@click.option("--reasoning-enabled/--no-reasoning-enabled", default=None)
@click.option("--timeout-seconds", type=int, default=None)
@click.option("--temperature", type=float, default=None)
@click.option("--max-tokens", type=int, default=None)
@click.option("--batch-size", type=int, default=None)
@click.option("--batch-json/--no-batch-json", default=None)
@click.option(
    "--fallback-format",
    type=click.Choice(["openai_compatible", "anthropic", "google", "ollama", "lmstudio"], case_sensitive=False),
    default=None,
)
@click.option("--fallback-provider", type=str, default=None)
@click.option("--fallback-model", type=str, default=None)
@click.option("--fallback-api-key", type=str, default=None)
@click.option("--fallback-base-url", type=str, default=None)
@click.option("--fallback-reasoning-enabled/--no-fallback-reasoning-enabled", default=None)
@click.option("--non-interactive", is_flag=True, help="Do not prompt for missing values.")
@handle_error
def config_llm_init(
    api_format: str | None,
    provider: str | None,
    model: str | None,
    api_key: str | None,
    base_url: str | None,
    system_prompt_mode: str | None,
    custom_system_prompt: str | None,
    glossary_file: str | None,
    reasoning_enabled: bool | None,
    timeout_seconds: int | None,
    temperature: float | None,
    max_tokens: int | None,
    batch_size: int | None,
    batch_json: bool | None,
    fallback_format: str | None,
    fallback_provider: str | None,
    fallback_model: str | None,
    fallback_api_key: str | None,
    fallback_base_url: str | None,
    fallback_reasoning_enabled: bool | None,
    non_interactive: bool,
) -> None:
    payload = _build_llm_payload(
        api_format=api_format,
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        system_prompt_mode=system_prompt_mode,
        custom_system_prompt=custom_system_prompt,
        glossary_file=glossary_file,
        reasoning_enabled=reasoning_enabled,
        timeout_seconds=timeout_seconds,
        temperature=temperature,
        max_tokens=max_tokens,
        batch_size=batch_size,
        batch_json=batch_json,
        fallback_format=fallback_format,
        fallback_provider=fallback_provider,
        fallback_model=fallback_model,
        fallback_api_key=fallback_api_key,
        fallback_base_url=fallback_base_url,
        fallback_reasoning_enabled=fallback_reasoning_enabled,
        prompt_for_missing=not non_interactive,
    )
    runtime_service = get_runtime_config_service()
    test_result = runtime_service.test_connection(payload)
    if not test_result.get("success"):
        raise ValueError(test_result.get("message") or "LLM connection test failed")
    emit(runtime_service.update_runtime_config(payload), "LLM runtime config saved")


@cli.group("release", hidden=True)
def release_group() -> None:
    """Beginner-friendly local release commands."""


@release_group.command("package-info", help="Show package and release flow details.")
@handle_error
def release_package_info() -> None:
    emit(package_info(), "Local package info")


@release_group.command("build", help="Build local package artifacts.")
@handle_error
def release_build() -> None:
    result = build_distributions()
    emit(result, f"Built package artifacts in {result['dist_dir']}")


@release_group.command("smoke", help="Run beginner-friendly smoke checks.")
@handle_error
def release_smoke() -> None:
    result = run_smoke_checks()
    emit(result, "Smoke checks completed")


@cli.command("repl", help="Enter interactive REPL mode.")
@handle_error
def repl() -> None:
    global _repl_mode
    _repl_mode = True
    from cli.utils.repl_skin import ReplSkin

    skin = ReplSkin("cad", version="1.0.0")
    skin.print_banner()
    skin.help(
        {
            "project new": "Create a lightweight CLI project",
            "files list": "Scan a directory for DWG, DXF, and XLSX files",
            "pipeline extract": "Extract DXF text into Excel",
            "pipeline apply": "Apply translations from Excel back into DXF",
            "tasks list": "List generated tasks",
            "quit": "Exit REPL",
        }
    )
    pt_session = skin.create_prompt_session()
    while True:
        try:
            line = skin.get_input(
                pt_session,
                project_name=(get_session().project_data or {}).get("name", ""),
                modified=get_session().is_modified(),
            )
            if not line:
                continue
            if line.strip().lower() in {"quit", "exit", "q"}:
                break
            if line.strip().lower() == "help":
                skin.help(
                    {
                        "project new": "Create a lightweight CLI project",
                        "files list": "Scan a directory for DWG, DXF, and XLSX files",
                        "pipeline extract": "Extract DXF text into Excel",
                        "pipeline apply": "Apply translations from Excel back into DXF",
                        "tasks list": "List generated tasks",
                        "quit": "Exit REPL",
                    }
                )
                continue
            try:
                cli.main(args=line.split(), prog_name="cad-translate", standalone_mode=False)
            except SystemExit:
                pass
            except click.ClickException as exc:
                skin.error(str(exc))
        except (EOFError, KeyboardInterrupt):
            break
    skin.print_goodbye()
    _repl_mode = False


def main() -> None:
    cli(obj={})


if __name__ == "__main__":
    main()
