#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Excel处理服务
Excel Processing Service
"""

import pandas as pd
from pathlib import Path
from typing import List, Dict, Any, Optional
import structlog

logger = structlog.get_logger(__name__)

class ExcelProcessor:
    """Excel文件处理器"""
    
    def __init__(self):
        """初始化Excel处理器"""
        logger.info("阿里百炼云Excel处理器初始化完成")
    
    def create_extraction_excel(
        self, 
        texts: List[Dict[str, Any]], 
        output_file: str
    ) -> Dict[str, Any]:
        """
        创建文本提取结果的Excel文件
        
        Args:
            texts: 提取的文本列表
            output_file: 输出Excel文件路径
            
        Returns:
            处理结果
        """
        try:
            # 创建DataFrame
            df = pd.DataFrame(texts)
            
            # 保存到Excel
            df.to_excel(output_file, index=False, engine='openpyxl')
            
            logger.info("Excel文件创建成功", 
                       output_file=output_file, 
                       text_count=len(texts))
            
            return {
                "success": True,
                "message": f"成功创建Excel文件，包含 {len(texts)} 条记录",
                "file_path": output_file,
                "record_count": len(texts)
            }
            
        except Exception as e:
            logger.error("Excel文件创建失败", error=str(e))
            return {
                "success": False,
                "message": f"Excel文件创建失败: {str(e)}",
                "file_path": None,
                "record_count": 0
            }
    
    def read_excel_for_translation(self, excel_file: str) -> Dict[str, Any]:
        """
        读取Excel文件用于翻译
        
        Args:
            excel_file: Excel文件路径
            
        Returns:
            读取结果和数据
        """
        try:
            df = pd.read_excel(excel_file, engine='openpyxl')
            
            # 转换为字典列表
            records = df.to_dict('records')
            
            logger.info("Excel文件读取成功", 
                       excel_file=excel_file, 
                       record_count=len(records))
            
            return {
                "success": True,
                "message": f"成功读取 {len(records)} 条记录",
                "data": records,
                "record_count": len(records)
            }
            
        except Exception as e:
            logger.error("Excel文件读取失败", error=str(e))
            return {
                "success": False,
                "message": f"Excel文件读取失败: {str(e)}",
                "data": [],
                "record_count": 0
            }
    
    def save_translated_excel(
        self, 
        translated_data: List[Dict[str, Any]], 
        output_file: str
    ) -> Dict[str, Any]:
        """
        保存翻译后的Excel文件
        
        Args:
            translated_data: 翻译后的数据
            output_file: 输出文件路径
            
        Returns:
            保存结果
        """
        try:
            df = pd.DataFrame(translated_data)
            df.to_excel(output_file, index=False, engine='openpyxl')
            
            logger.info("翻译Excel文件保存成功", 
                       output_file=output_file, 
                       record_count=len(translated_data))
            
            return {
                "success": True,
                "message": f"成功保存翻译结果，包含 {len(translated_data)} 条记录",
                "file_path": output_file,
                "record_count": len(translated_data)
            }
            
        except Exception as e:
            logger.error("翻译Excel文件保存失败", error=str(e))
            return {
                "success": False,
                "message": f"翻译Excel文件保存失败: {str(e)}",
                "file_path": None,
                "record_count": 0
            }

# 创建全局实例
excel_processor = ExcelProcessor()