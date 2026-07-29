#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified LLM translation services."""

from __future__ import annotations

import json
import os
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd
import requests
import structlog

from app.config import get_settings, load_runtime_config
from app.services.config_manager import ConfigManager

logger = structlog.get_logger(__name__)

CAD_SPECIALIZED_SYSTEM_PROMPT = (
    "You are a professional CAD drawing translation specialist. "
    "Preserve engineering meaning, drawing codes, units, tag numbers, and punctuation. "
    "Use concise domain terminology, keep repeated labels consistent, and output translated text only."
)


@dataclass(frozen=True)
class ProviderPreset:
    id: str
    name: str
    api_format: str
    base_url: str
    default_model: str
    api_key_env: str
    notes: str
    free_tier_hint: bool = False


PROVIDER_PRESETS: Dict[str, ProviderPreset] = {
    "openai": ProviderPreset(
        id="openai",
        name="OpenAI",
        api_format="openai_compatible",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4.1-mini",
        api_key_env="OPENAI_API_KEY",
        notes="Official OpenAI endpoint",
    ),
    "openrouter": ProviderPreset(
        id="openrouter",
        name="OpenRouter",
        api_format="openai_compatible",
        base_url="https://openrouter.ai/api/v1",
        default_model="stepfun/step-3.5-flash:free",
        api_key_env="OPENROUTER_API_KEY",
        notes="Multi-vendor gateway, often has free/community models",
        free_tier_hint=True,
    ),
    "nvidia": ProviderPreset(
        id="nvidia",
        name="NVIDIA API Catalog",
        api_format="openai_compatible",
        base_url="https://integrate.api.nvidia.com/v1",
        default_model="moonshotai/kimi-k2.5",
        api_key_env="NVIDIA_API_KEY",
        notes="Direct NVIDIA chat completions endpoint",
    ),
    "dashscope": ProviderPreset(
        id="dashscope",
        name="Alibaba DashScope",
        api_format="openai_compatible",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="qwen-max",
        api_key_env="LLM_API_KEY",
        notes="Qwen models via OpenAI-compatible endpoint",
    ),
    "deepseek": ProviderPreset(
        id="deepseek",
        name="DeepSeek",
        api_format="openai_compatible",
        base_url="https://api.deepseek.com/v1",
        default_model="deepseek-chat",
        api_key_env="DEEPSEEK_API_KEY",
        notes="DeepSeek official endpoint",
    ),
    "groq": ProviderPreset(
        id="groq",
        name="Groq",
        api_format="openai_compatible",
        base_url="https://api.groq.com/openai/v1",
        default_model="llama-3.3-70b-versatile",
        api_key_env="GROQ_API_KEY",
        notes="High-speed inference, some free tier quotas",
        free_tier_hint=True,
    ),
    "minimax": ProviderPreset(
        id="minimax",
        name="MiniMax",
        api_format="openai_compatible",
        base_url="https://api.minimax.chat/v1",
        default_model="MiniMax-Text-01",
        api_key_env="MINIMAX_API_KEY",
        notes="MiniMax open platform",
    ),
    "minimax-cn": ProviderPreset(
        id="minimax-cn",
        name="MiniMax 国内版",
        api_format="openai_compatible",
        base_url="https://api.minimaxi.com/v1",
        default_model="MiniMax-M2.5",
        api_key_env="MINIMAX_API_KEY",
        notes="MiniMax 中国国内官方端点",
    ),
    "zhipu": ProviderPreset(
        id="zhipu",
        name="Zhipu GLM",
        api_format="openai_compatible",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        default_model="glm-4-plus",
        api_key_env="ZHIPU_API_KEY",
        notes="GLM models",
    ),
    "moonshot": ProviderPreset(
        id="moonshot",
        name="Moonshot",
        api_format="openai_compatible",
        base_url="https://api.moonshot.cn/v1",
        default_model="moonshot-v1-8k",
        api_key_env="MOONSHOT_API_KEY",
        notes="Kimi models",
    ),
    "siliconflow": ProviderPreset(
        id="siliconflow",
        name="SiliconFlow",
        api_format="openai_compatible",
        base_url="https://api.siliconflow.cn/v1",
        default_model="Qwen/Qwen2.5-7B-Instruct",
        api_key_env="SILICONFLOW_API_KEY",
        notes="Open-model hosting platform, often low/free trial credits",
        free_tier_hint=True,
    ),
    "together": ProviderPreset(
        id="together",
        name="Together AI",
        api_format="openai_compatible",
        base_url="https://api.together.xyz/v1",
        default_model="meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
        api_key_env="TOGETHER_API_KEY",
        notes="Open-model inference provider",
    ),
    "anthropic": ProviderPreset(
        id="anthropic",
        name="Anthropic",
        api_format="anthropic",
        base_url="https://api.anthropic.com/v1",
        default_model="claude-3-5-haiku-latest",
        api_key_env="ANTHROPIC_API_KEY",
        notes="Claude Messages API",
    ),
    "google": ProviderPreset(
        id="google",
        name="Google Gemini",
        api_format="google",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        default_model="gemini-2.0-flash",
        api_key_env="GOOGLE_API_KEY",
        notes="Gemini API / AI Studio",
    ),
    "ollama": ProviderPreset(
        id="ollama",
        name="Ollama",
        api_format="ollama",
        base_url="http://127.0.0.1:11434",
        default_model="qwen2.5:7b",
        api_key_env="OLLAMA_API_KEY",
        notes="Local Ollama server",
        free_tier_hint=True,
    ),
    "lmstudio": ProviderPreset(
        id="lmstudio",
        name="LM Studio",
        api_format="lmstudio",
        base_url="http://127.0.0.1:1234/v1",
        default_model="local-model",
        api_key_env="LMSTUDIO_API_KEY",
        notes="Local LM Studio OpenAI-compatible server",
        free_tier_hint=True,
    ),
    "custom": ProviderPreset(
        id="custom",
        name="Custom OpenAI-Compatible",
        api_format="openai_compatible",
        base_url="https://your-endpoint/v1",
        default_model="your-model",
        api_key_env="LLM_API_KEY",
        notes="Bring your own OpenAI-compatible endpoint",
    ),
}


