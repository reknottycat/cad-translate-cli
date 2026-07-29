#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
翻译服务模块
Translation Service Module
"""

import json
import hmac
import hashlib
import base64
import time
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import requests
import pandas as pd
from pathlib import Path
import structlog

from app.config import get_settings

logger = structlog.get_logger()

class TencentTranslationService:
    """腾讯云翻译服务"""
    
    def __init__(self):
        self.settings = get_settings()
        self.secret_id = self.settings.TENCENT_SECRET_ID
        self.secret_key = self.settings.TENCENT_SECRET_KEY
        self.region = self.settings.TENCENT_REGION
        self.endpoint = "tmt.tencentcloudapi.com"
        self.service = "tmt"
        self.version = "2018-03-21"
        
    def _sign(self, key: bytes, msg: str) -> bytes:
        """生成签名"""
        return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()
    
    def _get_signature_key(self, key: str, date_stamp: str, region_name: str, service_name: str) -> bytes:
        """获取签名密钥"""
        k_date = self._sign(('TC3' + key).encode('utf-8'), date_stamp)
        k_region = self._sign(k_date, region_name)
        k_service = self._sign(k_region, service_name)
        k_signing = self._sign(k_service, 'tc3_request')
        return k_signing
    
    def _create_headers(self, payload: str, action: str) -> Dict[str, str]:
        """创建请求头"""
        algorithm = 'TC3-HMAC-SHA256'
        timestamp = int(time.time())
        date = datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d')
        
        # 创建规范请求
        http_request_method = 'POST'
        canonical_uri = '/'
        canonical_querystring = ''
        canonical_headers = f'content-type:application/json; charset=utf-8\nhost:{self.endpoint}\nx-tc-action:{action.lower()}\n'
        signed_headers = 'content-type;host;x-tc-action'
        hashed_request_payload = hashlib.sha256(payload.encode('utf-8')).hexdigest()
        canonical_request = f'{http_request_method}\n{canonical_uri}\n{canonical_querystring}\n{canonical_headers}\n{signed_headers}\n{hashed_request_payload}'
        
        # 创建待签名字符串
        credential_scope = f'{date}/{self.region}/{self.service}/tc3_request'
        hashed_canonical_request = hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()
        string_to_sign = f'{algorithm}\n{timestamp}\n{credential_scope}\n{hashed_canonical_request}'
        
        # 计算签名
        signing_key = self._get_signature_key(self.secret_key, date, self.region, self.service)
        signature = hmac.new(signing_key, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
        
        # 创建授权头
        authorization = f'{algorithm} Credential={self.secret_id}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}'
        
        return {
            'Authorization': authorization,
            'Content-Type': 'application/json; charset=utf-8',
            'Host': self.endpoint,
            'X-TC-Action': action,
            'X-TC-Timestamp': str(timestamp),
            'X-TC-Version': self.version,
            'X-TC-Region': self.region
        }
    
    def translate_text(self, text: str, source_lang: str = "auto", target_lang: str = "zh") -> Optional[str]:
        """翻译单个文本"""
        try:
            if not text or not text.strip():
                return text
                
            payload = {
                "SourceText": text,
                "Source": source_lang,
                "Target": target_lang,
                "ProjectId": 0
            }
            
            payload_json = json.dumps(payload)
            headers = self._create_headers(payload_json, 'TextTranslate')
            
            url = f"https://{self.endpoint}"
            response = requests.post(url, headers=headers, data=payload_json, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if 'Response' in result and 'TargetText' in result['Response']:
                    translated_text = result['Response']['TargetText']
                    logger.info("翻译成功", original=text[:50], translated=translated_text[:50])
                    return translated_text
                else:
                    logger.error("翻译响应格式错误", response=result)
                    return text
            else:
                logger.error("翻译请求失败", status_code=response.status_code, response=response.text)
                return text
                
        except Exception as e:
            logger.error("翻译异常", error=str(e), text=text[:50])
            return text
    
    def translate_batch(self, texts: List[str], source_lang: str = "auto", target_lang: str = "zh") -> List[str]:
        """批量翻译文本"""
        try:
            if not texts:
                return []
            
            # 过滤空文本
            non_empty_texts = [(i, text) for i, text in enumerate(texts) if text and text.strip()]
            if not non_empty_texts:
                return texts
            
            # 批量翻译（腾讯云支持批量翻译）
            source_texts = [text for _, text in non_empty_texts]
            
            payload = {
                "SourceTextList": source_texts,
                "Source": source_lang,
                "Target": target_lang,
                "ProjectId": 0
            }
            
            payload_json = json.dumps(payload)
            headers = self._create_headers(payload_json, 'TextTranslateBatch')
            
            url = f"https://{self.endpoint}"
            response = requests.post(url, headers=headers, data=payload_json, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                if 'Response' in result and 'TargetTextList' in result['Response']:
                    translated_texts = result['Response']['TargetTextList']
                    
                    # 将翻译结果映射回原始位置
                    final_results = texts.copy()
                    for (original_index, _), translated in zip(non_empty_texts, translated_texts):
                        final_results[original_index] = translated
                    
                    logger.info("批量翻译成功", count=len(translated_texts))
                    return final_results
                else:
                    logger.error("批量翻译响应格式错误", response=result)
                    return texts
            else:
                logger.error("批量翻译请求失败", status_code=response.status_code, response=response.text)
                return texts
                
        except Exception as e:
            logger.error("批量翻译异常", error=str(e))
            # 降级到单个翻译
            return [self.translate_text(text, source_lang, target_lang) for text in texts]


class ExcelTranslationProcessor:
    """Excel翻译处理器"""
    
    def __init__(self):
        self.translation_service = TencentTranslationService()
        self.settings = get_settings()
    
    def translate_excel_file(self, 
                           input_file_path: str, 
                           output_file_path: str,
                           text_columns: List[str] = None,
                           source_lang: str = "auto",
                           target_lang: str = "zh",
                           translation_mode: str = "add") -> Dict[str, any]:
        """
        翻译Excel文件
        
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
            logger.info("开始翻译Excel文件", input_file=input_file_path, output_file=output_file_path)
            
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
                
                logger.info("翻译列", column=column)
                
                # 获取非空文本
                texts_to_translate = df[column].fillna('').astype(str).tolist()
                
                # 批量翻译
                translated_texts = self.translation_service.translate_batch(
                    texts_to_translate, source_lang, target_lang
                )
                
                # 根据翻译模式处理结果
                if translation_mode == "add":
                    # 添加新列
                    new_column_name = f"{column}_translated"
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
            
            logger.info("Excel翻译完成", stats=translation_stats)
            return translation_stats
            
        except Exception as e:
            logger.error("Excel翻译失败", error=str(e))
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
        """创建翻译报告"""
        try:
            report_data = {
                "翻译时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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
            report_path = output_path.replace('.xlsx', '_translation_report.xlsx')
            report_df.to_excel(report_path, index=False)
            
            logger.info("翻译报告已创建", report_path=report_path)
            return report_path
            
        except Exception as e:
            logger.error("创建翻译报告失败", error=str(e))
            return ""


# 全局翻译服务实例
translation_service = TencentTranslationService()
excel_processor = ExcelTranslationProcessor()