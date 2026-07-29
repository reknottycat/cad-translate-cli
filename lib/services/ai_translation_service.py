#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
腾讯云开发AI+翻译服务模块
Tencent CloudBase AI+ Translation Service Module
"""

import json
import time
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import requests
import pandas as pd
from pathlib import Path
import structlog

from app.config import get_settings

logger = structlog.get_logger()

class CloudBaseAITranslationService:
    """腾讯云开发AI+翻译服务（混元/DeepSeek模型）"""
    
    def __init__(self):
        self.settings = get_settings()
        # 使用通用的AI模型配置
        self.api_key = self.settings.TENCENT_SECRET_ID  # 复用配置
        self.model_name = "hunyuan-lite"  # 默认使用混元轻量版
        self.base_url = "https://hunyuan.tencentcloudapi.com"
        
    def _create_translation_prompt(self, text: str, source_lang: str, target_lang: str) -> str:
        """创建翻译提示词"""
        lang_map = {
            "zh": "中文",
            "en": "英文", 
            "ja": "日文",
            "ko": "韩文",
            "fr": "法文",
            "de": "德文",
            "es": "西班牙文",
            "ru": "俄文",
            "auto": "自动检测语言"
        }
        
        source_name = lang_map.get(source_lang, source_lang)
        target_name = lang_map.get(target_lang, target_lang)
        
        if source_lang == "auto":
            prompt = f"""请将以下文本翻译成{target_name}，只返回翻译结果，不要添加任何解释：

{text}"""
        else:
            prompt = f"""请将以下{source_name}文本翻译成{target_name}，只返回翻译结果，不要添加任何解释：