def load_custom_providers() -> None:
    settings = get_settings()
    custom_providers_path = settings.get_runtime_config_path().parent / "custom_providers.json"
    if custom_providers_path.exists():
        try:
            customs = json.loads(custom_providers_path.read_text(encoding="utf-8"))
            for cid, cdata in customs.items():
                PROVIDER_PRESETS[cid] = ProviderPreset(
                    id=cid,
                    name=cdata.get("name", cid),
                    api_format=cdata.get("api_format", "openai_compatible"),
                    base_url=cdata.get("base_url", ""),
                    default_model=cdata.get("default_model", ""),
                    api_key_env="LLM_API_KEY",
                    notes=cdata.get("notes", "Custom provider"),
                    free_tier_hint=False,
                )
        except Exception as exc:
            logger.error("failed_to_load_custom_providers", error=str(exc))


def save_custom_providers() -> None:
    settings = get_settings()
    custom_providers_path = settings.get_runtime_config_path().parent / "custom_providers.json"
    customs = {}
    
    # We define any preset that lacks an explicit api_key_env different than LLM_API_KEY
    # and isn't 'custom' or the built-ins as a custom one. To be safer, we explicitly check
    # if it's not a known static preset.
    static_ids = {
        "openai",
        "openrouter",
        "nvidia",
        "dashscope",
        "deepseek",
        "groq",
        "minimax",
        "minimax-cn",
        "zhipu",
        "moonshot",
        "siliconflow",
        "together",
        "anthropic",
        "google",
        "ollama",
        "lmstudio",
        "custom",
    }
    
    for p_id, p in PROVIDER_PRESETS.items():
        if p_id not in static_ids:
            customs[p_id] = {
                "name": p.name,
                "api_format": p.api_format,
                "base_url": p.base_url,
                "default_model": p.default_model,
                "notes": p.notes,
            }
            
    try:
        custom_providers_path.write_text(json.dumps(customs, indent=2, ensure_ascii=False))
    except Exception as exc:
        logger.error("failed_to_save_custom_providers", error=str(exc))


load_custom_providers()

def list_provider_presets() -> List[Dict[str, Any]]:
    return [
        {
            "id": p.id,
            "name": p.name,
            "base_url": p.base_url,
            "api_format": p.api_format,
            "default_model": p.default_model,
            "api_key_env": p.api_key_env,
            "notes": p.notes,
            "free_tier_hint": p.free_tier_hint,
        }
        for p in PROVIDER_PRESETS.values()
    ]


def add_custom_provider(provider_id: str, name: str, base_url: str, default_model: str, notes: str) -> None:
    sanitized_id = provider_id.strip().lower()
    PROVIDER_PRESETS[sanitized_id] = ProviderPreset(
        id=sanitized_id,
        name=name,
        api_format="openai_compatible",
        base_url=base_url,
        default_model=default_model,
        api_key_env="LLM_API_KEY",
        notes=notes,
        free_tier_hint=False,
    )
    save_custom_providers()


def delete_custom_provider(provider_id: str) -> bool:
    sanitized_id = provider_id.strip().lower()
    static_ids = {
        "openai",
        "openrouter",
        "nvidia",
        "dashscope",
        "deepseek",
        "groq",
        "minimax",
        "minimax-cn",
        "zhipu",
        "moonshot",
        "siliconflow",
        "together",
        "anthropic",
        "google",
        "ollama",
        "lmstudio",
        "custom",
    }
    if sanitized_id in static_ids:
        return False
        
    if sanitized_id in PROVIDER_PRESETS:
        del PROVIDER_PRESETS[sanitized_id]
        save_custom_providers()
        return True
    return False


