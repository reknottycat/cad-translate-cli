#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CAD 翻译管道编排器
pipeline.py - 将工作流引擎与具体功能模块绑定，供 cad_pipeline_service 调用

核心思路：
  1. 创建 WorkflowRunner 实例
  2. 注册 4 个功能处理函数（convert / extract / translate / apply）
  3. 提供 run_pipeline() 方法，接收上下文并执行工作流
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from app.workflow.engine import WorkflowRunner, StepResult
from app.functions.dwg_converter import DWGConverter
from app.functions.text_extractor import TextExtractor
from app.functions.translator import Translator
from app.functions.text_applier import TextApplier

logger = structlog.get_logger(__name__)

# 默认工作流文件路径（相对于 repo 根目录）
_WORKFLOW_FILE = Path(__file__).resolve().parents[4] / ".agents" / "workflows" / "cad_translation_workflow.md"


class CADPipeline:
    """
    CAD 翻译管道编排器
    
    将 WorkflowRunner 与四个功能模块绑定，并提供高层 run() 接口。
    """

    def __init__(
        self,
        dwg_converter: Optional[DWGConverter] = None,
        text_extractor: Optional[TextExtractor] = None,
        translator: Optional[Translator] = None,
        text_applier: Optional[TextApplier] = None,
        workflow_file: Optional[str] = None,
    ) -> None:
        self._converter = dwg_converter or DWGConverter()
        self._extractor = text_extractor or TextExtractor()
        self._translator = translator or Translator()
        self._applier = text_applier or TextApplier()
        self._workflow_file = workflow_file or str(_WORKFLOW_FILE)

        self._runner = WorkflowRunner()
        self._register_handlers()

    # ------------------------------------------------------------------
    # 注册处理函数
    # ------------------------------------------------------------------

    def _register_handlers(self) -> None:
        self._runner.register("dwg_converter", self._handle_convert)
        self._runner.register("text_extractor", self._handle_extract)
        self._runner.register("translator", self._handle_translate)
        self._runner.register("text_applier", self._handle_apply)

    # ------------------------------------------------------------------
    # 各步骤处理函数（context in / context out）
    # ------------------------------------------------------------------

    def _handle_convert(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """步骤1：DWG -> DXF 转换"""
        input_file = ctx.get("input_file", "")
        task_dir = Path(ctx.get("task_dir", "."))
        backend = ctx.get("converter_backend", "dxf_only")

        input_path = Path(input_file)
        if input_path.suffix.lower() == ".dxf":
            logger.info("pipeline_convert_skipped", reason="already_dxf", file=input_file)
            return {"dxf_file": input_file}

        dxf_path = self._converter.convert(input_file, task_dir, backend_override=backend)
        return {"dxf_file": dxf_path}

    def _handle_extract(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """步骤2：从 DXF 提取文本到 Excel"""
        dxf_file = ctx.get("dxf_file", ctx.get("input_file", ""))
        task_dir = ctx.get("task_dir", ".")

        result = self._extractor.extract_to_excel(dxf_file, task_dir)
        return {
            "excel_file": result.get("output_file"),
            "texts": result.get("texts", []),
            "texts_count": result.get("texts_count", 0),
        }

    def _handle_translate(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """步骤3：翻译 Excel 并构建翻译映射表"""
        excel_file = ctx.get("excel_file")
        target_lang = ctx.get("target_language", "en")

        if not excel_file or not Path(excel_file).exists():
            logger.warning("pipeline_translate_skipped", reason="no_excel_file")
            return {"translation_map": {}}

        # 如果设置了翻译功能，先翻译 Excel
        try:
            self._translator.translate_excel(excel_file, target_lang=target_lang)
        except RuntimeError:
            # translation_func 未配置（手动翻译场景），跳过
            logger.info("pipeline_translate_manual", reason="no_translation_func_configured")

        # 从 Excel 读取翻译映射
        translation_map = self._translator.build_translation_map_from_excel(excel_file)
        return {"translation_map": translation_map}

    def _handle_apply(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """步骤4：将翻译回填到 DXF"""
        dxf_file = ctx.get("dxf_file", ctx.get("input_file", ""))
        task_dir = Path(ctx.get("task_dir", "."))
        translation_map = ctx.get("translation_map", {})
        translation_mode = ctx.get("translation_mode", "replace")
        font_name = ctx.get("font_name", "Times New Roman")
        font_size_reduction = ctx.get("font_size_reduction", 2)

        if not translation_map:
            raise ValueError("翻译映射表为空，无法执行回填。")

        output_file = task_dir / f"translated_{Path(dxf_file).name}"
        result = self._applier.apply(
            dxf_file_path=dxf_file,
            output_file_path=str(output_file),
            translation_map=translation_map,
            translation_mode=translation_mode,
            font_name=font_name,
            font_size_reduction=font_size_reduction,
        )
        return {
            "output_file": result["output_file"],
            "translated_entities": result["translated_entities"],
        }

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def run(
        self,
        context: Dict[str, Any],
        stop_on_error: bool = True,
        steps_override: Optional[List[str]] = None,
        workflow_file: Optional[str] = None,
    ) -> List[StepResult]:
        """
        执行完整管道。

        Args:
            context:        执行上下文（见工作流文件中的 Context 变量说明）
            stop_on_error:  遇到错误时是否停止
            steps_override: 若提供，则覆盖工作流文件中的步骤列表直接按此运行
            workflow_file:  覆盖默认工作流文件路径

        Returns:
            StepResult 列表
        """
        if steps_override:
            return self._runner.run_steps(steps_override, context, stop_on_error=stop_on_error)
        wf_file = workflow_file or self._workflow_file
        return self._runner.run(wf_file, context, stop_on_error=stop_on_error)

    def run_apply_only(
        self,
        dxf_file: str,
        task_dir: str,
        translation_map: Dict[str, str],
        translation_mode: str = "replace",
        font_name: str = "Times New Roman",
        font_size_reduction: int = 2,
    ) -> Dict[str, Any]:
        """
        仅执行回填步骤（用于用户手动翻译完 Excel 后调用）。

        Returns:
            apply 步骤的 context 更新字典
        """
        ctx = {
            "dxf_file": dxf_file,
            "task_dir": task_dir,
            "translation_map": translation_map,
            "translation_mode": translation_mode,
            "font_name": font_name,
            "font_size_reduction": font_size_reduction,
        }
        return self._handle_apply(ctx)


# 全局单例（延迟初始化，依赖注入时使用）
_default_pipeline: Optional[CADPipeline] = None


def get_pipeline() -> CADPipeline:
    """获取全局 CADPipeline 单例"""
    global _default_pipeline
    if _default_pipeline is None:
        _default_pipeline = CADPipeline()
    return _default_pipeline
