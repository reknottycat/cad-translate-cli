# cad-translate 中文使用手册

`cad-translate` 是一个本地可安装的 CAD 翻译命令行工具，负责把
`backend/` 中现有的能力包装成可直接使用的 CLI 工作流。

它当前主要支持：

- `DWG -> DXF` 转换
- `DXF` 文本提取
- Excel 翻译中转
- 翻译后 DXF 回写
- 本地 LLM 配置
- 本地发布与冒烟验证

## 重构说明（2026-03-25）

当前 CAD CLI 正在按 CLI-Anything 的 harness 标准重构（Click + REPL + JSON 输出 + 真实后端集成 + 测试/文档/发布闭环）。

CLI-Anything 作为开发参考的技能包保留，不是运行时依赖。

旧实现已归档到 `agent-harness/cad-translate_legacy/`，它不属于运行时、不会被打包，也不会被 pytest 扫描；新代码不要依赖它。

后续 CAD 专项功能会在 `cli/` 这个骨架上继续加，不和旧实现混用。

## 顶层命令（骨架）

顶层保留的 harness 风格命令是：

- `onboard`
- `config`
- `project`
- `files`
- `pipeline`
- `tasks`
- `repl`（不带子命令时默认进入 REPL）

说明：`release` 相关命令仍然可用，但为了保持骨架清晰，已从顶层 `--help` 中隐藏。

## 安装

```bash
cd agent-harness
pip install -e .
```

如果 Windows 下找不到 `cad-translate`，通常需要把下面目录加入
`PATH`：

`<USER>\AppData\Roaming\Python\Python312\Scripts`

## 常用命令

```bash
cad-translate --help
cad-translate onboard
cad-translate config show
cad-translate config get cad.target_language
cad-translate config set cad.target_language ru
cad-translate config set cad.translation_mode add
cad-translate pipeline extract -i ".\sample.dxf" -o ".\output"
cad-translate pipeline translate-excel -i ".\output\sample_extracted_texts.xlsx" --target-language en
cad-translate pipeline apply -i ".\sample.dxf" -e ".\output\sample_extracted_texts.xlsx" -o ".\output" --translation-mode replace
```

## 配置体系

当前已经使用统一配置系统：

- 全局配置文件：
  `~/.config/cad-translate/config.json`
- 项目配置文件：
  当前工作目录下 `.cad-translaterc`
- 配置优先级：
  `CLI 参数 > 环境变量 > 项目配置 > 全局配置 > 默认值`

支持的配置命令：

- `config show`
  查看当前生效配置、来源和配置文件路径
- `config get <path>`
  读取单个配置项，例如 `config get cad.target_language`
- `config set <path> <value>`
  写入单个配置项，例如 `config set cad.target_language ru`
- `config validate`
  校验当前合并后的配置是否符合 schema

常见 CAD 配置项：

- `cad.target_language`
- `cad.translation_mode`
- `cad.font_name`
- `cad.font_size_reduction`
- `cad.default_output_dir`
- `cad.converter_backend`

常见 LLM 配置项：

- `llm.primary`
- `llm.fallback_models`
- `llm.system_prompt_mode`
- `llm.glossary_file`

## DWG 转换后端

当前自动模式顺序：

`haochen_com -> autocad_com -> oda`

说明：

- `haochen_com`
  适合本机已安装并可正常保存的浩辰 CAD
- `autocad_com`
  适合本机安装 AutoCAD 的场景
- `oda`
  作为更稳的 fallback，尤其适合复杂图纸和图像保留场景

如果前面的后端不可用或失败，CLI 会自动回退到下一个后端。

## LLM 配置

当前支持这些接口格式：

- `openai_compatible`
- `nvidia`
- `anthropic`
- `google`
- `ollama`
- `lmstudio`

支持这些 prompt 模式：

- `default`
- `cad_specialized`
- `custom`

支持术语库格式：

- `csv`
- `xlsx`
- `xls`

如果存在默认术语库：

`backend/DocuTranslate.csv`

系统会在合适模式下自动使用它。

## 发布与本地验证

```bash
cad-translate release package-info
cad-translate release build
cad-translate release smoke
```

含义：

- `release package-info`
  查看包名、入口命令和构建信息
- `release build`
  本地构建安装包
- `release smoke`
  跑最基础的可用性检查

## 当前状态

目前已经验证通过：

- Path A：
  `DXF -> extract -> apply`
- Path B：
  `DWG -> convert -> extract -> apply`
- 统一配置系统
- LLM 主备模型回退
- glossary 术语库支持
- reasoning 请求参数处理

## 已知限制

- `haochen_com` 可能会被探测到，但如果本机授权不可用，实际保存仍可能失败
- 免费在线模型可能遇到上游 `429` 限流
- 大批量 Excel 在线翻译速度仍受模型和 provider 响应速度影响
- 当前 `config set` 默认写全局配置，项目级写入能力还可以继续增强

## 建议阅读顺序

如果你要继续看更详细的信息，建议按下面顺序阅读：

1. `README_CN.md`
2. `QA_CN.md`
3. `improve.md`
4. `README.md`
5. `QA.md`
6. `tests/TEST.md`

## 相关文档

- `QA_CN.md`
  中文问题报告，适合查看当前已知问题和运行限制
- `improve.md`
  中文优化方案，适合查看下一阶段最值得继续做的改进方向
