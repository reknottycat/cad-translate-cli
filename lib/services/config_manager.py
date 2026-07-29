from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.config import get_settings


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _normalize_legacy_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if "cad" in payload or "llm" in payload or "include" in payload:
        return payload

    cad_keys = {
        "target_language",
        "translation_mode",
        "font_name",
        "font_size_reduction",
        "default_output_dir",
        "converter_backend",
    }
    llm_primary_keys = {
        "provider",
        "format",
        "base_url",
        "api_key",
        "model",
        "timeout_seconds",
        "temperature",
        "max_tokens",
        "reasoning_enabled",
    }
    llm_keys = {
        "system_prompt_mode",
        "custom_system_prompt",
        "glossary_file",
        "batch_size",
        "batch_json",
        "parallel_count",
        "retry_count",
        "rpm",
        "tpm",
        "extra_body",
        "use_system_proxy",
        "fallback_models",
    }

    normalized: dict[str, Any] = {}
    cad = {key: payload[key] for key in cad_keys if key in payload}
    llm_primary = {key: payload[key] for key in llm_primary_keys if key in payload}
    llm = {key: payload[key] for key in llm_keys if key in payload}
    if llm_primary:
        llm["primary"] = llm_primary
    if cad:
        normalized["cad"] = cad
    if llm:
        normalized["llm"] = llm
    return normalized or payload


