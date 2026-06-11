# CAD Translate CLI

CAD 图纸翻译命令行工具 — 从 DWG/DXF 文件中提取文字，通过 LLM 翻译后回填。

## 功能

- **DWG → DXF 转换**：支持 AutoCAD COM / 浩辰 CAD COM / ODA File Converter / LibreDWG
- **文字提取**：从 DXF 中提取 TEXT / MTEXT / ATTDEF / ATTRIB 实体，导出为 Excel
- **LLM 翻译**：支持 16+ 厂商（OpenAI、DeepSeek、阿里百炼、MiniMax、智谱等）
- **翻译回填**：将译文写回 DXF，支持替换、追加、换行三种模式

## 快速开始

### 1. 安装

```bash
pip install -r requirements.txt
pip install -e .
```

### 2. 首次配置

```bash
# 交互式引导
cad-translate onboard

# 或直接指定参数
cad-translate config llm init --non-interactive \
  --format openai_compatible \
  --provider custom \
  --model "你的模型" \
  --base-url "https://api.xxx.com/v1" \
  --api-key "你的密钥" \
  --system-prompt-mode cad_specialized

# 设置目标语言
cad-translate config set --target-language ru
```

### 3. 翻译流程

```bash
# 1. DWG → DXF
cad-translate pipeline convert -i 图纸.dwg

# 2. 提取文字到 Excel
cad-translate pipeline extract -i 输出/图纸.dxf

# 3. LLM 翻译
cad-translate pipeline translate-excel -i 输出/图纸_extracted_texts.xlsx --target-language ru

# 4. 回填翻译（replace=替换原文 / add=追加）
cad-translate pipeline apply -i 输出/图纸.dxf -e 输出/图纸_extracted_texts_translated.xlsx --translation-mode replace
```

## 目录结构

```
.
├── cli/                    # CLI 源码
│   ├── cad_cli.py          # 命令入口（Click）
│   ├── core/               # 流水线、任务、项目管理
│   └── utils/              # 后端桥接、终端 UI
├── lib/                    # 核心处理库
│   ├── config.py           # 配置加载（.env + config.json）
│   ├── functions/          # DWG 转换、文字提取/回填
│   ├── services/           # LLM 翻译引擎、配置管理
│   └── workflow/           # 流水线编排引擎
├── tools/libredwg/         # LibreDWG 二进制（可选）
├── skill/                  # Claude Code skill 定义
├── setup.py                # 包安装配置
├── requirements.txt        # Python 依赖
└── .env.example            # 环境变量模板
```

## 常用命令

| 命令 | 说明 |
|------|------|
| `config show` | 查看当前配置 |
| `config llm show` | 查看 LLM 配置 |
| `config llm test` | 测试 LLM 连接 |
| `config set --target-language ru` | 设置目标语言 |
| `config set --translation-mode replace` | 设置回填模式 |
| `files list --path .` | 扫描目录中的 CAD 文件 |
| `tasks list` | 查看任务列表 |
| `repl` | 进入交互式 REPL |

## DWG 转换后端

| 后端 | 说明 | 要求 |
|------|------|------|
| `auto` | 自动探测（推荐） | — |
| `autocad_com` | AutoCAD COM | Windows + AutoCAD |
| `haochen_com` | 浩辰 CAD COM | Windows + 浩辰 CAD |
| `oda` | ODA File Converter | 需安装 ODA |
| `libredwg` | LibreDWG | 捆绑在 tools/ |

## 支持的 LLM 厂商

openai, openrouter, deepseek, dashscope, groq, minimax, zhipu, moonshot, siliconflow, together, anthropic, google, ollama, lmstudio, nvidia, custom（任意 OpenAI 兼容 API）

## 许可证

MIT
