#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CAD文本处理服务 - 集成原始文本提取和回填逻辑
CAD Text Processing Service - Integrated Original Text Extraction and Backfill Logic

将原始的extract_texts.py和回填.py逻辑集成到Web服务中
"""

import os
import sys
import subprocess
import pandas as pd
import ezdxf
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any
import structlog
import tempfile
import shutil
from app.config import get_settings
from app.functions.dwg_converter import DWGConverter

logger = structlog.get_logger(__name__)

class CADTextProcessor:
    """CAD文本处理器 - 集成提取和回填功能"""
    
    def __init__(self):
        self.logger = logger
        self.settings = get_settings()
        
    def extract_texts_to_excel(self, dxf_file_path: str, output_dir: str) -> Dict[str, Any]:
        """
        从DXF文件提取文本并导出到Excel
        集成自extract_texts.py的逻辑
        
        Args:
            dxf_file_path: DXF文件路径
            output_dir: 输出目录
            
        Returns:
            Dict包含提取结果信息
        """
        try:
            dxf_path = Path(dxf_file_path)
            output_path = Path(output_dir)
            
            self.logger.info("开始提取DXF文本", file_path=str(dxf_path))
            
            # 读取DXF文件
            try:
                doc = ezdxf.readfile(str(dxf_path))
            except Exception as e:
                raise Exception(f"无法读取DXF文件: {str(e)}")
            
            # 提取文本实体
            texts = []
            
            # 从模型空间提取
            msp = doc.modelspace()
            texts.extend(self._extract_texts_from_space(msp, "ModelSpace"))
            
            # 从图纸空间提取
            for layout in doc.layouts:
                if layout.name != 'Model':
                    texts.extend(self._extract_texts_from_space(layout, f"PaperSpace_{layout.name}"))
            
            # 从块定义提取
            try:
                for block in doc.blocks:
                    block_name = block.name
                    if not block_name.startswith('*'):  # 跳过匿名块
                        texts.extend(self._extract_texts_from_space(block, f"Block_{block_name}"))
            except Exception as e:
                self.logger.debug(f"提取块定义文本失败: {str(e)}")
            
            self.logger.info(f"提取到 {len(texts)} 条文本")
            
            if not texts:
                return {
                    "success": True,
                    "input_file": str(dxf_path),
                    "output_file": None,
                    "texts_count": 0,
                    "message": "未提取到文本内容"
                }
            
            # 创建Excel文件
            excel_filename = f"{dxf_path.stem}_extracted_texts.xlsx"
            excel_path = output_path / excel_filename
            
            # 转换为DataFrame并导出
            df = pd.DataFrame(texts)
            df.to_excel(str(excel_path), index=False, engine='openpyxl')
            
            self.logger.info(f"文本提取完成，保存到: {excel_path}")
            
            return {
                "success": True,
                "input_file": str(dxf_path),
                "output_file": str(excel_path),
                "texts_count": len(texts),
                "texts": texts,
                "message": f"成功提取 {len(texts)} 条文本"
            }
            
        except Exception as e:
            self.logger.error("文本提取失败", error=str(e))
            raise Exception(f"文本提取失败: {str(e)}")
    
    def _extract_texts_from_space(self, space, space_name: str) -> List[Dict[str, Any]]:
        """从指定空间提取文本实体"""
        texts = []
        
        for entity in space:
            try:
                text_info = self._extract_text_from_entity(entity, space_name)
                if text_info:
                    texts.append(text_info)
            except Exception as e:
                self.logger.debug(f"提取实体文本失败: {str(e)}")
                continue
        
        return texts
    
    def _extract_text_from_entity(self, entity, space_name: str) -> Optional[Dict[str, Any]]:
        """从单个实体提取文本信息"""
        entity_type = entity.dxftype()
        
        # 支持的文本实体类型
        if entity_type not in ['TEXT', 'MTEXT', 'ATTDEF', 'ATTRIB']:
            return None
        
        try:
            # 提取文本内容
            text_content = None
            if entity_type == 'TEXT':
                text_content = entity.dxf.text
            elif entity_type == 'MTEXT':
                text_content = entity.dxf.text
            elif entity_type in ['ATTDEF', 'ATTRIB']:
                text_content = getattr(entity.dxf, 'text', None) or getattr(entity.dxf, 'tag', None)
            
            if not text_content or not text_content.strip():
                return None
            
            # 获取位置信息
            insert_point = getattr(entity.dxf, 'insert', (0, 0, 0))
            
            # 获取其他属性
            height = getattr(entity.dxf, 'height', None) or getattr(entity.dxf, 'char_height', 2.5)
            layer = getattr(entity.dxf, 'layer', '0')
            rotation = getattr(entity.dxf, 'rotation', 0)
            
            return {
                "序号": None,  # 将在Excel中自动填充
                "原文": text_content.strip(),
                "译文": "",  # 空白，等待用户填写或AI翻译
                "实体类型": entity_type,
                "空间": space_name,
                "图层": layer,
                "X坐标": round(insert_point[0], 3),
                "Y坐标": round(insert_point[1], 3),
                "Z坐标": round(insert_point[2], 3),
                "高度": round(height, 3),
                "旋转角度": round(rotation, 3)
            }
            
        except Exception as e:
            self.logger.debug(f"提取{entity_type}实体文本失败: {str(e)}")
            return None
    
    def apply_translation_to_dxf(
        self,
        dxf_file_path: str,
        excel_file_path: Optional[str] = None,
        output_file_path: str = "",
        font_name: str = "Times New Roman",
        translation_mode: str = "add",
        font_size_reduction: int = 4,
        translation_map: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        将Excel中的翻译应用到DXF文件
        集成自回填.py的逻辑
        
        Args:
            dxf_file_path: DXF文件路径
            excel_file_path: Excel翻译文件路径
            output_dir: 输出目录
            font_name: 字体名称
            translation_mode: 翻译模式 (add/replace)
            font_size_reduction: 字体大小减少值
            
        Returns:
            Dict包含应用结果信息
        """
        try:
            dxf_path = Path(dxf_file_path)
            
            # 处理输出路径
            if output_file_path:
                output_path = Path(output_file_path)
            else:
                # 兼容旧的output_dir参数
                output_dir = excel_file_path if excel_file_path else str(dxf_path.parent)
                output_path = Path(output_dir) / f"translated_{dxf_path.name}"
            
            self.logger.info("开始应用翻译到DXF", 
                           dxf_file=str(dxf_path),
                           output_file=str(output_path),
                           mode=translation_mode)
            
            # 加载翻译映射表
            if translation_map is None:
                if not excel_file_path:
                    raise Exception("必须提供excel_file_path或translation_map参数")
                excel_path = Path(excel_file_path)
                translation_map = self._load_translation_map(str(excel_path))
                if not translation_map:
                    raise Exception("翻译映射表为空或加载失败")
            
            self.logger.info(f"加载了 {len(translation_map)} 条翻译映射")
            
            # 读取DXF文件
            try:
                doc = ezdxf.readfile(str(dxf_path))
            except Exception as e:
                raise Exception(f"无法读取DXF文件: {str(e)}")
            
            # 应用翻译
            replace_mode = (translation_mode == "replace")
            translated_count = 0
            
            # 处理模型空间
            msp = doc.modelspace()
            translated_count += self._translate_space_entities(
                msp, translation_map, font_name, replace_mode, font_size_reduction, doc
            )
            
            # 处理图纸空间
            for layout in doc.layouts:
                if layout.name != 'Model':
                    translated_count += self._translate_space_entities(
                        layout, translation_map, font_name, replace_mode, font_size_reduction, doc
                    )
            
            # 处理块定义
            try:
                for block in doc.blocks:
                    block_name = block.name
                    if not block_name.startswith('*'):  # 跳过匿名块
                        translated_count += self._translate_space_entities(
                            block, translation_map, font_name, replace_mode, font_size_reduction, doc
                        )
            except Exception as e:
                self.logger.debug(f"处理块定义翻译失败: {str(e)}")
            
            # 保存翻译后的文件
            doc.saveas(str(output_path))
            
            self.logger.info(f"翻译应用完成，共翻译 {translated_count} 个文本实体")
            
            return {
                "success": True,
                "input_file": str(dxf_path),
                "output_file": str(output_path),
                "translation_count": len(translation_map),
                "translated_entities": translated_count,
                "font_name": font_name,
                "translation_mode": translation_mode,
                "message": f"成功应用 {len(translation_map)} 条翻译，翻译了 {translated_count} 个文本实体"
            }
            
        except Exception as e:
            self.logger.error("翻译应用失败", error=str(e))
            raise Exception(f"翻译应用失败: {str(e)}")
    
    def _load_translation_map(self, excel_path: str) -> Dict[str, str]:
        """从Excel加载翻译映射表"""
        try:
            df = pd.read_excel(excel_path)
            self.logger.info(f"Excel文件读取成功，共 {len(df)} 行数据")
            
            translation_map = {}
            for _, row in df.iterrows():
                # 智能检测列索引，支持不同的Excel格式
                if len(row) >= 3:
                    # 3列格式：序号、原文、译文
                    original = str(row.iloc[1]).strip()  # 原文（第2列）
                    translated = row.iloc[2]  # 译文（第3列）
                elif len(row) >= 2:
                    # 2列格式：原文、译文
                    original = str(row.iloc[0]).strip()  # 原文（第1列）
                    translated = row.iloc[1]  # 译文（第2列）
                else:
                    continue
                
                # 检查翻译是否有效
                if pd.notna(translated):
                    translated_str = str(translated).strip()
                    invalid_values = ['', 'nan', 'none', 'null', 'n/a', 'na']
                    if translated_str and translated_str.lower() not in invalid_values:
                        translation_map[original] = translated_str
            
            self.logger.info(f"翻译映射表加载成功，共 {len(translation_map)} 条有效翻译映射")
            return translation_map
            
        except Exception as e:
            self.logger.error(f"读取Excel文件时出错: {str(e)}")
            raise Exception(f"读取Excel文件时出错: {str(e)}")
    
    def _translate_space_entities(
        self,
        space,
        translation_map: Dict[str, str],
        font_name: str,
        replace_mode: bool,
        font_size_reduction: int,
        doc
    ) -> int:
        """翻译指定空间中的文本实体"""
        translated_count = 0
        
        for entity in space:
            try:
                if self._translate_text_entity(
                    space, entity, translation_map, font_name, replace_mode, font_size_reduction, doc
                ):
                    translated_count += 1
            except Exception as e:
                self.logger.debug(f"翻译实体失败: {str(e)}")
                continue
        
        return translated_count
    
    def _translate_text_entity(
        self,
        owner,
        entity,
        translation_map: Dict[str, str],
        font_name: str,
        replace_mode: bool,
        font_size_reduction: int,
        doc
    ) -> bool:
        """翻译单个文本实体"""
        entity_type = entity.dxftype()
        
        # 只处理文本实体
        if entity_type not in ['TEXT', 'MTEXT', 'ATTDEF', 'ATTRIB']:
            return False
        
        try:
            # 提取原文本
            original_text = None
            if entity_type == 'TEXT':
                original_text = entity.dxf.text
            elif entity_type == 'MTEXT':
                original_text = entity.dxf.text
            elif entity_type in ['ATTDEF', 'ATTRIB']:
                original_text = getattr(entity.dxf, 'text', None) or getattr(entity.dxf, 'tag', None)
            
            if not original_text or not original_text.strip():
                return False
            
            # 查找翻译
            translated_text = self._smart_translate(original_text.strip(), translation_map)
            if not translated_text:
                return False
            
            self.logger.debug(f"找到翻译: '{original_text}' -> '{translated_text}'")
            
            # 获取文本高度
            height = getattr(entity.dxf, 'height', None) or getattr(entity.dxf, 'char_height', 2.5)
            
            if replace_mode:
                # 替换模式：直接修改原文本
                if entity_type == 'TEXT':
                    entity.dxf.text = translated_text
                    entity.dxf.height = max(1, height - font_size_reduction)
                elif entity_type == 'MTEXT':
                    entity.dxf.text = translated_text
                    entity.dxf.char_height = max(1, height - font_size_reduction)
                elif entity_type in ['ATTDEF', 'ATTRIB']:
                    if hasattr(entity.dxf, 'text'):
                        entity.dxf.text = translated_text
                    entity.dxf.height = max(1, height - font_size_reduction)
                
                # 设置字体样式
                self._set_font_style(entity, font_name, doc)
                
            else:
                # 添加模式：在原文本下方添加翻译
                self._add_translation_text(
                    owner, entity, translated_text, font_name, height, font_size_reduction, doc
                )
            
            return True
            
        except Exception as e:
            self.logger.debug(f"翻译{entity_type}实体失败: {str(e)}")
            return False
    
    def _smart_translate(self, text: str, translation_map: Dict[str, str]) -> Optional[str]:
        """智能翻译函数，支持多种空格处理策略"""
        if not text or not isinstance(text, str):
            return None
        
        # 首先尝试直接匹配
        if text in translation_map:
            translated = translation_map[text]
            if translated and translated.strip():
                return translated
        
        # 定义标准化方法
        normalization_methods = [
            ('移除空格', lambda x: re.sub(r'\s+', '', x)),
            ('单空格', lambda x: re.sub(r'\s+', ' ', x.strip())),
            ('去首尾空格', lambda x: x.strip())
        ]
        
        # 尝试各种标准化方法
        for method_name, method_func in normalization_methods:
            normalized_text = method_func(text)
            
            for original, translated in translation_map.items():
                if method_func(original) == normalized_text:
                    if translated and translated.strip():
                        self.logger.debug(f"智能翻译匹配: '{text}' -> '{translated}' (通过{method_name})")
                        return translated
        
        return None
    
    def _set_font_style(self, entity, font_name: str, doc):
        """设置文本实体的字体样式"""
        try:
            style_name = f"TranslationStyle_{font_name.replace(' ', '_')}"
            
            if style_name not in doc.styles:
                style = doc.styles.add(style_name, font=font_name)
                style.dxf.bigfont = ""
            
            entity.dxf.style = style_name
            
        except Exception as e:
            self.logger.debug(f"设置字体样式失败: {str(e)}")
    
    def _add_translation_text(
        self,
        owner,
        original_entity,
        translated_text: str,
        font_name: str,
        original_height: float,
        font_size_reduction: int,
        doc
    ):
        """在原文本下方添加翻译文本"""
        try:
            # 获取原文本属性
            insert_point = getattr(original_entity.dxf, 'insert', (0, 0, 0))
            layer = getattr(original_entity.dxf, 'layer', '0')
            rotation = getattr(original_entity.dxf, 'rotation', 0)
            
            # 计算偏移位置
            offset_y = -original_height * 1.2  # 向下偏移
            
            # 根据旋转角度调整偏移量
            import math
            rotation_rad = rotation * (math.pi / 180.0)
            dx = offset_y * math.sin(rotation_rad)
            dy = offset_y * math.cos(rotation_rad)
            
            new_x = insert_point[0] + dx
            new_y = insert_point[1] + dy
            new_z = insert_point[2]
            
            # 创建翻译文本
            attribs = {
                'text': translated_text,
                'insert': (new_x, new_y, new_z),
                'height': max(1, original_height - font_size_reduction),
                'layer': layer,
                'rotation': rotation,
                'color': 1  # 红色以示区别
            }
            
            # 设置字体样式
            style_name = f"TranslationStyle_{font_name.replace(' ', '_')}"
            if style_name not in doc.styles:
                style = doc.styles.add(style_name, font=font_name)
                style.dxf.bigfont = ""
            attribs['style'] = style_name
            
            # 添加文本实体
            owner.add_text(**attribs)
            
        except Exception as e:
            self.logger.debug(f"添加翻译文本失败: {str(e)}")

    def _convert_dwg_to_dxf(
        self,
        dwg_file_path: str,
        temp_dir: Path,
        backend_override: Optional[str] = None,
    ) -> str:
        """Convert DWG to DXF using configured backend."""
        converter = DWGConverter(
            converter_backend=self.settings.DWG_CONVERTER_BACKEND,
            dwg_auto_backends=self.settings.DWG_AUTO_BACKENDS,
            dwg_disabled_backends=self.settings.DWG_DISABLED_BACKENDS,
            oda_path=self.settings.ODA_FILE_CONVERTER_PATH,
            oda_output_version=self.settings.ODA_OUTPUT_VERSION,
            oda_output_format=self.settings.ODA_OUTPUT_FORMAT,
            cad_converter_timeout=self.settings.CAD_CONVERTER_TIMEOUT,
            libredwg_dwg2dxf_path=self.settings.LIBREDWG_DWG2DXF_PATH,
            libredwg_install_dir=self.settings.LIBREDWG_INSTALL_DIR,
            libredwg_download_url=self.settings.LIBREDWG_DOWNLOAD_URL,
            libredwg_auto_download=self.settings.LIBREDWG_AUTO_DOWNLOAD,
        )
        return converter.convert(
            dwg_file_path=str(dwg_file_path),
            output_dir=temp_dir,
            backend_override=backend_override,
        )

    async def process_cad_file(
        self,
        input_file: str,
        target_language: str = "en",
        extract_only: bool = False
    ) -> Dict[str, Any]:
        """
        处理CAD文件的完整流程
        
        Args:
            input_file: 输入CAD文件路径
            target_language: 目标翻译语言
            extract_only: 是否仅提取文本不翻译
            
        Returns:
            处理结果字典
        """
        import uuid
        import time
        from .alibaba_ai_translation_service import alibaba_ai_translation_service
        
        start_time = time.time()
        task_id = str(uuid.uuid4())[:8]
        
        try:
            self.logger.info("开始处理CAD文件", 
                           file=input_file, 
                           target_language=target_language,
                           extract_only=extract_only,
                           task_id=task_id)
            
            # 创建临时工作目录
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                # 如果是DWG文件，按配置转换为DXF
                input_path = Path(input_file)
                if input_path.suffix.lower() == '.dwg':
                    dxf_file = self._convert_dwg_to_dxf(input_file, temp_path)
                else:
                    dxf_file = input_file
                
                # 1. 提取文本到Excel
                extract_result = self.extract_texts_to_excel(
                    dxf_file_path=dxf_file,
                    output_dir=str(temp_path)
                )
                
                excel_file = extract_result.get('excel_file')
                text_count = extract_result.get('text_count', 0)
                
                result = {
                    'task_id': task_id,
                    'text_count': text_count,
                    'excel_file': excel_file,
                    'processing_time': None,
                    'translation_count': 0,
                    'translated_cad_file': None
                }
                
                # 如果仅提取文本，直接返回
                if extract_only:
                    result['processing_time'] = time.time() - start_time
                    self.logger.info("文本提取完成", task_id=task_id, text_count=text_count)
                    return result
                
                # 2. 翻译Excel中的文本
                if excel_file and Path(excel_file).exists():
                    try:
                        # 读取Excel文件
                        df = pd.read_excel(excel_file)
                        
                        if '原文' in df.columns:
                            translation_count = 0
                            translations = []
                            
                            for idx, row in df.iterrows():
                                original_text = str(row['原文']).strip()
                                if original_text and original_text != 'nan':
                                    try:
                                        # 调用翻译服务
                                        translated_text = alibaba_ai_translation_service.translate_text(
                                            text=original_text,
                                            target_lang=target_language
                                        )
                                        translations.append(translated_text)
                                        translation_count += 1
                                    except Exception as e:
                                        self.logger.warning("翻译失败", text=original_text, error=str(e))
                                        translations.append(original_text)  # 翻译失败时保持原文
                                else:
                                    translations.append('')
                            
                            # 添加翻译列
                            df['译文'] = translations
                            
                            # 保存更新后的Excel
                            df.to_excel(excel_file, index=False)
                            
                            result['translation_count'] = translation_count
                            
                            # 3. 将翻译应用到CAD文件
                            if translation_count > 0:
                                translated_dxf = temp_path / f"translated_{input_path.name}"
                                
                                translate_result = self.apply_translation_to_dxf(
                                    dxf_file_path=dxf_file,
                                    excel_file_path=excel_file,
                                    output_file_path=str(translated_dxf),
                                    font_name="Arial",
                                    font_size_reduction=0,
                                    translation_mode="replace"
                                )
                                
                                if translate_result.get('success'):
                                    result['translated_cad_file'] = str(translated_dxf)
                                    self.logger.info("CAD文件翻译完成", 
                                                   task_id=task_id, 
                                                   translation_count=translation_count)
                    
                    except Exception as e:
                        self.logger.error("翻译处理失败", task_id=task_id, error=str(e))
                        # 即使翻译失败，也返回提取的文本
                
                result['processing_time'] = time.time() - start_time
                return result
                
        except Exception as e:
            self.logger.error("CAD文件处理失败", task_id=task_id, error=str(e))
            raise Exception(f"处理失败: {str(e)}")

# 创建全局实例
cad_text_processor = CADTextProcessor()
