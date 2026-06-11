# CAD Translate CLI — Agent 集成指南

> 本文件面向 AI 编程助手（Claude、GPT、Copilot 等），说明如何调用本工具完成 CAD 图纸翻译。

## 工具概述

`cad-translate` 是一个 Click-based CLI，提供 DWG/DXF 图纸的翻译流水线。通过 `python -m cli` 或安装后的 `cad-translate` 命令调用。

## 调用约定

所有命令支持 `--json` 标志输出结构化 JSON，便于程序化解析：

```bash
python -m cli --json config show
python -m cli --json pipeline convert -i input.dwg
```

JSON 输出格式统一为：
```json
{
  "success": true,
  "task_id": "xxxx",
  "output_file": "path/to/output",
  ...
}
```

失败时：
```json
{
  "success": false,
  "error_type": "usage_error|artifact_error|dependency_error|processing_error",
  "message": "错误描述"
}
```

## 完整翻译流程

按顺序执行以下 4 个命令，每步的输出是下一步的输入：

### Step 1: DWG → DXF

```bash
python -m cli --json pipeline convert -i <input.dwg>
```

- 输出：`output_file` 字段为生成的 `.dxf` 路径
- 前置条件：需要 AutoCAD/浩辰CAD COM 或 ODA/LibreDWG
- 失败原因：通常是没有可用的 DWG 转换后端

### Step 2: 提取文字

```bash
python -m cli --json pipeline extract -i <step1_output.dxf>
```

- 输出：`excel_file` 字段为生成的 `.xlsx` 路径，`text_count` 为提取的文字数量
- 无外部依赖，使用 `ezdxf` 库直接解析

### Step 3: LLM 翻译

```bash
python -m cli --json pipeline translate-excel -i <step2_output.xlsx> --target-language <lang>
```

- 输出：`output_file` 为翻译后的 `.xlsx`，`translated_cells` 为翻译数量
- 前置条件：已配置 LLM（`config llm init` 或 `onboard`）
- `--target-language`：目标语言代码（ru/zh/en/ja/ko 等）
- `--source-language`：源语言，默认 `auto`

### Step 4: 回填

```bash
python -m cli --json pipeline apply -i <step1_output.dxf> -e <step3_output.xlsx> --translation-mode replace
```

- 输出：`output_file` 为最终翻译后的 `.dxf`
- `--translation-mode`：
  - `replace`：替换原文（推荐，最干净）
  - `add`：在原文下方追加译文
  - `newline`：在原文内部换行追加

## 配置管理

### 检查配置

```bash
python -m cli --json config show
python -m cli --json config llm show
```

### 设置 LLM

```bash
python -m cli config llm init --non-interactive \
  --format openai_compatible \
  --provider <provider> \
  --model <model> \
  --base-url <url> \
  --api-key <key>
```

### 测试连接

```bash
python -m cli --json config llm test
```

返回 `{"success": true}` 表示连接正常。

### 修改参数

```bash
python -m cli config set --target-language ru
python -m cli config set --translation-mode replace
python -m cli config set --font-name "SimSun"
python -m cli config set --font-size-reduction 2
```

## 配置文件位置

| 文件 | 路径 | 说明 |
|------|------|------|
| 运行时配置 | `~/.config/cad-translate/config.json` | LLM 密钥、模型、CAD 参数 |
| 环境变量 | 项目根目录 `.env` | 覆盖默认配置 |

## 错误处理

| error_type | 含义 | 处理方式 |
|------------|------|----------|
| `usage_error` | 参数错误 | 检查命令参数 |
| `artifact_error` | 文件不存在 | 检查路径 |
| `dependency_error` | 缺少依赖（如 COM 后端） | 安装对应软件 |
| `processing_error` | 处理失败 | 查看 message 字段 |

## 注意事项

1. **顺序依赖**：4 步流水线必须按顺序执行，每步的输出是下一步的输入
2. **文件编码**：DXF 文件路径支持中文，但 Excel 输出路径建议用英文避免编码问题
3. **并发**：LLM 翻译默认 3 个并发，可通过 `--batch-size` 调整
4. **超时**：LLM 默认超时 300 秒，可通过 `config set` 调整
5. **COM 后端**：AutoCAD/浩辰CAD 需要在 Windows 上运行且软件已安装
6. **输出目录**：默认输出到 `outputs/cad_tasks/` 下，每步生成独立子目录
