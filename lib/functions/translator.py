#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 翻译功能模块
translator.py - 调用翻译服务将文本列表翻译为目标语言
"""

from __future__ import annotations

from typing import Dict, List, Optional, Any
from pathlib import Path

import pandas as pd
import structlog

logger = structlog.get_logger(__name__)


class Translator:
    """
    文本翻译器
    
    通过注入的翻译函数（translation_func）对文本列表进行翻译，
    并将结果写回 Excel 文件。
    
    translation_func 签名：
        (text: str, target_lang: str) -> str
    """

    def __init__(self, translation_func=None) -> None:
        """
        Args:
            translation_func: 可调用对象，接收 (text, target_lang) -> str
        """
        self._translate = translation_func

    def translate_excel(
        self,
        excel_path: str,
        target_lang: str = "en",
        original_col: str = "原文",
        translated_col: str = "译文",
    ) -> Dict[str, Any]:
        """
        读取 Excel 中指定原文列，翻译后写入译文列并覆盖保存。

        Args:
            excel_path:     Excel 文件路径
            target_lang:    目标语言代码
            original_col:   原文所在列名
            translated_col: 译文写入列名

        Returns:
            {"success": bool, "translated_count": int, "message": str}
        """
        if self._translate is None:
            raise RuntimeError("翻译功能未配置，请提供 translation_func 参数。")

        path = Path(excel_path)
        if not path.exists():
            raise FileNotFoundError(f"Excel 文件不存在: {excel_path}")

        df = pd.read_excel(str(path))

        if original_col not in df.columns:
            raise ValueError(f"Excel 中找不到列 '{original_col}'")

        translated_count = 0
        results: List[str] = []

        for _, row in df.iterrows():
            original = str(row.get(original_col, "")).strip()
            if original and original.lower() not in ("nan", "none", ""):
                try:
                    translated = self._translate(original, target_lang)
                    results.append(translated or original)
                    if translated and translated != original:
                        translated_count += 1
                except Exception as exc:
                    logger.warning("translate_failed", text=original[:40], error=str(exc))
                    results.append(original)
            else:
                results.append("")

        df[translated_col] = results
        df.to_excel(str(path), index=False, engine="openpyxl")

        logger.info("translate_excel_done", path=str(path), translated=translated_count)
        return {
            "success": True,
            "translated_count": translated_count,
            "excel_path": str(path),
            "message": f"成功翻译 {translated_count} 条文本",
        }

    def build_translation_map_from_excel(
        self,
        excel_path: str,
        original_col_idx: int = 1,
        translated_col_idx: int = 2,
    ) -> Dict[str, str]:
        """
        从 Excel 文件构建原文 -> 译文 映射表。
        
        支持两种 Excel 格式：
         - 3 列：序号 | 原文 | 译文  (original_col_idx=1, translated_col_idx=2)
         - 2 列：原文 | 译文          (original_col_idx=0, translated_col_idx=1)
        """
        df = pd.read_excel(excel_path)
        translation_map: Dict[str, str] = {}

        for _, row in df.iterrows():
            ncols = len(row)
            if ncols >= 3:
                original = str(row.iloc[1]).strip()
                translated = row.iloc[2]
            elif ncols >= 2:
                original = str(row.iloc[0]).strip()
                translated = row.iloc[1]
            else:
                continue

            if pd.notna(translated):
                translated_str = str(translated).strip()
                if translated_str and translated_str.lower() not in ("", "nan", "none", "null", "n/a", "na"):
                    translation_map[original] = translated_str

        logger.info("translation_map_built", count=len(translation_map), path=excel_path)
        return translation_map
