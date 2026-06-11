#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文本回填功能模块
text_applier.py - 将翻译文本应用回 DXF 文件（替换或追加）
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import ezdxf
import structlog

logger = structlog.get_logger(__name__)

SUPPORTED_ENTITY_TYPES = ["TEXT", "MTEXT", "ATTDEF", "ATTRIB"]


class TextApplier:
    """
    翻译文本回填器
    
    支持两种模式：
      - replace: 直接替换原文本内容
      - add:     在原文本下方添加译文（保留原文）
    """

    def apply(
        self,
        dxf_file_path: str,
        output_file_path: str,
        translation_map: Dict[str, str],
        translation_mode: str = "replace",
        font_name: str = "Times New Roman",
        font_size_reduction: int = 2,
    ) -> Dict[str, Any]:
        """
        将翻译映射表应用到 DXF 文件，输出新 DXF。

        Args:
            dxf_file_path:      输入 DXF 文件路径
            output_file_path:   输出 DXF 文件路径
            translation_map:    {原文: 译文} 字典
            translation_mode:   "replace" | "add" | "newline"
            font_name:          输出字体名称
            font_size_reduction: 字号缩小量（单位与 DXF 字高一致）

        Returns:
            {
                "success": bool,
                "input_file": str,
                "output_file": str,
                "translation_count": int,
                "translated_entities": int,
                "font_name": str,
                "translation_mode": str,
                "message": str,
            }
        """
        dxf_path = Path(dxf_file_path)
        output_path = Path(output_file_path)

        logger.info(
            "text_apply_start",
            dxf=str(dxf_path),
            output=str(output_path),
            mode=translation_mode,
            font=font_name,
            reduction=font_size_reduction,
        )

        try:
            doc = ezdxf.readfile(str(dxf_path))
        except Exception as exc:
            raise RuntimeError(f"无法读取 DXF 文件: {exc}") from exc

        replace_mode = translation_mode == "replace"
        newline_mode = translation_mode == "newline"
        translated_count = 0

        def _process_space(space):
            nonlocal translated_count
            for entity in list(space):
                try:
                    if self._translate_entity(space, entity, translation_map, font_name, replace_mode, font_size_reduction, doc, newline_mode):
                        translated_count += 1
                except Exception as exc:
                    logger.debug("entity_translate_failed", error=str(exc))

        _process_space(doc.modelspace())
        for layout in doc.layouts:
            if layout.name != "Model":
                _process_space(layout)
        try:
            for block in doc.blocks:
                if not block.name.startswith("*"):
                    _process_space(block)
        except Exception as exc:
            logger.debug("block_translate_failed", error=str(exc))

        self._sanitize_materials_for_save(doc)
        doc.saveas(str(output_path))
        logger.info("text_apply_done", translated=translated_count, output=str(output_path))

        return {
            "success": True,
            "input_file": str(dxf_path),
            "output_file": str(output_path),
            "translation_count": len(translation_map),
            "translated_entities": translated_count,
            "font_name": font_name,
            "translation_mode": translation_mode,
            "message": f"成功应用 {len(translation_map)} 条翻译，翻译了 {translated_count} 个文本实体",
        }

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _smart_match(self, text: str, translation_map: Dict[str, str]) -> Optional[str]:
        """智能文本匹配：直接匹配 -> 去空格 -> 单空格 -> 去首尾空格"""
        if text in translation_map and translation_map[text].strip():
            return translation_map[text]

        strategies = [
            lambda x: re.sub(r"\s+", "", x),
            lambda x: re.sub(r"\s+", " ", x.strip()),
            lambda x: x.strip(),
        ]
        for strategy in strategies:
            src = strategy(text)
            for orig, trans in translation_map.items():
                if strategy(orig) == src and trans.strip():
                    return trans
        return None

    def _set_font(self, entity, font_name: str, doc) -> None:
        """为实体设置字体样式"""
        try:
            style_name = f"TStyle_{font_name.replace(' ', '_')}"
            if style_name not in doc.styles:
                style = doc.styles.add(style_name, font=font_name)
                style.dxf.bigfont = ""
            entity.dxf.style = style_name
        except Exception as exc:
            logger.debug("set_font_failed", error=str(exc))

    def _translate_entity(
        self,
        owner,
        entity,
        translation_map: Dict[str, str],
        font_name: str,
        replace_mode: bool,
        font_size_reduction: int,
        doc,
        newline_mode: bool = False,
    ) -> bool:
        entity_type = entity.dxftype()
        if entity_type not in SUPPORTED_ENTITY_TYPES:
            return False

        try:
            if entity_type in ("TEXT", "MTEXT"):
                original_text = entity.dxf.text
            else:
                original_text = getattr(entity.dxf, "text", None) or getattr(entity.dxf, "tag", None)

            if not original_text or not original_text.strip():
                return False

            translated = self._smart_match(original_text.strip(), translation_map)
            if not translated:
                return False

            height = float(getattr(entity.dxf, "height", None) or getattr(entity.dxf, "char_height", 2.5))

            if replace_mode:
                # 替换模式
                if entity_type in ("TEXT", "ATTDEF", "ATTRIB"):
                    entity.dxf.text = translated
                    entity.dxf.height = max(1.0, height - font_size_reduction)
                elif entity_type == "MTEXT":
                    entity.dxf.text = translated
                    entity.dxf.char_height = max(1.0, height - font_size_reduction)
                self._set_font(entity, font_name, doc)
            elif newline_mode:
                # 换行追加模式：在原文实体内部换行追加翻译
                self._append_text_newline(entity, translated, font_name, height, font_size_reduction, doc)
            else:
                # 追加模式：在原文下方插入新文本实体
                self._add_text_below(owner, entity, translated, font_name, height, font_size_reduction, doc)

            return True

        except Exception as exc:
            logger.debug("translate_entity_failed", type=entity_type, error=str(exc))
            return False

    def _append_text_newline(
        self,
        entity,
        translated_text: str,
        font_name: str,
        original_height: float,
        font_size_reduction: int,
        doc,
    ) -> None:
        """在原文实体内部换行追加翻译文本（保留原文）。"""
        try:
            entity_type = entity.dxftype()
            if entity_type == "MTEXT":
                original = entity.dxf.text
                # MTEXT supports \\P for paragraph/newline
                entity.dxf.text = f"{original}\\P{translated_text}"
                entity.dxf.char_height = max(1.0, original_height - font_size_reduction)
                self._set_font(entity, font_name, doc)
            elif entity_type in ("TEXT", "ATTDEF", "ATTRIB"):
                original = entity.dxf.text
                # TEXT uses \\n for newline in some viewers; use MTEXT replacement for better support
                entity.dxf.text = f"{original}\\n{translated_text}"
                entity.dxf.height = max(1.0, original_height - font_size_reduction)
                self._set_font(entity, font_name, doc)
        except Exception as exc:
            logger.debug("append_text_newline_failed", error=str(exc))

    def _add_text_below(
        self,
        owner,
        original_entity,
        translated_text: str,
        font_name: str,
        original_height: float,
        font_size_reduction: int,
        doc,
    ) -> None:
        """在原文本下方添加翻译文本（红色）"""
        try:
            insert_point = getattr(original_entity.dxf, "insert", (0, 0, 0))
            layer = getattr(original_entity.dxf, "layer", "0")
            rotation = float(getattr(original_entity.dxf, "rotation", 0))

            offset_y = -original_height * 1.2
            rotation_rad = rotation * (math.pi / 180.0)
            dx = offset_y * math.sin(rotation_rad)
            dy = offset_y * math.cos(rotation_rad)

            new_x = float(insert_point[0]) + dx
            new_y = float(insert_point[1]) + dy
            new_z = float(insert_point[2]) if len(insert_point) > 2 else 0.0

            style_name = f"TStyle_{font_name.replace(' ', '_')}"
            if style_name not in doc.styles:
                s = doc.styles.add(style_name, font=font_name)
                s.dxf.bigfont = ""

            attribs = {
                "insert": (new_x, new_y, new_z),
                "height": max(1.0, original_height - font_size_reduction),
                "layer": layer,
                "rotation": rotation,
                "color": 1,  # 红色
                "style": style_name,
            }
            owner.add_text(translated_text, dxfattribs=attribs)
        except Exception as exc:
            logger.debug("add_text_below_failed", error=str(exc))

    def _sanitize_materials_for_save(self, doc) -> None:
        """Drop dangling material references before saving converted DXF files."""
        invalid_names = []
        for name, entry in list(doc.materials.object_dict.items()):
            material = entry
            if isinstance(entry, str):
                material = doc.entitydb.get(entry)
            if material is None or getattr(material, "dxftype", lambda: None)() != "MATERIAL":
                doc.materials.object_dict.discard(name)
                invalid_names.append(name)

        if invalid_names:
            logger.info("text_apply_sanitized_materials", removed=invalid_names)
            doc.header["$CMATERIAL"] = "0"

        doc.materials.create_required_entries()
