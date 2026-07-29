# cli-anything-cad 测试状态说明

## 文档目的

这份文档用于说明当前 `cli-anything-cad` 的测试覆盖范围、已经完成的验证动作，
以及目前仍然存在的验证边界。

它不是未来规划文档，而是“当前已验证状态”的说明。

## 重构提示（2026-03-25）

当前 CAD CLI 正在按 CLI-Anything 的 harness 标准重构，旧实现已归档到
`agent-harness/cad-translate_legacy/`，并且被刻意排除在运行时、打包和 pytest 扫描范围之外。

CLI-Anything 作为开发参考的技能包保留，不是运行时依赖。

本文档里“最近一次完整验证结果”的测试数字是历史记录（用于追溯稳定状态），在重构期间请以实际 `pytest` 运行结果为准。

## 当前测试构成

目前主要分为三层：

1. `test_core.py`
   覆盖 CLI 和核心逻辑层
2. `test_full_e2e.py`
   覆盖 CAD 真实工作流的端到端路径
3. `tests/backend/test_backend_runtime.py`
   覆盖 backend 运行时、DWG 后端、LLM 配置和翻译相关逻辑

## 已覆盖内容

### 核心与 CLI 层

已覆盖：

- 包导入
- project/session 基础行为
- 文件扫描
- pipeline 上下文合并
- task 摘要提取
- CLI `--help`
- JSON 输出
- `release` 命令
- `config show/get/set/validate`
- path 风格的 `config set`
- `config llm show/test/init`
- `pipeline apply` 的 `translation_mode`
- CAD extract Excel 的翻译列回填逻辑

### 端到端 CAD 流程

已覆盖两条主路径：

- Path A：
  `DXF -> extract -> apply`
- Path B：
  `DWG -> convert -> extract -> apply`

Path B 当前使用真实的本机后端链：

- `haochen_com`
- `autocad_com`
- `oda`

并通过自动探测和回退机制完成。

### backend 运行时层

已覆盖：

- 翻译配置读写
- 统一配置文件优先级
- CAD 默认配置读写
- config manager 深合并与 schema 校验
- LLM 主备模型回退
- glossary 加载
- `default / cad_specialized / custom` prompt 模式
- reasoning 请求参数注入
- NVIDIA 直连 provider
- DWG 后端探测与回退
- ODA 缺失时的安装提示
- COM 临时路径与编码处理
- DXF 回写
- `add` 模式插入翻译文本

## 最近一次完整验证结果

执行时间：

- 2026-03-16

已执行命令：

```bash
python -m pytest cli/tests/test_core.py -v
python -m pytest tests/backend/test_backend_runtime.py -v
python -m pytest cli/tests/test_full_e2e.py::test_dwg_convert_extract_apply_roundtrip -v -s
python -m cad-translate --json config show
python -m cad-translate --json config get cad.target_language
python -m cad-translate --json config validate
python -m build
```

实际结果：

- `cli/tests/test_core.py`
  `34 passed`
- `tests/backend/test_backend_runtime.py`
  `37 passed`
- `cli/tests/test_full_e2e.py::test_dwg_convert_extract_apply_roundtrip`
  `1 passed`
- `config show/get/validate`
  命令级验证通过
- `python -m build`
  构建通过，且 README 缺失 warning 已修复

## 当前验证结论

可以认为当前已经确认这些结论：

- 统一配置系统可用
- `config show/get/set/validate` 可用
- path 风格配置写入可用
- CAD 主流程可用
- DWG 自动后端探测与回退可用
- LLM 主备模型机制可用
- glossary 和 prompt 模式可用
- 本地构建流程可用

## 当前验证边界

虽然主流程已通过，但仍有一些边界需要明确：

- 大批量在线翻译的速度与稳定性仍受上游 provider 影响
- 免费模型可能触发 `429`
- `haochen_com` 是否真正可保存，仍可能受本机授权状态影响
- Windows 之外的 COM 路径不适用

## 建议后续补强

下一步测试增强建议：

- 增加 `onboard` 向导测试
- 增加 `config unset` 测试
- 增加项目级配置写入测试
- 增加 `doctor` 命令测试
- 增加长批量翻译进度和恢复测试
