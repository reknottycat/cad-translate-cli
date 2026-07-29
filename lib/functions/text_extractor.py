#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文本提取功能模块
text_extractor.py - 从 DXF 文件中提取文本并导出到 Excel
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import ezdxf
import pandas as pd
import structlog

logger = structlog.get_logger(__name__)

# 支持的文本实体类型
SUPPORTED_ENTITY_TYPES = ["TEXT", "MTEXT", "ATTDEF", "ATTRIB"]


class TextExtractor:
    """从 DXF 文件提取文本实体并导出为 Excel"""

    def extract_to_excel(self, dxf_file_path: str, output_dir: str) -> Dict[str, Any]:
        """
        从 DXF 文件提取文本并保存到 Excel。

        Args:
            dxf_file_path: DXF 文件路径
            output_dir:    输出目录

        Returns:
            {
                "success": bool,
                "input_file": str,
                "output_file": str | None,
                "texts_count": int,
                "texts": list[dict],
                "message": str,
            }
        """
        dxf_path = Path(dxf_file_path)
        output_path = Path(output_dir)

        logger.info("text_extract_start", file=str(dxf_path))

        try:
            doc = ezdxf.readfile(str(dxf_path))
        except Exception as exc:
            raise RuntimeError(f"无法读取 DXF 文件: {exc}") from exc

        texts: List[Dict[str, Any]] = []

        # 模型空间
        texts.extend(self._extract_from_space(doc.modelspace(), "ModelSpace"))

        # 图纸空间
        for layout in doc.layouts:
            if layout.name != "Model":
                texts.extend(self._extract_from_space(layout, f"PaperSpace_{layout.name}"))

        # 块定义
        try:
            for block in doc.blocks:
                if not block.name.startswith("*"):
                    texts.extend(self._extract_from_space(block, f"Block_{block.name}"))
        except Exception as exc:
            logger.debug("block_extract_failed", error=str(exc))

        # 添加序号
        for i, t in enumerate(texts, start=1):
            t["序号"] = i

        logger.info("text_extract_done", count=len(texts))

        if not texts:
            return {
                "success": True,
                "input_file": str(dxf_path),
                "output_file": None,
                "texts_count": 0,
                "texts": [],
                "message": "未提取到文本内容",
            }

        excel_filename = f"{dxf_path.stem}_extracted_texts.xlsx"
        excel_path = output_path / excel_filename
        df = pd.DataFrame(texts)
        df.to_excel(str(excel_path), index=False, engine="openpyxl")

        logger.info("text_extract_excel_saved", path=str(excel_path))
        return {
            "success": True,
            "input_file": str(dxf_path),
            "output_file": str(excel_path),
            "texts_count": len(texts),
            "texts": texts,
            "message": f"成功提取 {len(texts)} 条文本",
        }

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _extract_from_space(self, space, space_name: str) -> List[Dict[str, Any]]:
        texts = []
        for entity in space:
            try:
                info = self._extract_entity(entity, space_name)
                if info:
                    texts.append(info)
            except Exception as exc:
                logger.debug("entity_extract_failed", error=str(exc))
        return texts

    def _extract_entity(self, entity, space_name: str) -> Optional[Dict[str, Any]]:
        entity_type = entity.dxftype()
        if entity_type not in SUPPORTED_ENTITY_TYPES:
            return None

        try:
            if entity_type == "TEXT":
                text_content = entity.dxf.text
            elif entity_type == "MTEXT":
                text_content = entity.dxf.text
            else:
                text_content = getattr(entity.dxf, "text", None) or getattr(entity.dxf, "tag", None)

            if not text_content or not text_content.strip():
                return None

            insert_point = getattr(entity.dxf, "insert", (0, 0, 0))
            height = getattr(entity.dxf, "height", None) or getattr(entity.dxf, "char_height", 2.5)
            layer = getattr(entity.dxf, "layer", "0")
            rotation = getattr(entity.dxf, "rotation", 0)

            return {
                "序号": None,
                "原文": text_content.strip(),
                "译文": "",
                "实体类型": entity_type,
                "空间": space_name,
                "图层": layer,
                "X坐标": round(float(insert_point[0]), 3),
                "Y坐标": round(float(insert_point[1]), 3),
                "Z坐标": round(float(insert_point[2]), 3),
                "高度": round(float(height), 3),
                "旋转角度": round(float(rotation), 3),
            }
        except Exception as exc:
            logger.debug("entity_parse_failed", type=entity_type, error=str(exc))
            return None