class LLMTranslationService:
    def __init__(self):
        self.settings = get_settings()
        # Cache provider probes (reachability checks) so we don't spam /models.
        self._probe_cache: Dict[Tuple[str, str, str], Tuple[float, Dict[str, Any]]] = {}
        self._probe_ttl_seconds = 300

    @staticmethod
    def _is_translatable_text(text: str) -> bool:
        stripped = (text or "").strip()
        if not stripped:
            return False
        if re.fullmatch(r"\d+(?:[.,:/-]\d+)*", stripped):
            return False
        if re.fullmatch(r"[^\w\u4e00-\u9fff]+", stripped, flags=re.UNICODE):
            return False
        return True

    def count_translatable_texts(self, texts: List[str]) -> int:
        return sum(1 for text in texts if self._is_translatable_text(text))

    def _resolve_api_key(self, provider: str, raw_api_key: str, provider_api_keys: dict[str, str] | None = None) -> tuple[str, str]:
        """Resolve API key with precedence:

        1) Explicit key in config payload (raw_api_key)
        2) Provider-specific key from provider_api_keys dict
        3) Provider-specific environment variable (e.g. OPENROUTER_API_KEY)
        4) Generic LLM_API_KEY / settings fallback (mainly for custom gateways)
        """
        api_key = (raw_api_key or "").strip()
        if api_key:
            return api_key, "config"

        # Check provider-specific keys from config file
        if provider_api_keys:
            provider_key = str(provider_api_keys.get(provider) or "").strip()
            if provider_key:
                return provider_key, "config"

        preset = PROVIDER_PRESETS.get(provider)
        env_keys: list[str] = []
        if preset is not None and preset.api_key_env:
            env_keys.append(preset.api_key_env)
        if "LLM_API_KEY" not in env_keys:
            env_keys.append("LLM_API_KEY")

        for env_key in env_keys:
            candidate = (os.environ.get(env_key) or "").strip()
            if candidate:
                return candidate, "env"
            # Fallback to settings attributes (from .env file) when present.
            settings_value = (getattr(self.settings, env_key, "") or "").strip()
            if settings_value:
                return settings_value, "settings"

        # Final fallback: the generic settings key.
        candidate = (getattr(self.settings, "LLM_API_KEY", "") or "").strip()
        if candidate:
            return candidate, "settings"
        return "", "none"

    def _setting_default(self, field_name: str) -> Any:
        # Return the actual value from settings (which reflects .env / environment),
        # falling back to the Pydantic field default only if the attribute is missing.
        return getattr(
            self.settings,
            field_name,
            type(self.settings).model_fields[field_name].default,
        )

    def _retry_delay_seconds(self, attempt: int) -> float:
        return min(1.5, 0.4 * attempt)

    def _should_retry_http_status(self, status_code: int) -> bool:
        return status_code == 429 or status_code >= 500

    def _extract_message_content(self, data: Dict[str, Any]) -> str:
        choices = data.get("choices") or []
        if not choices:
            raise ValueError("LLM response did not include choices")

        message = choices[0].get("message") or {}
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("LLM response did not include text content")
        return content.strip()

    def _resolve_default_glossary(self, configured_glossary: str) -> tuple[str, bool]:
        glossary_path = configured_glossary
        default_glossary_used = False
        if not glossary_path:
            for candidate_name in ("DocuTranslate.csv", "DocuTranslate.xlsx", "DocuTranslate.xls"):
                candidate = self.settings.BASE_DIR / candidate_name
                if candidate.exists():
                    glossary_path = str(candidate)
                    default_glossary_used = True
                    break
        return glossary_path, default_glossary_used

    def _resolve_candidate_config(self, raw: Dict[str, Any], provider_api_keys: dict[str, str] | None = None) -> Dict[str, Any]:
        provider = str(raw.get("provider") or self._setting_default("TRANSLATION_PROVIDER") or "custom").strip().lower()
        if provider == "openai_compatible":
            provider = "custom"
        preset = PROVIDER_PRESETS.get(provider)
        api_format = str(
            raw.get("format") or (preset.api_format if preset else self._setting_default("LLM_API_FORMAT") or "openai_compatible")
        ).strip().lower()
        base_url = str(raw.get("base_url") or self._setting_default("LLM_BASE_URL")).strip().rstrip("/")
        model = str(raw.get("model") or self._setting_default("LLM_MODEL")).strip()
        api_key, api_key_source = self._resolve_api_key(provider, str(raw.get("api_key") or ""), provider_api_keys)

        if preset is not None:
            base_url = base_url or preset.base_url
            model = model or preset.default_model
            api_format = api_format or preset.api_format

        return {
            "provider": provider,
            "format": api_format,
            "base_url": base_url,
            "model": model,
            "api_key": api_key,
            "api_key_source": api_key_source,
            "timeout": int(raw.get("timeout") or raw.get("timeout_seconds") or self._setting_default("LLM_TIMEOUT_SECONDS")),
            "temperature": float(raw.get("temperature") or self._setting_default("LLM_TEMPERATURE")),
            "max_tokens": int(raw.get("max_tokens") or self._setting_default("LLM_MAX_TOKENS")),
            "reasoning_enabled": bool(raw.get("reasoning_enabled", self._setting_default("LLM_REASONING_ENABLED"))),
        }

    def _active_config(self) -> Dict[str, Any]:
        file_runtime = ConfigManager().get_effective_config().get("llm", {})
        provider_api_keys = file_runtime.get("provider_api_keys") if isinstance(file_runtime, dict) else None
        primary = self._resolve_candidate_config(file_runtime.get("primary") or {}, provider_api_keys)
        configured_glossary = str(file_runtime.get("glossary_file") or self._setting_default("LLM_GLOSSARY_FILE") or "").strip()
        glossary_path, default_glossary_used = self._resolve_default_glossary(configured_glossary)
        fallback_models = [
            self._resolve_candidate_config(entry)
            for entry in (file_runtime.get("fallback_models") or [])
            if isinstance(entry, dict)
        ]

        primary.update(
            {
                "system_prompt": str(file_runtime.get("system_prompt") or self._setting_default("LLM_SYSTEM_PROMPT") or "").strip(),
                "system_prompt_mode": str(file_runtime.get("system_prompt_mode") or self._setting_default("LLM_SYSTEM_PROMPT_MODE") or "default").strip().lower(),
                "custom_system_prompt": str(file_runtime.get("custom_system_prompt") or self._setting_default("LLM_CUSTOM_SYSTEM_PROMPT") or "").strip(),
                "glossary_file": glossary_path,
                "default_glossary_used": default_glossary_used,
                "batch_size": int(file_runtime.get("batch_size") or self._setting_default("LLM_BATCH_SIZE")),
                "batch_json": bool(file_runtime.get("batch_json", self._setting_default("LLM_ENABLE_BATCH_JSON"))),
                "parallel_count": int(file_runtime.get("parallel_count") or self._setting_default("LLM_PARALLEL_COUNT")),
                "retry_count": int(file_runtime.get("retry_count") or self._setting_default("LLM_RETRY_COUNT")),
                "rpm": int(file_runtime.get("rpm") or self._setting_default("LLM_RPM")),
                "tpm": str(file_runtime.get("tpm") or self._setting_default("LLM_TPM") or "").strip(),
                "extra_body": str(file_runtime.get("extra_body") or self._setting_default("LLM_EXTRA_BODY") or "").strip(),
                "use_system_proxy": bool(file_runtime.get("use_system_proxy", self._setting_default("LLM_USE_SYSTEM_PROXY"))),
                "allow_demo_fallback": bool(file_runtime.get("allow_demo_fallback", self._setting_default("LLM_ALLOW_DEMO_FALLBACK"))),
                "fallback_models": fallback_models,
            }
        )
        return primary

    def get_runtime_summary(self) -> Dict[str, Any]:
        cfg = self._active_config()
        glossary_path = Path(cfg["glossary_file"]) if cfg["glossary_file"] else None
        if glossary_path and not glossary_path.is_absolute():
            glossary_path = (self.settings.BASE_DIR / glossary_path).resolve()
        fallback_models = [
            {
                "provider": fallback["provider"],
                "format": fallback["format"],
                "base_url": fallback["base_url"],
                "model": fallback["model"],
                "api_key_configured": bool(fallback["api_key"]),
                "reasoning_enabled": fallback.get("reasoning_enabled", False),
            }
            for fallback in cfg.get("fallback_models", [])
        ]
        return {
            "provider": cfg["provider"],
            "format": cfg["format"],
            "base_url": cfg["base_url"],
            "model": cfg["model"],
            "api_key_configured": bool(cfg["api_key"]),
            "api_key_source": cfg.get("api_key_source", "none"),
            "system_prompt_mode": cfg["system_prompt_mode"],
            "custom_system_prompt": cfg["custom_system_prompt"],
            "custom_system_prompt_configured": bool(cfg["custom_system_prompt"]),
            "glossary_file": str(glossary_path) if glossary_path else cfg["glossary_file"],
            "glossary_configured": bool(glossary_path) and glossary_path.exists(),
            "default_glossary_used": cfg["default_glossary_used"],
            "reasoning_enabled": cfg["reasoning_enabled"],
            "timeout_seconds": cfg["timeout"],
            "temperature": cfg["temperature"],
            "max_tokens": cfg["max_tokens"],
            "batch_size": cfg["batch_size"],
            "batch_json": cfg["batch_json"],
            "parallel_count": cfg["parallel_count"],
            "retry_count": cfg["retry_count"],
            "rpm": cfg["rpm"],
            "tpm": cfg["tpm"],
            "extra_body": cfg["extra_body"],
            "use_system_proxy": cfg["use_system_proxy"],
            "fallback_count": len(fallback_models),
            "fallback_models": fallback_models,
        }

    def _load_glossary_records(self, glossary_file: str | None) -> List[tuple[str, str]]:
        if not glossary_file:
            return []

        glossary_path = Path(glossary_file)
        if not glossary_path.is_absolute():
            glossary_path = (self.settings.BASE_DIR / glossary_path).resolve()
        if not glossary_path.exists():
            return []

        if glossary_path.suffix.lower() == ".csv":
            df = None
            last_error: Exception | None = None
            for encoding in ("utf-8", "utf-8-sig", "gb18030", "gbk"):
                try:
                    df = pd.read_csv(glossary_path, dtype=str, encoding=encoding).fillna("")
                    break
                except UnicodeDecodeError as exc:
                    last_error = exc
            if df is None:
                if last_error is not None:
                    raise last_error
                return []
        elif glossary_path.suffix.lower() in {".xlsx", ".xls"}:
            df = pd.read_excel(glossary_path, dtype=str).fillna("")
        else:
            return []

        if df.empty or len(df.columns) < 2:
            return []

        first_col = df.columns[0]
        second_col = df.columns[1]
        records: List[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for _, row in df.iterrows():
            source = str(row.get(first_col, "") or "").strip()
            target = str(row.get(second_col, "") or "").strip()
            if not source or not target:
                continue
            pair = (source, target)
            if pair in seen:
                continue
            seen.add(pair)
            records.append(pair)
        return records

    def _select_glossary_records(self, records: List[tuple[str, str]], texts: List[str], limit: int = 30) -> List[tuple[str, str]]:
        if not records:
            return []

        haystack = "\n".join(texts).casefold()
        if not haystack.strip():
            return records[:limit]

        matched = [pair for pair in records if pair[0].casefold() in haystack]
        if matched:
            return matched[:limit]
        return records[: min(limit, 12)]

    def _format_glossary_block(self, records: List[tuple[str, str]]) -> str:
        return "\n".join(f"- {source} => {target}" for source, target in records)

    def _infer_terminology_preferences(self, texts: List[str], source_lang: str, target_lang: str) -> str:
        samples = [text.strip() for text in texts if text and text.strip()][:30]
        if len(samples) < 2:
            return ""

        try:
            return self._chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "You analyze CAD labels and infer likely translation terminology preferences. "
                            "Return only short practical guidance, at most 4 bullet points."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Based on these sample CAD labels from {source_lang} to {target_lang}, "
                            "infer likely terminology preferences that should stay consistent:\n\n"
                            + "\n".join(samples)
                        ),
                    },
                ]
            ).strip()
        except Exception as exc:
            logger.warning("terminology_inference_failed", error=str(exc))
            return ""

    def _compose_system_prompt(
        self,
        texts: List[str],
        source_lang: str,
        target_lang: str,
        *,
        enable_inference: bool,
    ) -> str:
        cfg = self._active_config()
        mode = cfg["system_prompt_mode"]
        if mode == "custom" and cfg["custom_system_prompt"]:
            base_prompt = cfg["custom_system_prompt"]
        elif mode == "cad_specialized":
            base_prompt = CAD_SPECIALIZED_SYSTEM_PROMPT
        else:
            base_prompt = cfg["system_prompt"]

        sections = [base_prompt]

        glossary_records = self._load_glossary_records(cfg["glossary_file"])
        selected_records = self._select_glossary_records(glossary_records, texts)
        if selected_records:
            sections.append(
                "Preferred glossary terms. When applicable, these terms take priority:\n"
                + self._format_glossary_block(selected_records)
            )

        if enable_inference and mode == "default":
            inferred_preferences = self._infer_terminology_preferences(texts, source_lang, target_lang)
            if inferred_preferences:
                sections.append(
                    "Likely terminology preferences inferred from the current task:\n"
                    + inferred_preferences
                )

        return "\n\n".join(section.strip() for section in sections if section and section.strip())

    def _chat_openai_compatible(self, cfg: Dict[str, Any], messages: List[Dict[str, str]]) -> str:
        endpoint = f"{cfg['base_url']}/chat/completions"
        payload = {
            "model": cfg["model"],
            "messages": messages,
            "temperature": cfg["temperature"],
            "max_tokens": cfg["max_tokens"],
        }
        if cfg["provider"] == "nvidia" and cfg.get("reasoning_enabled"):
            payload["chat_template_kwargs"] = {"thinking": True}
        elif cfg.get("reasoning_enabled"):
            payload["reasoning"] = {"enabled": True}
        headers = {
            "Authorization": f"Bearer {cfg['api_key']}",
            "Content-Type": "application/json",
        }
        if cfg["provider"] == "openrouter":
            headers["X-Title"] = self.settings.APP_NAME
        response = requests.post(endpoint, headers=headers, json=payload, timeout=cfg["timeout"])
        if response.status_code != 200:
            raise ValueError(f"LLM request failed: {response.status_code} {response.text[:300]}")
        return self._extract_message_content(response.json())

    def _chat_anthropic(self, cfg: Dict[str, Any], messages: List[Dict[str, str]]) -> str:
        system_messages = [message["content"] for message in messages if message.get("role") == "system"]
        user_messages = [
            {
                "role": "assistant" if message.get("role") == "assistant" else "user",
                "content": message.get("content", ""),
            }
            for message in messages
            if message.get("role") != "system"
        ]
        response = requests.post(
            f"{cfg['base_url']}/messages",
            headers={
                "x-api-key": cfg["api_key"],
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": cfg["model"],
                "system": "\n\n".join(system_messages).strip(),
                "messages": user_messages,
                "max_tokens": cfg["max_tokens"],
                "temperature": cfg["temperature"],
            },
            timeout=cfg["timeout"],
        )
        if response.status_code != 200:
            raise ValueError(f"LLM request failed: {response.status_code} {response.text[:300]}")
        data = response.json()
        content = data.get("content") or []
        text_parts = [item.get("text", "") for item in content if item.get("type") == "text"]
        if not any(part.strip() for part in text_parts):
            raise ValueError("LLM response did not include text content")
        return "\n".join(part for part in text_parts if part).strip()

    def _chat_google(self, cfg: Dict[str, Any], messages: List[Dict[str, str]]) -> str:
        prompt = "\n\n".join(f"{message.get('role', 'user')}: {message.get('content', '')}" for message in messages)
        response = requests.post(
            f"{cfg['base_url']}/models/{cfg['model']}:generateContent",
            params={"key": cfg["api_key"]},
            headers={"Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=cfg["timeout"],
        )
        if response.status_code != 200:
            raise ValueError(f"LLM request failed: {response.status_code} {response.text[:300]}")
        data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise ValueError("LLM response did not include candidates")
        parts = (((candidates[0].get("content") or {}).get("parts")) or [])
        texts = [part.get("text", "") for part in parts if isinstance(part, dict)]
        if not any(text.strip() for text in texts):
            raise ValueError("LLM response did not include text content")
        return "\n".join(text for text in texts if text).strip()

    def _chat_ollama(self, cfg: Dict[str, Any], messages: List[Dict[str, str]]) -> str:
        headers = {"Content-Type": "application/json"}
        if cfg["api_key"]:
            headers["Authorization"] = f"Bearer {cfg['api_key']}"
        response = requests.post(
            f"{cfg['base_url'].rstrip('/')}/api/chat",
            headers=headers,
            json={"model": cfg["model"], "messages": messages, "stream": False},
            timeout=cfg["timeout"],
        )
        if response.status_code != 200:
            raise ValueError(f"LLM request failed: {response.status_code} {response.text[:300]}")
        data = response.json()
        content = ((data.get("message") or {}).get("content")) or ""
        if not str(content).strip():
            raise ValueError("LLM response did not include text content")
        return str(content).strip()

    def _probe_candidate(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        cache_key = (cfg["provider"], cfg["base_url"], cfg["model"])
        cached = self._probe_cache.get(cache_key)
        if cached and (time.time() - cached[0]) < self._probe_ttl_seconds:
            return cached[1]

        try:
            if cfg["format"] not in {"ollama", "lmstudio"} and not cfg["api_key"]:
                result = {
                    "success": False,
                    "reachable": False,
                    "status_code": 0,
                    "provider": cfg["provider"],
                    "format": cfg["format"],
                    "endpoint": cfg["base_url"],
                    "model": cfg["model"],
                    "message": "api key missing",
                }
            elif cfg["format"] in {"openai_compatible", "lmstudio"}:
                headers = {"Content-Type": "application/json"}
                if cfg["api_key"]:
                    headers["Authorization"] = f"Bearer {cfg['api_key']}"
                endpoint = f"{cfg['base_url']}/models"
                response = requests.get(endpoint, headers=headers, timeout=cfg["timeout"])
                # Fallback to /chat/completions for providers that don't support /models (e.g. MiniMax)
                if response.status_code == 404:
                    endpoint = f"{cfg['base_url']}/chat/completions"
                    try:
                        response = requests.post(
                            endpoint,
                            headers=headers,
                            json={
                                "model": cfg["model"],
                                "messages": [{"role": "user", "content": "hi"}],
                                "max_tokens": 1,
                            },
                            timeout=cfg["timeout"],
                        )
                    except Exception:
                        pass
                result = {
                    "success": response.status_code == 200,
                    "reachable": response.status_code < 500,
                    "status_code": response.status_code,
                    "provider": cfg["provider"],
                    "format": cfg["format"],
                    "endpoint": endpoint,
                    "model": cfg["model"],
                    "message": "connection ok" if response.status_code == 200 else response.text[:300],
                }
            elif cfg["format"] == "anthropic":
                headers = {
                    "x-api-key": cfg["api_key"],
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                }
                endpoint = f"{cfg['base_url']}/models"
                response = requests.get(endpoint, headers=headers, timeout=cfg["timeout"])
                # Fallback to /messages for providers that don't support /models
                if response.status_code == 404:
                    endpoint = f"{cfg['base_url']}/messages"
                    try:
                        response = requests.post(
                            endpoint,
                            headers=headers,
                            json={
                                "model": cfg["model"],
                                "messages": [{"role": "user", "content": "hi"}],
                                "max_tokens": 1,
                            },
                            timeout=cfg["timeout"],
                        )
                    except Exception:
                        pass
                result = {
                    "success": response.status_code == 200,
                    "reachable": response.status_code < 500,
                    "status_code": response.status_code,
                    "provider": cfg["provider"],
                    "format": cfg["format"],
                    "endpoint": endpoint,
                    "model": cfg["model"],
                    "message": "connection ok" if response.status_code == 200 else response.text[:300],
                }
            elif cfg["format"] == "google":
                endpoint = f"{cfg['base_url']}/models"
                response = requests.get(endpoint, params={"key": cfg["api_key"]}, timeout=cfg["timeout"])
                # Fallback to direct model endpoint for providers that don't support /models
                if response.status_code == 404:
                    endpoint = f"{cfg['base_url']}/models/{cfg['model']}:generateContent"
                    try:
                        response = requests.post(
                            endpoint,
                            params={"key": cfg["api_key"]},
                            json={
                                "contents": [{"role": "user", "parts": [{"text": "hi"}]}],
                            },
                            timeout=cfg["timeout"],
                        )
                    except Exception:
                        pass
                result = {
                    "success": response.status_code == 200,
                    "reachable": response.status_code < 500,
                    "status_code": response.status_code,
                    "provider": cfg["provider"],
                    "format": cfg["format"],
                    "endpoint": endpoint,
                    "model": cfg["model"],
                    "message": "connection ok" if response.status_code == 200 else response.text[:300],
                }
            elif cfg["format"] == "ollama":
                headers = {"Content-Type": "application/json"}
                if cfg["api_key"]:
                    headers["Authorization"] = f"Bearer {cfg['api_key']}"
                response = requests.get(f"{cfg['base_url'].rstrip('/')}/api/tags", headers=headers, timeout=cfg["timeout"])
                result = {
                    "success": response.status_code == 200,
                    "reachable": response.status_code < 500,
                    "status_code": response.status_code,
                    "provider": cfg["provider"],
                    "format": cfg["format"],
                    "endpoint": f"{cfg['base_url'].rstrip('/')}/api/tags",
                    "model": cfg["model"],
                    "message": "connection ok" if response.status_code == 200 else response.text[:300],
                }
            else:
                result = {
                    "success": False,
                    "reachable": False,
                    "status_code": 0,
                    "provider": cfg["provider"],
                    "format": cfg["format"],
                    "endpoint": cfg["base_url"],
                    "model": cfg["model"],
                    "message": f"unsupported LLM format: {cfg['format']}",
                }
        except requests.RequestException as exc:
            result = {
                "success": False,
                "reachable": False,
                "status_code": 0,
                "provider": cfg["provider"],
                "format": cfg["format"],
                "endpoint": cfg["base_url"],
                "model": cfg["model"],
                "message": str(exc),
            }

        self._probe_cache[cache_key] = (time.time(), result)
        return result

    def _is_retryable_chat_error(self, exc: Exception) -> bool:
        if isinstance(exc, requests.RequestException):
            return True
        message = str(exc)
        match = re.search(r"LLM request failed:\s*(\d+)", message)
        if match:
            status_code = int(match.group(1))
            return self._should_retry_http_status(status_code)
        return False

    def _dispatch_chat(self, cfg: Dict[str, Any], messages: List[Dict[str, str]]) -> str:
        if cfg["format"] in {"openai_compatible", "lmstudio"}:
            return self._chat_openai_compatible(cfg, messages)
        if cfg["format"] == "anthropic":
            return self._chat_anthropic(cfg, messages)
        if cfg["format"] == "google":
            return self._chat_google(cfg, messages)
        if cfg["format"] == "ollama":
            return self._chat_ollama(cfg, messages)
        raise ValueError(f"Unsupported LLM format: {cfg['format']}")

    def _chat(self, messages: List[Dict[str, str]]) -> str:
        cfg = self._active_config()
        last_error: Exception | None = None
        candidate_chain = [cfg, *cfg.get("fallback_models", [])]
        for candidate in candidate_chain:
            if candidate["format"] not in {"ollama", "lmstudio"} and not candidate["api_key"]:
                if candidate.get("allow_demo_fallback"):
                    return "[DEMO_MODE] API key missing"
                last_error = ValueError(f"No API key configured for provider {candidate['provider']}")
                continue

            probe = self._probe_candidate(candidate)
            if not probe.get("success"):
                last_error = ValueError(
                    f"Provider {candidate['provider']} is unavailable: {probe.get('message') or 'probe failed'}"
                )
                logger.warning("llm_provider_probe_failed", provider=candidate["provider"], message=probe.get("message"))
                continue

            for attempt in range(1, 4):
                try:
                    return self._dispatch_chat(candidate, messages)
                except (requests.RequestException, ValueError) as exc:
                    last_error = exc
                    if attempt < 3 and self._is_retryable_chat_error(exc):
                        time.sleep(self._retry_delay_seconds(attempt))
                        continue
                    break

            logger.warning("llm_provider_failed_fallback", provider=candidate["provider"], error=str(last_error))
        if last_error is not None:
            raise ValueError(str(last_error)) from last_error
        raise ValueError("LLM request failed without a response")

    def translate_text(
        self,
        text: str,
        source_lang: str = "auto",
        target_lang: str = "en",
        system_prompt_override: str | None = None,
    ) -> str:
        if not text or not text.strip():
            return text

        prompt = (
            f"Translate from {source_lang} to {target_lang}. "
            "Return translated text only, keep units/codes/symbols unchanged:\n\n"
            f"{text}"
        )
        system_prompt = system_prompt_override or self._compose_system_prompt(
            [text],
            source_lang,
            target_lang,
            enable_inference=False,
        )

        try:
            translated = self._chat(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ]
            )
            return self._strip_think_tags(translated)
        except Exception as exc:
            logger.error("translate_text_failed", error=str(exc))
            return f"[translation_error]{text}"

    def _extract_json_block(self, content: str) -> str:
        stripped = content.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if len(lines) >= 3:
                return "\n".join(lines[1:-1]).strip()
        return stripped

    @staticmethod
    def _strip_think_tags(text: str) -> str:
        """Remove <think>...</think> reasoning blocks from model output."""
        if not text:
            return text
        # Handle nested or multiple think blocks
        while True:
            start = text.lower().find("<think>")
            if start == -1:
                break
            end = text.lower().find("</think>", start)
            if end == -1:
                # Unclosed tag: remove from start to end of string
                text = text[:start]
                break
            prefix = text[:start]
            suffix = text[end + 8:]
            # Insert a space if both sides have non-whitespace content
            if prefix.rstrip() and suffix.lstrip():
                text = prefix.rstrip() + " " + suffix.lstrip()
            else:
                text = prefix + suffix
        return text.strip()

    def _translate_batch_json(
        self,
        texts: List[str],
        source_lang: str,
        target_lang: str,
        system_prompt_override: str | None = None,
    ) -> Dict[str, str]:
        payload = {f"text_{idx}": value for idx, value in enumerate(texts)}
        user_content = json.dumps(payload, ensure_ascii=False)

        prompt = (
            f"Translate JSON values from {source_lang} to {target_lang}. "
            "Keep keys unchanged. Output valid JSON only."
        )
        system_prompt = system_prompt_override or self._compose_system_prompt(
            texts,
            source_lang,
            target_lang,
            enable_inference=False,
        )

        content = self._chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
                {"role": "user", "content": user_content},
            ]
        )
        content = self._strip_think_tags(content)
        parsed = json.loads(self._extract_json_block(content))
        return {original: parsed.get(f"text_{idx}", original) for idx, original in enumerate(texts)}

    def translate_batch(
        self,
        texts: List[str],
        source_lang: str = "auto",
        target_lang: str = "en",
        progress_callback: Callable[[Dict[str, Any]], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> List[str]:
        if not texts:
            return []

        runtime = self._active_config()
        batch_size = max(1, int(runtime["batch_size"]))
        batch_json_enabled = bool(runtime["batch_json"])
        parallel_count = max(1, int(runtime.get("parallel_count", 1)))
        translated_by_text: Dict[str, str] = {}
        out: List[str] = []

        translatable_texts = [t for t in texts if self._is_translatable_text(t)]
        if not translatable_texts:
            return texts

        total_chunks = max(1, (len(translatable_texts) + batch_size - 1) // batch_size)
        processed_count = 0
        completed_chunks = 0
        lock = threading.Lock()

        def emit_progress(event: str, **payload: Any) -> None:
            if progress_callback is None:
                return
            try:
                with lock:
                    progress_callback(
                        {
                            "event": event,
                            "provider": runtime["provider"],
                            "model": runtime["model"],
                            "batch_size": batch_size,
                            "retry_count": int(runtime["retry_count"]),
                            "total_texts": len(translatable_texts),
                            "translated_count": processed_count,
                            "total_chunks": total_chunks,
                            "completed_chunks": completed_chunks,
                            "parallel_count": parallel_count,
                            **payload,
                        }
                    )
            except Exception as exc:
                logger.warning("translate_batch_progress_callback_failed", error=str(exc))

        def raise_if_cancelled() -> None:
            if should_cancel and should_cancel():
                raise RuntimeError("Task cancelled by user.")

        def _translate_chunk_worker(
            chunk_index: int,
            chunk: List[str],
        ) -> Tuple[int, Dict[str, str], str]:
            """Worker function to translate a single chunk."""
            chunk_translated: Dict[str, str] = {}
            chunk_error = ""

            try:
                if batch_json_enabled and len(chunk) > 1:
                    chunk_translated.update(
                        self._translate_batch_json(
                            chunk,
                            source_lang,
                            target_lang,
                            system_prompt_override=system_prompt,
                        )
                    )
                else:
                    for t in chunk:
                        raise_if_cancelled()
                        chunk_translated[t] = self.translate_text(
                            t,
                            source_lang,
                            target_lang,
                            system_prompt_override=system_prompt,
                        )
            except Exception as exc:
                chunk_error = str(exc)
                logger.warning("batch_json_failed_fallback_single", error=str(exc))
                for t in chunk:
                    raise_if_cancelled()
                    chunk_translated[t] = self.translate_text(
                        t,
                        source_lang,
                        target_lang,
                        system_prompt_override=system_prompt,
                    )

            return chunk_index, chunk_translated, chunk_error

        emit_progress("started")

        system_prompt = self._compose_system_prompt(
            translatable_texts[:30],
            source_lang,
            target_lang,
            enable_inference=True,
        )

        # Build chunks
        chunks = []
        for chunk_index, start in enumerate(range(0, len(translatable_texts), batch_size), start=1):
            chunk = translatable_texts[start : start + batch_size]
            chunks.append((chunk_index, chunk))

        # Sequential execution when parallel_count == 1
        if parallel_count <= 1:
            for chunk_index, chunk in chunks:
                raise_if_cancelled()
                emit_progress(
                    "chunk_started",
                    chunk_index=chunk_index,
                    chunk_size=len(chunk),
                    completed_chunks=completed_chunks,
                )
                _, chunk_translated, chunk_error = _translate_chunk_worker(chunk_index, chunk)
                with lock:
                    translated_by_text.update(chunk_translated)
                    processed_count += len(chunk)
                    completed_chunks += 1
                emit_progress(
                    "chunk_completed",
                    chunk_index=chunk_index,
                    chunk_size=len(chunk),
                    completed_chunks=completed_chunks,
                    translated_count=processed_count,
                    last_error=chunk_error,
                    chunk_translations=chunk_translated,
                )
                time.sleep(0.05)
        else:
            # Parallel execution with ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=parallel_count) as executor:
                future_to_index = {
                    executor.submit(_translate_chunk_worker, chunk_index, chunk): chunk_index
                    for chunk_index, chunk in chunks
                }

                for future in as_completed(future_to_index):
                    raise_if_cancelled()
                    chunk_index = future_to_index[future]
                    try:
                        _, chunk_translated, chunk_error = future.result()
                        with lock:
                            translated_by_text.update(chunk_translated)
                            processed_count += len(chunk_translated)
                            completed_chunks += 1
                        emit_progress(
                            "chunk_completed",
                            chunk_index=chunk_index,
                            chunk_size=len(chunk_translated),
                            completed_chunks=completed_chunks,
                            translated_count=processed_count,
                            last_error=chunk_error,
                            chunk_translations=chunk_translated,
                        )
                    except Exception as exc:
                        logger.error("chunk_translation_failed", chunk_index=chunk_index, error=str(exc))
                        raise

        for item in texts:
            if item and item.strip():
                translated = translated_by_text.get(item, item)
                # Preserve [translation_error] marker so callers can detect failures
                if isinstance(translated, str) and translated.startswith("[translation_error]"):
                    out.append(translated)
                else:
                    out.append(translated)
            else:
                out.append(item)

        emit_progress(
            "completed",
            completed_chunks=total_chunks,
            translated_count=processed_count,
        )
        return out


class LLMExcelTranslationProcessor:
    def __init__(self):
        self.service = LLMTranslationService()

    def _detect_text_columns(self, df: pd.DataFrame) -> List[str]:
        cols: List[str] = []
        for col in df.columns:
            if df[col].dtype != "object":
                continue
            sample = df[col].dropna().astype(str).head(10)
            if sample.empty:
                continue
            if any(any(ch.isalpha() or "\u4e00" <= ch <= "\u9fff" for ch in text) for text in sample):
                cols.append(col)
        return cols

    def translate_excel_file(
        self,
        input_file_path: str,
        output_file_path: str,
        text_columns: Optional[List[str]] = None,
        source_lang: str = "auto",
        target_lang: str = "en",
        translation_mode: str = "add",
    ) -> Dict[str, Any]:
        df = pd.read_excel(input_file_path)
        text_columns = text_columns or self._detect_text_columns(df)

        stats = {
            "total_rows": len(df),
            "text_columns": text_columns,
            "translated_cells": 0,
            "skipped_cells": 0,
            "error_cells": 0,
        }

        for col in text_columns:
            if col not in df.columns:
                continue
            values = df[col].fillna("").astype(str).tolist()
            translated = self.service.translate_batch(values, source_lang=source_lang, target_lang=target_lang)

            for original, target in zip(values, translated):
                if not original.strip():
                    stats["skipped_cells"] += 1
                elif target.startswith("[translation_error]"):
                    stats["error_cells"] += 1
                else:
                    stats["translated_cells"] += 1

            # Replace [translation_error] markers with empty strings in output
            cleaned_translated = []
            for target in translated:
                if isinstance(target, str) and target.startswith("[translation_error]"):
                    cleaned_translated.append("")
                else:
                    cleaned_translated.append(target)

            if translation_mode == "replace":
                df[col] = cleaned_translated
            else:
                df[f"{col}_translated"] = cleaned_translated

        df.to_excel(output_file_path, index=False)
        stats.update(
            {
                "sheets_processed": 1,
                "rows_translated": len(df),
                "columns_translated": len(text_columns),
                "successful_translations": stats["translated_cells"],
                "failed_translations": stats["error_cells"],
            }
        )
        return stats

    def create_translation_report(self, stats: Dict[str, Any], output_path: str) -> str:
        report = {
            "engine": "unified-llm-translation-service",
            "provider": self.service.get_runtime_summary()["provider"],
            "model": self.service.get_runtime_summary()["model"],
            "total_rows": stats["total_rows"],
            "translated_cells": stats["translated_cells"],
            "skipped_cells": stats["skipped_cells"],
            "error_cells": stats["error_cells"],
        }
        report_df = pd.DataFrame(list(report.items()), columns=["item", "value"])
        report_path = output_path.replace(".xlsx", "_translation_report.xlsx")
        report_df.to_excel(report_path, index=False)
        return report_path


llm_translation_service = LLMTranslationService()
llm_excel_processor = LLMExcelTranslationProcessor()
