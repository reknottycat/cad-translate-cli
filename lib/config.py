#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Application configuration."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = Path(os.environ.get("CAD_TRANSLATION_ENV_FILE", BACKEND_DIR / ".env"))


def _xdg_config_home() -> Path:
    explicit = os.environ.get("XDG_CONFIG_HOME", "").strip()
    if explicit:
        return Path(explicit)
    return Path.home() / ".config"


def _default_runtime_config_file() -> Path:
    explicit = os.environ.get("CAD_TRANSLATION_RUNTIME_CONFIG_FILE", "").strip()
    if explicit:
        return Path(explicit)
    return _xdg_config_home() / "cli-anything-cad" / "config.json"


DEFAULT_RUNTIME_CONFIG_FILE = Path(
    _default_runtime_config_file()
)


class Settings(BaseSettings):
    """Global application settings."""

    model_config = SettingsConfigDict(
        env_file=str(DEFAULT_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    APP_NAME: str = Field(default="CAD Translation System")
    VERSION: str = Field(default="2.0.0")
    DEBUG: bool = Field(default=False)
    APP_ENV: str = Field(default="development")
    LOG_LEVEL: str = Field(default="INFO")

    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)

    ALLOWED_ORIGINS: List[str] = Field(
        default=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:4174",
            "http://127.0.0.1:4174",
            "http://localhost:4175",
            "http://127.0.0.1:4175",
        ]
    )
    CORS_ORIGINS: str = Field(
        default=(
            "http://localhost:3000,http://127.0.0.1:3000,"
            "http://localhost:4174,http://127.0.0.1:4174,"
            "http://localhost:4175,http://127.0.0.1:4175"
        )
    )

    DATABASE_URL: str = Field(default="sqlite:///./cad_translation.db")
    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    ASYNC_TASKS_MODE: str = Field(default="auto")

    BASE_DIR: Path = Field(default=BACKEND_DIR)
    UPLOAD_DIR: str = Field(default="uploads")
    OUTPUT_DIR: str = Field(default="outputs")
    TEMP_DIR: str = Field(default="temp")
    UPLOAD_PATH: str = Field(default="./uploads")
    OUTPUT_PATH: str = Field(default="./outputs")

    MAX_FILE_SIZE: int = Field(default=100 * 1024 * 1024)
    MAX_FILES_PER_PROJECT: int = Field(default=50)
    ALLOWED_FILE_EXTENSIONS: List[str] = Field(default=[".dwg", ".dxf", ".DWG", ".DXF"])

    CAD_CONVERTER_TIMEOUT: int = Field(default=300)
    TEXT_EXTRACTION_TIMEOUT: int = Field(default=180)
    TRANSLATION_TIMEOUT: int = Field(default=120)
    DWG_CONVERTER_BACKEND: str = Field(default="auto")
    DWG_AUTO_BACKENDS: str = Field(default="haochen_com,autocad_com,oda")
    DWG_DISABLED_BACKENDS: str = Field(default="")
    LIBREDWG_DWG2DXF_PATH: str = Field(default="")
    LIBREDWG_INSTALL_DIR: str = Field(default="tools/libredwg/0.13.3-win64")
    LIBREDWG_DOWNLOAD_URL: str = Field(
        default=(
            "https://github.com/LibreDWG/libredwg/releases/download/0.13.3/"
            "libredwg-0.13.3-win64.zip"
        )
    )
    LIBREDWG_AUTO_DOWNLOAD: bool = Field(default=True)
    ODA_FILE_CONVERTER_PATH: str = Field(default="")
    ODA_OUTPUT_VERSION: str = Field(default="ACAD2018")
    ODA_OUTPUT_FORMAT: str = Field(default="DXF")

    TENCENT_SECRET_ID: str = Field(default="")
    TENCENT_SECRET_KEY: str = Field(default="")
    TENCENT_REGION: str = Field(default="ap-beijing")

    HUNYUAN_SECRET_ID: str = Field(default="")
    HUNYUAN_SECRET_KEY: str = Field(default="")
    HUNYUAN_MODEL: str = Field(default="hunyuan-lite")
    HUNYUAN_REGION: str = Field(default="ap-beijing")

    DEEPSEEK_API_KEY: str = Field(default="")
    DEEPSEEK_MODEL: str = Field(default="deepseek-chat")

    JWT_SECRET_KEY: str = Field(default="change-this-in-production")
    ENABLE_ADMIN_GUARD: bool = Field(default=False)
    ADMIN_API_TOKEN: str = Field(default="")

    DEFAULT_SOURCE_LANGUAGE: str = Field(default="zh")
    DEFAULT_TARGET_LANGUAGE: str = Field(default="en")
    DEFAULT_FONT_NAME: str = Field(default="Times New Roman")
    DEFAULT_FONT_SIZE_REDUCTION: int = Field(default=4)
    DEFAULT_TRANSLATION_MODE: str = Field(default="add")

    AVAILABLE_FONTS: List[str] = Field(
        default=[
            "Times New Roman",
            "Arial",
            "SimSun",
            "SimHei",
            "Microsoft YaHei",
            "Calibri",
            "Verdana",
            "Tahoma",
            "Georgia",
            "Courier New",
        ]
    )

    SUPPORTED_LANGUAGES: Dict[str, str] = Field(
        default={
            "zh": "中文",
            "en": "English",
            "ja": "日本語",
            "ko": "한국어",
            "fr": "Français",
            "de": "Deutsch",
            "es": "Español",
            "ru": "Русский",
        }
    )

    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/0")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/0")
    CELERY_TASK_TIMEOUT: int = Field(default=3600)
    CELERY_RESULT_EXPIRES: int = Field(default=3600)

    TRANSLATION_PROVIDER: str = Field(default="openai_compatible")
    LLM_API_FORMAT: str = Field(default="openai_compatible")
    LLM_BASE_URL: str = Field(default="https://dashscope.aliyuncs.com/compatible-mode/v1")
    LLM_API_KEY: str = Field(default="")
    LLM_MODEL: str = Field(default="qwen-max")
    LLM_SYSTEM_PROMPT_MODE: str = Field(default="default")
    LLM_CUSTOM_SYSTEM_PROMPT: str = Field(default="")
    LLM_GLOSSARY_FILE: str = Field(default="")
    LLM_REASONING_ENABLED: bool = Field(default=False)
    LLM_TIMEOUT_SECONDS: int = Field(default=300)
    LLM_TEMPERATURE: float = Field(default=0.1)
    LLM_MAX_TOKENS: int = Field(default=16384)
    LLM_BATCH_SIZE: int = Field(default=12)
    LLM_ENABLE_BATCH_JSON: bool = Field(default=True)
    LLM_PARALLEL_COUNT: int = Field(default=1)
    LLM_RETRY_COUNT: int = Field(default=2)
    LLM_RPM: int = Field(default=40)
    LLM_TPM: str = Field(default="")
    LLM_EXTRA_BODY: str = Field(default="")
    LLM_USE_SYSTEM_PROXY: bool = Field(default=False)
    LLM_ALLOW_DEMO_FALLBACK: bool = Field(default=False)
    LLM_SYSTEM_PROMPT: str = Field(
        default=(
            "你是专业 CAD 图纸翻译专家。保持术语准确，保持原文单位和代号格式，"
            "只输出翻译文本，不输出解释。"
        )
    )

    OPENAI_API_KEY: str = Field(default="")
    OPENROUTER_API_KEY: str = Field(default="")
    NVIDIA_API_KEY: str = Field(default="")
    GROQ_API_KEY: str = Field(default="")
    TOGETHER_API_KEY: str = Field(default="")
    SILICONFLOW_API_KEY: str = Field(default="")
    MOONSHOT_API_KEY: str = Field(default="")
    ZHIPU_API_KEY: str = Field(default="")
    MINIMAX_API_KEY: str = Field(default="")

    def get_env_file_path(self) -> Path:
        return DEFAULT_ENV_FILE

    def get_runtime_config_path(self) -> Path:
        return DEFAULT_RUNTIME_CONFIG_FILE

    def resolve_path(self, value: str | Path) -> Path:
        path = Path(value)
        return path if path.is_absolute() else self.BASE_DIR / path

    def resolve_database_url(self) -> str:
        prefix = "sqlite:///"
        if not self.DATABASE_URL.startswith(prefix):
            return self.DATABASE_URL

        sqlite_path = self.DATABASE_URL[len(prefix) :]
        db_path = Path(sqlite_path)
        if db_path.is_absolute():
            return self.DATABASE_URL
        return f"{prefix}{(self.BASE_DIR / db_path).resolve().as_posix()}"

    def get_upload_path(self) -> Path:
        upload_path = self.resolve_path(self.UPLOAD_DIR)
        upload_path.mkdir(parents=True, exist_ok=True)
        return upload_path

    def get_output_path(self) -> Path:
        output_path = self.resolve_path(self.OUTPUT_DIR)
        output_path.mkdir(parents=True, exist_ok=True)
        return output_path

    def get_temp_path(self) -> Path:
        temp_path = self.resolve_path(self.TEMP_DIR)
        temp_path.mkdir(parents=True, exist_ok=True)
        return temp_path

    def get_static_path(self) -> Path:
        static_path = self.resolve_path("static")
        static_path.mkdir(parents=True, exist_ok=True)
        return static_path

    def get_admin_token(self) -> str:
        return self.ADMIN_API_TOKEN.strip()

    @field_validator("DEBUG", mode="before")
    @classmethod
    def normalize_debug(cls, value: Any) -> Any:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "production", "prod", "false", "0", "no", "off"}:
                return False
            if normalized in {"development", "dev", "true", "1", "yes", "on"}:
                return True
        return value


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def load_runtime_config(path: Path | None = None) -> Dict[str, Any]:
    runtime_path = path or DEFAULT_RUNTIME_CONFIG_FILE
    if not runtime_path.exists():
        return {}

    try:
        data = json.loads(runtime_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    return data if isinstance(data, dict) else {}
