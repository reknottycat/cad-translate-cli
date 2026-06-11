---
name: cad-translate
description: CAD图纸翻译CLI工具 - DWG/DXF文字提取、LLM翻译、回填
license: MIT
compatibility: opencode
metadata:
  audience: developers
  workflow: cad-processing
  tags: [cad, dxf, dwg, translation, cli, python]
---

## CAD 图纸翻译 CLI

使用 `cli-anything-cad` 命令行工具完成 CAD 图纸翻译。

### 首次使用 - 必须配置 LLM

```bash
cli-anything-cad config llm init --non-interactive \
  --format openai_compatible \
  --provider custom \
  --model "模型名" \
  --base-url "https://api.xxx.com/v1" \
  --api-key "你的密钥" \
  --system-prompt-mode cad_specialized

cli-anything-cad config set --target-language ru
```

或使用交互式引导：`cli-anything-cad onboard`

### 翻译流水线（4 步）

```bash
# 1. DWG → DXF（需要 AutoCAD/浩辰CAD/ODA/LibreDWG 之一）
cli-anything-cad pipeline convert -i 图纸.dwg

# 2. 提取文字到 Excel
cli-anything-cad pipeline extract -i 输出/图纸.dxf

# 3. LLM 翻译
cli-anything-cad pipeline translate-excel -i 输出/图纸_extracted_texts.xlsx --target-language ru

# 4. 回填（--translation-mode replace 替换原文 / add 追加）
cli-anything-cad pipeline apply -i 输出/图纸.dxf -e 输出/图纸_extracted_texts_translated.xlsx --translation-mode replace
```

### 常用命令

| 命令 | 说明 |
|------|------|
| `config show` | 查看当前配置 |
| `config llm show` | 查看 LLM 配置 |
| `config llm test` | 测试 LLM 连接 |
| `config set --target-language ru` | 设置目标语言 |
| `config set --translation-mode replace` | 设置回填模式 |
| `files list --path .` | 扫描 CAD 文件 |
| `tasks list` | 查看任务列表 |
| `repl` | 交互式 REPL |

### 支持的 LLM 厂商

openai, openrouter, deepseek, dashscope, groq, minimax, zhipu, moonshot, siliconflow, together, anthropic, google, ollama, lmstudio, nvidia, custom（任意 OpenAI 兼容 API）

### DWG 转换后端

- `auto`：自动探测（推荐）
- `autocad_com`：AutoCAD（需已安装）
- `haochen_com`：浩辰 CAD（需已安装）
- `oda`：ODA File Converter
- `libredwg`：LibreDWG（捆绑在 tools/）

### 回填模式

- `replace`：替换原文为译文
- `add`：在原文下方追加译文
- `newline`：在原文内部换行追加译文
