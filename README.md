# CAD Translate CLI (legacy)

> [!WARNING]
> **本仓库不再是 CAD CLI 的主维护入口。**
> 当前维护中的 CLI 位于 **[cad-translation-web/agent-harness](https://github.com/reknottycat/cad-translation-web/tree/main/agent-harness)**，
> 包名为 `cad-translate`，入口为 `cad_translate.cli:main`，并直接复用 `backend/app`。

## 这个仓库为什么要收口

现在有两个仓库都提供名为 `cad-translate` 的命令：

- 本仓库：distribution 是 `cad-translate-cli`，入口是 `cli.cad_cli:main`；
- canonical 仓库：distribution 是 `cad-translate`，入口是 `cad_translate.cli:main`。

旧 README 仍把本仓库写成完整、持续维护的产品，因此用户或 Agent 很容易装错入口，
后续修复也可能分别落到旧 `lib.*` 和新 `backend/app`，再次产生功能漂移。
这就是本次 PR 要解决的问题；它不是在修一个 CAD 算法 bug。

## 当前决策

- **新安装、新功能和 bugfix：只进入 `cad-translation-web/agent-harness` / `backend/app`。**
- **本仓库：保留给已有 standalone 用户做兼容和历史复现。**
- 不删除代码或 Git 历史，不迁移用户配置/任务，不改 `1.0.1`，不发布新的 PyPI 版本。
- 暂不增加自动转发 shim：旧端仍有 `repl`、`onboard`、`release` 和不同的 fallback/错误行为，
  直接转发并不能保证旧脚本无损兼容。

## 迁移要点

| 项目 | standalone | canonical |
|---|---|---|
| distribution | `cad-translate-cli` | `cad-translate` |
| console entry | `cli.cad_cli:main` | `cad_translate.cli:main` |
| 实现 | 仓内 `lib.*` | 直接复用 `backend/app` |
| 裸命令 | 进入 REPL | 显示帮助 |
| 特有命令 | `repl` / `onboard` / `release` | 不提供同名行为 |
| translation mode | `add` / `replace` | `add` / `replace` |
| 全局配置 | `~/.config/cli-anything-cad/config.json` | 相同 |
| 项目配置 | 当前目录 `.cli-anything-cadrc` | 相同 |

两个 distribution 会安装同名 `cad-translate` launcher，因此迁移时请使用**新的虚拟环境**，
不要直接叠加安装。完整命令/配置差异与验证步骤见 **[docs/MIGRATION.md](docs/MIGRATION.md)**。

下方旧手册仅用于已有 standalone 环境的历史复现；与上方或迁移指南冲突时，以迁移指南为准。

<details>
<summary>旧版历史说明（仅供复现已有 standalone 安装，不是当前产品指南）</summary>

# CAD Translate CLI

CAD 图纸翻译命令行工具 — 从 DWG/DXF 文件中提取文字，通过 LLM 翻译后回填。

## 功能

- **DWG → DXF 转换**：支持 AutoCAD COM / 浩辰 CAD COM / ODA File Converter / LibreDWG
- **文字提取**：从 DXF 中提取 TEXT / MTEXT / ATTDEF / ATTRIB 实体，导出为 Excel
- **LLM 翻译**：支持 16+ 厂商（OpenAI、DeepSeek、阿里百炼、MiniMax、智谱等）
- **翻译回填**：将译文写回 DXF，支持替换、追加两种模式

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
| `~/.config/cli-anything-cad/config.json` | 运行时配置（LLM、CAD 参数） |
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

</details>