def _flatten_leaf_paths(payload: dict[str, Any], prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in payload.items():
        if key == "include":
            continue
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(_flatten_leaf_paths(value, path))
        else:
            flat[path] = path
    return flat


def _nested_from_path(path: str, value: Any) -> dict[str, Any]:
    parts = [segment for segment in path.split(".") if segment]
    if not parts:
        return {}
    payload: dict[str, Any] = value
    for segment in reversed(parts):
        payload = {segment: payload}
    return payload


def _parse_bool(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class LLMEndpointConfig(BaseModel):
    provider: str = "custom"
    format: str = "openai_compatible"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    timeout_seconds: int = 300
    temperature: float = 0.1
    max_tokens: int = 16384
    reasoning_enabled: bool = False


class CADConfig(BaseModel):
    target_language: str = "en"
    translation_mode: str = "add"
    font_name: str = "Times New Roman"
    font_size_reduction: int = 4
    default_output_dir: str = ""
    converter_backend: str = "auto"

    @field_validator("translation_mode")
    @classmethod
    def validate_translation_mode(cls, value: str) -> str:
        normalized = str(value).strip().lower()
        if normalized not in {"add", "replace"}:
            raise ValueError("translation_mode must be add or replace")
        return normalized

    @field_validator("font_size_reduction")
    @classmethod
    def validate_font_size_reduction(cls, value: int) -> int:
        if int(value) < 0:
            raise ValueError("font_size_reduction must be >= 0")
        return int(value)


class LLMConfig(BaseModel):
    primary: LLMEndpointConfig = Field(default_factory=LLMEndpointConfig)
    fallback_models: list[LLMEndpointConfig] = Field(default_factory=list)
    system_prompt: str = ""
    system_prompt_mode: str = "default"
    custom_system_prompt: str = ""
    glossary_file: str = ""
    batch_size: int = 12
    batch_json: bool = True
    parallel_count: int = 1
    retry_count: int = 2
    rpm: int = 40
    tpm: str = ""
    extra_body: str = ""
    use_system_proxy: bool = False
    allow_demo_fallback: bool = False
    provider_api_keys: dict[str, str] = Field(default_factory=dict)

    @field_validator("system_prompt_mode")
    @classmethod
    def validate_system_prompt_mode(cls, value: str) -> str:
        normalized = str(value).strip().lower()
        if normalized not in {"default", "cad_specialized", "custom"}:
            raise ValueError("system_prompt_mode must be default, cad_specialized, or custom")
        return normalized


class UnifiedConfig(BaseModel):
    include: list[str] = Field(default_factory=list)
    cad: CADConfig = Field(default_factory=CADConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)


@dataclass(frozen=True)
class ConfigPaths:
    global_config: Path
    project_config: Path


class ConfigManager:
    def __init__(self, cli_overrides: dict[str, Any] | None = None, cwd: Path | None = None) -> None:
        self.settings = get_settings()
        self.cwd = Path(cwd) if cwd is not None else Path.cwd()
        self.paths = ConfigPaths(
            global_config=self.settings.get_runtime_config_path(),
            project_config=self.cwd / ".cli-anything-cadrc",
        )
        self.cli_overrides = cli_overrides or {}

    def _defaults(self) -> dict[str, Any]:
        setting_defaults = type(self.settings).model_fields
        return {
            "cad": {
                "target_language": self.settings.DEFAULT_TARGET_LANGUAGE,
                "translation_mode": self.settings.DEFAULT_TRANSLATION_MODE,
                "font_name": self.settings.DEFAULT_FONT_NAME,
                "font_size_reduction": self.settings.DEFAULT_FONT_SIZE_REDUCTION,
                "default_output_dir": str(self.settings.get_output_path()),
                "converter_backend": self.settings.DWG_CONVERTER_BACKEND,
            },
            "llm": {
                "primary": {
                    "provider": setting_defaults["TRANSLATION_PROVIDER"].default,
                    "format": setting_defaults["LLM_API_FORMAT"].default,
                    "base_url": setting_defaults["LLM_BASE_URL"].default,
                    "api_key": setting_defaults["LLM_API_KEY"].default,
                    "model": setting_defaults["LLM_MODEL"].default,
                    "timeout_seconds": setting_defaults["LLM_TIMEOUT_SECONDS"].default,
                    "temperature": setting_defaults["LLM_TEMPERATURE"].default,
                    "max_tokens": setting_defaults["LLM_MAX_TOKENS"].default,
                    "reasoning_enabled": setting_defaults["LLM_REASONING_ENABLED"].default,
                },
                "fallback_models": [],
                "system_prompt_mode": setting_defaults["LLM_SYSTEM_PROMPT_MODE"].default,
                "custom_system_prompt": setting_defaults["LLM_CUSTOM_SYSTEM_PROMPT"].default,
                "glossary_file": setting_defaults["LLM_GLOSSARY_FILE"].default,
                "batch_size": setting_defaults["LLM_BATCH_SIZE"].default,
                "batch_json": setting_defaults["LLM_ENABLE_BATCH_JSON"].default,
                "parallel_count": setting_defaults["LLM_PARALLEL_COUNT"].default,
                "retry_count": setting_defaults["LLM_RETRY_COUNT"].default,
                "rpm": setting_defaults["LLM_RPM"].default,
                "tpm": setting_defaults["LLM_TPM"].default,
                "extra_body": setting_defaults["LLM_EXTRA_BODY"].default,
                "use_system_proxy": setting_defaults["LLM_USE_SYSTEM_PROXY"].default,
            },
        }

    def _resolve_include_path(self, ref: str, base_path: Path) -> Path:
        include_path = Path(ref)
        if include_path.is_absolute():
            return include_path
        return (base_path.parent / include_path).resolve()

    def _load_file_with_includes(self, path: Path, seen: set[Path] | None = None) -> dict[str, Any]:
        seen = seen or set()
        resolved = path.resolve()
        if resolved in seen:
            raise ValueError(f"Cyclic config include detected at {resolved}")
        seen.add(resolved)

        payload = _normalize_legacy_payload(_read_json_file(path))
        includes = payload.get("include") or []
        merged: dict[str, Any] = {}
        for ref in includes:
            include_path = self._resolve_include_path(str(ref), path)
            merged = _deep_merge(merged, self._load_file_with_includes(include_path, seen.copy()))

        payload = {key: value for key, value in payload.items() if key != "include"}
        return _deep_merge(merged, payload)

    def _env_overrides(self) -> dict[str, Any]:
        mapping: list[tuple[str, str, Any]] = [
            ("CAD_TRANSLATION_TARGET_LANGUAGE", "cad.target_language", str),
            ("CAD_TRANSLATION_TRANSLATION_MODE", "cad.translation_mode", str),
            ("CAD_TRANSLATION_FONT_NAME", "cad.font_name", str),
            ("CAD_TRANSLATION_FONT_SIZE_REDUCTION", "cad.font_size_reduction", int),
            ("CAD_TRANSLATION_DEFAULT_OUTPUT_DIR", "cad.default_output_dir", str),
            ("CAD_TRANSLATION_CONVERTER_BACKEND", "cad.converter_backend", str),
        ]
        merged: dict[str, Any] = {}
        for env_name, path, caster in mapping:
            raw = os.getenv(env_name)
            if raw is None or raw == "":
                continue
            merged = _deep_merge(merged, _nested_from_path(path, caster(raw)))
        return merged

    def _layers(self) -> list[tuple[str, dict[str, Any]]]:
        global_payload = self._load_file_with_includes(self.paths.global_config)
        project_payload = self._load_file_with_includes(self.paths.project_config)
        env_payload = self._env_overrides()
        return [
            ("defaults", self._defaults()),
            ("global", global_payload),
            ("project", project_payload),
            ("env", env_payload),
            ("cli", self.cli_overrides),
        ]

    def get_effective_model(self) -> UnifiedConfig:
        merged: dict[str, Any] = {}
        for _, layer in self._layers():
            merged = _deep_merge(merged, layer)
        try:
            return UnifiedConfig.model_validate(merged)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc

    def get_effective_config(self) -> dict[str, Any]:
        return self.get_effective_model().model_dump()

    def get_source_map(self) -> dict[str, str]:
        sources: dict[str, str] = {}
        for name, layer in self._layers():
            for path in _flatten_leaf_paths(layer):
                sources[path] = name
        return sources

    def get_effective_config_summary(self) -> dict[str, Any]:
        return {
            **self.get_effective_config(),
            "paths": {
                "global_config": str(self.paths.global_config),
                "project_config": str(self.paths.project_config),
            },
            "sources": self.get_source_map(),
        }

    def validate_effective_config(self) -> dict[str, Any]:
        try:
            self.get_effective_model()
        except ValueError as exc:
            return {
                "success": False,
                "valid": False,
                "errors": [str(exc)],
                "config_file": str(self.paths.global_config),
            }
        return {
            "success": True,
            "valid": True,
            "errors": [],
            "config_file": str(self.paths.global_config),
        }

    def get_path_value(self, path: str) -> Any:
        current: Any = self.get_effective_config()
        for segment in [part for part in path.split(".") if part]:
            if not isinstance(current, dict) or segment not in current:
                raise KeyError(path)
            current = current[segment]
        return current

    def update_global_config(self, patch: dict[str, Any]) -> dict[str, Any]:
        current = self._load_file_with_includes(self.paths.global_config)
        merged = _deep_merge(current, patch)
        model = UnifiedConfig.model_validate(merged)
        rendered = model.model_dump(exclude_none=True)
        self.paths.global_config.parent.mkdir(parents=True, exist_ok=True)
        self.paths.global_config.write_text(
            f"{json.dumps(rendered, ensure_ascii=False, indent=2)}\n",
            encoding="utf-8",
        )
        return rendered

    def update_project_config(self, patch: dict[str, Any]) -> dict[str, Any]:
        current = self._load_file_with_includes(self.paths.project_config)
        merged = _deep_merge(current, patch)
        model = UnifiedConfig.model_validate(merged)
        rendered = model.model_dump(exclude_none=True)
        self.paths.project_config.parent.mkdir(parents=True, exist_ok=True)
        self.paths.project_config.write_text(
            f"{json.dumps(rendered, ensure_ascii=False, indent=2)}\n",
            encoding="utf-8",
        )
        return rendered

    def set_global_path_value(self, path: str, value: Any) -> dict[str, Any]:
        patch = _nested_from_path(path, value)
        if not patch:
            raise ValueError("config path is required")
        return self.update_global_config(patch)

    def set_project_path_value(self, path: str, value: Any) -> dict[str, Any]:
        patch = _nested_from_path(path, value)
        if not patch:
            raise ValueError("config path is required")
        return self.update_project_config(patch)
