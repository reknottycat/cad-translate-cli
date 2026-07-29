#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工作流执行引擎
engine.py - 读取工作流定义并按步骤执行对应的功能模块

工作流定义格式（YAML frontmatter + Markdown）：
---
name: cad_translation_pipeline
description: CAD文件翻译完整工作流
steps:
  - id: convert
    function: dwg_converter
    enabled: true
    description: 将 DWG 文件转换为 DXF
  - id: extract
    function: text_extractor
    enabled: true
    description: 从 DXF 文件提取文本到 Excel
  - id: translate
    function: translator
    enabled: true
    description: 调用翻译服务翻译 Excel 中的文本
  - id: apply
    function: text_applier
    enabled: true
    description: 将翻译结果回填到 DXF 文件
---
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import structlog

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

logger = structlog.get_logger(__name__)


class StepResult:
    """单个工作流步骤的执行结果"""

    def __init__(self, step_id: str, success: bool, data: Any = None, error: str = "") -> None:
        self.step_id = step_id
        self.success = success
        self.data = data
        self.error = error

    def __repr__(self) -> str:
        return f"StepResult(id={self.step_id!r}, success={self.success}, error={self.error!r})"


class WorkflowRunner:
    """
    工作流执行引擎
    
    使用方式：
        runner = WorkflowRunner()
        runner.register("dwg_converter", my_convert_fn)
        runner.register("text_extractor", my_extract_fn)
        runner.register("translator", my_translate_fn)
        runner.register("text_applier", my_apply_fn)
        results = runner.run(workflow_file, context)
    """

    def __init__(self) -> None:
        # function_id -> callable: (context: dict) -> dict
        self._registry: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}

    # ------------------------------------------------------------------
    # 注册接口
    # ------------------------------------------------------------------

    def register(self, function_id: str, handler: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
        """注册一个功能处理函数。handler 接受 context 字典并返回更新后的 context。"""
        self._registry[function_id] = handler
        logger.debug("workflow_function_registered", function_id=function_id)

    # ------------------------------------------------------------------
    # 工作流读取
    # ------------------------------------------------------------------

    @staticmethod
    def load_workflow(workflow_file: str) -> Dict[str, Any]:
        """
        从 Markdown 工作流文件解析 YAML frontmatter。

        格式：
            ---
            name: ...
            steps:
              - id: convert
                function: dwg_converter
                enabled: true
            ---
        """
        content = Path(workflow_file).read_text(encoding="utf-8")
        # 提取 frontmatter
        match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if not match:
            raise ValueError(f"工作流文件格式错误（缺少 YAML frontmatter）: {workflow_file}")

        frontmatter = match.group(1)

        if YAML_AVAILABLE:
            return yaml.safe_load(frontmatter) or {}

        # 简易解析（不依赖 PyYAML）
        return WorkflowRunner._simple_parse(frontmatter)

    @staticmethod
    def _simple_parse(text: str) -> Dict[str, Any]:
        """简易 YAML 解析，仅支持 name/description/steps 结构"""
        result: Dict[str, Any] = {}
        steps: List[Dict[str, Any]] = []
        current_step: Optional[Dict[str, Any]] = None

        for raw_line in text.splitlines():
            line = raw_line.rstrip()
            if not line.strip() or line.strip().startswith("#"):
                continue

            indent = len(line) - len(line.lstrip())

            if line.strip().startswith("- ") and indent >= 2:
                # list item 开始
                if current_step is not None:
                    steps.append(current_step)
                current_step = {}
                rest = line.strip()[2:]
                if ":" in rest:
                    k, _, v = rest.partition(":")
                    current_step[k.strip()] = _coerce(v.strip())
                continue

            if ":" in line and not line.strip().startswith("-"):
                k, _, v = line.partition(":")
                k = k.strip()
                v = v.strip()
                if indent >= 4 and current_step is not None:
                    current_step[k] = _coerce(v)
                elif indent == 0:
                    if k != "steps":
                        result[k] = v
                continue

        if current_step is not None:
            steps.append(current_step)
        if steps:
            result["steps"] = steps
        return result

    # ------------------------------------------------------------------
    # 执行接口
    # ------------------------------------------------------------------

    def run(
        self,
        workflow_file: str,
        context: Dict[str, Any],
        stop_on_error: bool = True,
    ) -> List[StepResult]:
        """
        读取工作流文件，按顺序执行每个步骤。

        Args:
            workflow_file:  工作流 .md 文件路径
            context:        初始 context（会在步骤间传递和累积更新）
            stop_on_error:  遇到错误时是否停止

        Returns:
            steps 执行结果列表
        """
        workflow = self.load_workflow(workflow_file)
        workflow_name = workflow.get("name", "unnamed")
        steps = workflow.get("steps", [])

        logger.info("workflow_start", name=workflow_name, total_steps=len(steps))
        results: List[StepResult] = []

        for step in steps:
            step_id = step.get("id", "unknown")
            func_id = step.get("function", "")
            enabled = step.get("enabled", True)
            description = step.get("description", "")

            if not enabled:
                logger.info("workflow_step_skipped", step=step_id, reason="disabled")
                results.append(StepResult(step_id, success=True, data={"skipped": True}))
                continue

            handler = self._registry.get(func_id)
            if handler is None:
                error_msg = f"未找到功能处理函数: '{func_id}'（步骤: {step_id}）"
                logger.error("workflow_step_missing_handler", step=step_id, function=func_id)
                result = StepResult(step_id, success=False, error=error_msg)
                results.append(result)
                if stop_on_error:
                    break
                continue

            logger.info("workflow_step_start", step=step_id, function=func_id, description=description)
            try:
                updated_context = handler({**context, "_step": step})
                if isinstance(updated_context, dict):
                    context.update(updated_context)
                logger.info("workflow_step_done", step=step_id)
                results.append(StepResult(step_id, success=True, data=updated_context))
            except Exception as exc:
                error_msg = str(exc)
                logger.error("workflow_step_failed", step=step_id, error=error_msg)
                results.append(StepResult(step_id, success=False, error=error_msg))
                if stop_on_error:
                    break

        logger.info("workflow_done", name=workflow_name, total=len(results))
        return results

    def run_steps(
        self,
        steps: List[str],
        context: Dict[str, Any],
        stop_on_error: bool = True,
    ) -> List[StepResult]:
        """
        直接按 function_id 列表执行步骤（不需要工作流文件）。
        """
        results: List[StepResult] = []
        for func_id in steps:
            handler = self._registry.get(func_id)
            if handler is None:
                error_msg = f"未找到功能处理函数: '{func_id}'"
                results.append(StepResult(func_id, success=False, error=error_msg))
                if stop_on_error:
                    break
                continue
            try:
                updated = handler({**context})
                if isinstance(updated, dict):
                    context.update(updated)
                results.append(StepResult(func_id, success=True, data=updated))
            except Exception as exc:
                results.append(StepResult(func_id, success=False, error=str(exc)))
                if stop_on_error:
                    break
        return results


def _coerce(value: str) -> Any:
    """将字符串解析为 bool / int / str"""
    if value.lower() in ("true", "yes"):
        return True
    if value.lower() in ("false", "no"):
        return False
    try:
        return int(value)
    except ValueError:
        pass
    return value


# 全局默认引擎实例
default_runner = WorkflowRunner()
