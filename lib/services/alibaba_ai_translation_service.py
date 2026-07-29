#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Backward-compatible wrapper for legacy Alibaba service imports."""

from app.services.llm.translation_service import (
    LLMExcelTranslationProcessor,
    LLMTranslationService,
    llm_excel_processor,
    llm_translation_service,
)


class AlibabaBailianTranslationService(LLMTranslationService):
    """Compatibility alias. Uses the new unified LLM service."""


class AlibabaBailianExcelProcessor(LLMExcelTranslationProcessor):
    """Compatibility alias. Uses the new unified Excel translation processor."""


alibaba_ai_translation_service = llm_translation_service
alibaba_ai_excel_processor = llm_excel_processor
