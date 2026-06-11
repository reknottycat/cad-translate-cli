# CAD Translate CLI

CAD 图纸翻译命令行工具 — 从 DWG/DXF 文件中提取文字，通过 LLM 翻译后回填。

## 功能

- **DWG → DXF 转换**：支持 AutoCAD COM / 浩辰 CAD COM / ODA File Converter / LibreDWG
- **文字提取**：从 DXF 中提取 TEXT / MTEXT / ATTDEF / ATTRIB 实体，导出为 Excel
- **LLM 翻译**：支持 16+ 厂商（OpenAI、DeepSeek、阿里百炼、MiniMax、智谱等）
- **翻译回填**：将译文写回 DXF，支持替换、追加、换行三种模式

## 安装

### 1. 环境要求

- **Python 3.10+**
- **Windows**（COM 自动化依赖 Windows）
- **DWG 转换后端**（以下任选其一）：
  - AutoCAD（推荐，COM 自动化）
  - 浩辰 CAD / GStarCAD / ZWCAD（COM 自动化）
  - ODA File Converter（免费，需单独安装）
  - LibreDWG（已捆绑在 `tools/libredwg/`，免费但兼容性较弱）

### 2. 安装依赖

```bash
pip install -r requirements.txt
pip install -e .
```

### 3. 配置 LLM API

翻译功能需要一个 OpenAI 兼容的 LLM API。首次使用必须配置：

```bash
# 方式一：交互式引导（推荐新手）
cad-translate onboard

# 方式二：直接指定参数
cad-translate config llm init --non-interactive \
  --format openai_compatible \
  --provider custom \
  --model "你的模型名" \
  --base-url "https://你的API地址/v1" \
  --api-key "你的API密钥" \
  --system-prompt-mode cad_specialized

# 方式三：通过 .env 文件
cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY、LLM_BASE_URL、LLM_MODEL
```

**支持的 LLM 厂商**：openai, openrouter, deepseek, dashscope, groq, minimax, zhipu, moonshot, siliconflow, together, anthropic, google, ollama, lmstudio, nvidia, custom（任意 OpenAI 兼容 API）

### 4. 设置目标语言

```bash
cad-translate config set --target-language ru    # 俄语
cad-translate config set --target-language zh    # 中文
cad-translate config set --target-language en    # 英语
```

## 使用方法

### 完整翻译流程（4 步）

```bash
# 1. DWG → DXF（需要 AutoCAD/浩辰CAD/ODA/LibreDWG 之一）
cad-translate pipeline convert -i 图纸.dwg

# 2. 提取文字到 Excel
cad-translate pipeline extract -i 输出/图纸.dxf

# 3. LLM 翻译 Excel
cad-translate pipeline translate-excel -i 输出/图纸_extracted_texts.xlsx --target-language ru

# 4. 回填翻译到 DXF
cad-translate pipeline apply -i 输出/图纸.dxf -e 输出/图纸_extracted_texts_translated.xlsx --translation-mode replace
```

### 回填模式

| 模式 | 说明 |
|------|------|
| `replace` | 替换原文为译文（推荐） |
| `add` | 在原文下方追加译文 |
| `newline` | 在原文内部换行追加 |

### 常用命令

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
├── tools/libredwg/         # LibreDWG 二进制（可选 DWG 转换后端）
├── skill/                  # Claude Code skill 定义
├── setup.py                # 包安装配置
├── requirements.txt        # Python 依赖
└── .env.example            # 环境变量模板
```

## 配置文件位置

| 文件 | 说明 |
|------|------|
| `.env` | 环境变量配置（从 `.env.example` 复制） |
| `~/.config/cad-translate/config.json` | 运行时配置（LLM、CAD 参数） |
| `lib/config/runtime_config.example.json` | 运行时配置模板 |

## DWG 转换后端

| 后端 | 说明 | 要求 |
|------|------|------|
| `auto` | 自动探测（推荐） | — |
| `autocad_com` | AutoCAD COM | Windows + AutoCAD 已安装 |
| `haochen_com` | 浩辰 CAD COM | Windows + 浩辰 CAD 已安装 |
| `oda` | ODA File Converter | 需单独安装 ODA |
| `libredwg` | LibreDWG | 捆绑在 `tools/libredwg/` |

## 许可证

MIT