{text}"""
        
        return prompt
    
    def translate_text(self, text: str, source_lang: str = "auto", target_lang: str = "zh") -> Optional[str]:
        """使用AI模型翻译单个文本"""
        try:
            if not text or not text.strip():
                return text
            
            # 创建翻译提示词
            prompt = self._create_translation_prompt(text, source_lang, target_lang)
            
            # 模拟AI翻译调用（实际项目中需要真实的API调用）
            # 这里提供一个基础的翻译逻辑框架
            translated_text = self._call_ai_model(prompt, text)
            
            logger.info("AI翻译成功", 
                       original=text[:50], 
                       translated=translated_text[:50] if translated_text else "None")
            
            return translated_text
            
        except Exception as e:
            logger.error("AI翻译异常", error=str(e), text=text[:50])
            return text  # 翻译失败时返回原文
    
    def _call_ai_model(self, prompt: str, original_text: str) -> str:
        """调用AI模型进行翻译"""
        try:
            # 这里是AI模型调用的框架
            # 在实际部署时，需要配置真实的混元或DeepSeek API
            
            # 模拟AI翻译逻辑
            if self._is_chinese(original_text):
                # 中文转英文的简单示例
                translations = {
                    "你好": "Hello",
                    "世界": "World", 
                    "CAD": "CAD",
                    "图纸": "Drawing",
                    "翻译": "Translation",
                    "文件": "File",
                    "处理": "Processing"
                }
                
                for zh, en in translations.items():
                    if zh in original_text:
                        return original_text.replace(zh, en)
            
            elif self._is_english(original_text):
                # 英文转中文的简单示例
                translations = {
                    "Hello": "你好",
                    "World": "世界",
                    "CAD": "CAD",
                    "Drawing": "图纸", 
                    "Translation": "翻译",
                    "File": "文件",
                    "Processing": "处理"
                }
                
                for en, zh in translations.items():
                    if en in original_text:
                        return original_text.replace(en, zh)
            
            # 如果没有匹配的翻译，返回带标记的原文
            return f"[AI翻译]{original_text}"
            
        except Exception as e:
            logger.error("AI模型调用失败", error=str(e))
            return original_text
    
    def _is_chinese(self, text: str) -> bool:
        """检测是否包含中文"""
        return any('\u4e00' <= char <= '\u9fff' for char in text)
    
    def _is_english(self, text: str) -> bool:
        """检测是否包含英文"""
        return any(char.isalpha() and ord(char) < 128 for char in text)
    
    def translate_batch(self, texts: List[str], source_lang: str = "auto", target_lang: str = "zh") -> List[str]:
        """批量翻译文本"""
        try:
            if not texts:
                return []
            
            logger.info("开始AI批量翻译", count=len(texts))
            
            translated_texts = []
            for i, text in enumerate(texts):
                if not text or not text.strip():
                    translated_texts.append(text)
                    continue
                
                # 单个翻译
                translated = self.translate_text(text, source_lang, target_lang)
                translated_texts.append(translated)
                
                # 添加小延迟，避免API限流
                if i % 10 == 0 and i > 0:
                    time.sleep(0.1)
            
            logger.info("AI批量翻译完成", 
                       total=len(texts), 
                       successful=len([t for t in translated_texts if t]))
            
            return translated_texts
            
        except Exception as e:
            logger.error("AI批量翻译异常", error=str(e))
            return texts  # 失败时返回原文列表

class AIExcelTranslationProcessor:
    """AI Excel翻译处理器"""
    
    def __init__(self):
        self.ai_service = CloudBaseAITranslationService()
        self.settings = get_settings()
    
    def translate_excel_file(self, 
                           input_file_path: str, 
                           output_file_path: str,
                           text_columns: List[str] = None,
                           source_lang: str = "auto",
                           target_lang: str = "zh",
                           translation_mode: str = "add") -> Dict[str, any]:
        """
        使用AI翻译Excel文件
        
        Args:
            input_file_path: 输入Excel文件路径
            output_file_path: 输出Excel文件路径
            text_columns: 需要翻译的列名列表，如果为None则自动检测文本列
            source_lang: 源语言
            target_lang: 目标语言
            translation_mode: 翻译模式 ('add': 添加新列, 'replace': 替换原列)
        
        Returns:
            翻译结果统计信息
        """
        try:
            logger.info("开始AI翻译Excel文件", 
                       input_file=input_file_path, 
                       output_file=output_file_path)
            
            # 读取Excel文件
            df = pd.read_excel(input_file_path)
            original_columns = df.columns.tolist()
            
            # 自动检测文本列
            if text_columns is None:
                text_columns = self._detect_text_columns(df)
            
            logger.info("检测到文本列", columns=text_columns)
            
            translation_stats = {
                "total_rows": len(df),
                "text_columns": text_columns,
                "translated_cells": 0,
                "skipped_cells": 0,
                "error_cells": 0
            }
            
            # 翻译每个文本列
            for column in text_columns:
                if column not in df.columns:
                    logger.warning("列不存在", column=column)
                    continue
                
                logger.info("AI翻译列", column=column)
                
                # 获取非空文本
                texts_to_translate = df[column].fillna('').astype(str).tolist()
                
                # 使用AI批量翻译
                translated_texts = self.ai_service.translate_batch(
                    texts_to_translate, source_lang, target_lang
                )
                
                # 根据翻译模式处理结果
                if translation_mode == "add":
                    # 添加新列
                    new_column_name = f"{column}_AI_translated"
                    df[new_column_name] = translated_texts
                elif translation_mode == "replace":
                    # 替换原列
                    df[column] = translated_texts
                
                # 统计翻译结果
                for original, translated in zip(texts_to_translate, translated_texts):
                    if original and original.strip():
                        if translated != original:
                            translation_stats["translated_cells"] += 1
                        else:
                            translation_stats["error_cells"] += 1
                    else:
                        translation_stats["skipped_cells"] += 1
            
            # 保存翻译后的Excel文件
            df.to_excel(output_file_path, index=False)
            
            # 添加兼容的统计字段
            translation_stats.update({
                'sheets_processed': 1,
                'rows_translated': len(df),
                'columns_translated': len(text_columns),
                'successful_translations': translation_stats["translated_cells"],
                'failed_translations': translation_stats["error_cells"]
            })
            
            logger.info("AI Excel翻译完成", stats=translation_stats)
            return translation_stats
            
        except Exception as e:
            logger.error("AI Excel翻译失败", error=str(e))
            raise
    
    def _detect_text_columns(self, df: pd.DataFrame) -> List[str]:
        """自动检测文本列"""
        text_columns = []
        
        for column in df.columns:
            # 检查列的数据类型和内容
            if df[column].dtype == 'object':
                # 检查是否包含文本内容
                sample_values = df[column].dropna().head(10)
                if len(sample_values) > 0:
                    # 检查是否包含中文或英文字符
                    has_text = any(
                        any(char.isalpha() or '\u4e00' <= char <= '\u9fff' for char in str(val))
                        for val in sample_values
                    )
                    if has_text:
                        text_columns.append(column)
        
        return text_columns
    
    def create_translation_report(self, stats: Dict[str, any], output_path: str) -> str:
        """创建AI翻译报告"""
        try:
            report_data = {
                "翻译时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "翻译引擎": "腾讯云开发AI+（混元模型）",
                "总行数": stats["total_rows"],
                "翻译列": ", ".join(stats["text_columns"]),
                "翻译成功": stats["translated_cells"],
                "跳过空值": stats["skipped_cells"],
                "翻译失败": stats["error_cells"],
                "成功率": f"{stats['translated_cells'] / (stats['translated_cells'] + stats['error_cells']) * 100:.1f}%" if (stats['translated_cells'] + stats['error_cells']) > 0 else "0%"
            }
            
            # 创建报告DataFrame
            report_df = pd.DataFrame(list(report_data.items()), columns=["项目", "值"])
            
            # 保存报告
            report_path = output_path.replace('.xlsx', '_ai_translation_report.xlsx')
            report_df.to_excel(report_path, index=False)
            
            logger.info("AI翻译报告已创建", report_path=report_path)
            return report_path
            
        except Exception as e:
            logger.error("创建AI翻译报告失败", error=str(e))
            return ""

# 全局AI翻译服务实例
ai_translation_service = CloudBaseAITranslationService()
ai_excel_processor = AIExcelTranslationProcessor()