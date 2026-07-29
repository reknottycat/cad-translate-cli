# CAD Translation System — Agent Guide

> 本文件面向 AI 编程助手。如果你刚接触这个项目，请先阅读本指南再修改代码。
> 项目的主要文档语言为中文，代码注释混合中英文。本文件以中文撰写。

---

## 1. 项目概述

本项目是一套 **CAD 图纸翻译系统**，核心工作流为：

1. **转换**：将 DWG 文件转换为 DXF（支持 AutoCAD / 浩辰 CAD / ODA / LibreDWG 等多种后端）。
2. **提取**：从 DXF 中提取文字内容，导出为 Excel。
3. **翻译**：调用 LLM API（OpenAI-compatible、阿里百炼、DeepSeek 等）对文字进行批量翻译。
4. **回填**：将翻译后的文字写回 DXF 文件，生成翻译后的图纸。

项目提供三种运行形态：
- **Web 应用**：React 前端 + FastAPI 后端（主形态）。
- **CLI 包**：可安装命令行工具 `cli-anything-cad`（位于 `agent-harness/`）。
- **遗留桌面 GUI**：基于 `customtkinter` 的独立程序（位于 `trans_CAD_gui_V1.0/`）。

**操作系统定位**：以 Windows 为主（依赖 COM 自动化调用 AutoCAD/浩辰 CAD，以及 PowerShell 构建脚本）。

---

## 2. 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.10+、FastAPI、Celery、Redis、SQLAlchemy 2.0、Alembic、Pydantic v2、structlog、uvicorn |
| CAD 处理 | `ezdxf`、`pandas`、`openpyxl`、`pywin32`（Windows COM） |
| 翻译引擎 | 统一 LLM 引擎，支持 10+ 厂商预设（OpenAI、OpenRouter、DeepSeek、Groq、MiniMax、Zhipu、Moonshot、SiliconFlow、Together、阿里 DashScope 等） |
| 前端 | React 18、TypeScript、Vite 5、Tailwind CSS 3.4、TDesign React、Axios、React Router |
| CLI | `click`、`prompt-toolkit`、`rich` |
| 测试 | `pytest`、`pytest-asyncio`、Playwright |
| 打包 | PowerShell、PyInstaller、Nuitka、electron-builder |

---

## 3. 目录结构与模块划分

```
.
├── backend/                    # FastAPI 后端（唯一可信源）
│   ├── app/
│   │   ├── main.py             # FastAPI 应用入口（路由注册、生命周期、静态文件挂载）
│   │   ├── config.py           # Pydantic Settings，读取 .env 与运行时 JSON 配置
│   │   ├── database.py         # SQLAlchemy + SQLite 模型定义
│   │   ├── security.py         # JWT / admin token 校验
│   │   ├── routers/            # API 路由（projects、files、translation、cad）
│   │   ├── schemas/            # Pydantic 请求/响应模型
│   │   ├── services/           # 业务逻辑层
│   │   │   ├── llm/translation_service.py    # 统一翻译引擎
│   │   │   ├── cad_pipeline_service.py       # CAD 全流程编排（上传→转换→提取→翻译→回填）
│   │   │   ├── tasks/          # Celery 异步任务（cad_tasks、translation_tasks）
│   │   │   └── ...             # 各种兼容层与工具服务
│   │   ├── functions/          # 底层 CAD 功能（DWG 转换、文字提取/回填、翻译器）
│   │   ├── workflow/           # 工作流引擎抽象（pipeline、engine）
│   │   └── utils/              # 文件工具等
│   ├── requirements.txt        # 后端与 CLI 共享的运行时依赖
│   ├── .env / .env.example     # 环境变量配置
│   ├── run_server.py           # 启动 uvicorn 的便捷脚本
│   └── run_celery.py           # 启动 Celery worker 的便捷脚本
│
├── frontend/                   # React 前端
│   ├── src/
│   │   ├── main.tsx            # 应用入口
│   │   ├── App.tsx             # 根组件（当前直接渲染 TranslationWorkbenchPage）
│   │   ├── pages/              # 页面组件
│   │   ├── components/         # 通用组件
│   │   └── services/api.ts     # Axios 封装，代理到 /api
│   ├── package.json            # npm 脚本与依赖
│   ├── vite.config.ts          # Vite 配置（含 /api 代理到 localhost:8000）
│   └── tailwind.config.js      # Tailwind 配置
│
├── agent-harness/              # 可安装的 CLI 包
│   ├── cad-translate/       # CLI 源码（click 命令树）
│   ├── setup.py                # 包元数据与入口点 cli-anything-cad
│   └── pyproject.toml          # setuptools 构建配置
│
├── trans_CAD_gui_V1.0/         # 遗留桌面 GUI（customtkinter）
│   ├── gui.py                  # 主界面
│   ├── autocad_converter.py    # AutoCAD COM 转换器
│   ├── haochen_optimized_converter.py  # 浩辰 CAD COM 转换器
│   ├── dxf_text_extractor.py   # ezdxf 文字提取引擎
│   ├── 回填.py                  # 文字回填/应用器
│   └── ...
│
├── 命令行专用/                  # 遗留纯命令行脚本
│   ├── main_processor.py       # 完整四步流水线封装
│   ├── simple_processor.py     # 跳过 DWG 转换的简化版
│   └── 提取.py                  # 独立提取脚本
│
├── CLI-Anything/               # 通用插件框架生态（子项目，无 CAD 专用插件）
│
├── tools/libredwg/             # 捆绑的 LibreDWG v0.13.3 Windows 二进制文件
│
├── scripts/                    # 构建与打包脚本
│   ├── build_scale.ps1         # 主构建脚本：生成 scale_release/ 运行时包
│   ├── build_scale_exe.ps1     # 使用 PyInstaller 生成独立 EXE
│   ├── build_scale_exe_nuitka.ps1  # 使用 Nuitka 生成独立 EXE
│   └── ...
│
├── tests/                      # 主测试套件
│   ├── backend/                # 后端 API、安全、文件安全测试
│   ├── scripts/                # 脚本测试
│   ├── e2e_test.py             # Playwright + HTTP 端到端测试
│   ├── test_scale_release_packaging.py       # 打包脚本验证
│   └── test_scale_release_exe_packaging.py   # EXE 打包验证
│
├── docs/                       # 项目文档（中文为主）
│   └── modern/                 # 现代化文档（架构说明、API 规范、发布说明）
│
├── scale_release/              # Stage-1 运行时交付包（由 build_scale.ps1 生成）
├── electron_release/           # Electron 桌面应用尝试（较旧）
├── release_exe/                # EXE 启动器源码
└── cad-translation-skill/      # AI Skill 配置
```

### 重要注意事项
- **可信源唯一**：`backend/` 是唯一的活跃开发后端源码。`scale_release/backend/` 和 `electron_release/backend/` 是构建时复制的运行时镜像，**不要直接修改它们**。
- **前端当前为单页模式**：`App.tsx` 目前直接渲染 `<TranslationWorkbenchPage />`，`react-router-dom` 与 `Layout.tsx` 中的多路由定义暂时未被使用。
- **遗留代码与现代化代码并存**：修改 CAD 核心逻辑时，注意 `backend/app/functions/`（现代）与 `trans_CAD_gui_V1.0/`（遗留）可能存在重复实现。

---

## 4. 构建与运行命令

### 4.1 环境准备

```powershell
# 安装后端依赖
cd backend
pip install -r requirements.txt

# 安装前端依赖
cd frontend
npm install

# 安装 CLI 包（开发模式）
cd agent-harness
pip install -e .
```

### 4.2 开发模式运行

```powershell
# 终端 1：启动后端
cd backend
python run_server.py
# 或直接：uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 终端 2：启动前端
cd frontend
npm run dev
# 默认监听 0.0.0.0:3000，并通过 Vite 代理 /api 到 localhost:8000

# 终端 3（可选）：启动 Celery worker
cd backend
python run_celery.py
# 默认 concurrency=2，pool=threads
```

### 4.3 生产构建

```powershell
# 前端生产构建
cd frontend
npm run build
# 输出到 frontend/dist/

# 生成运行时交付包
cd ..
powershell -ExecutionPolicy Bypass -File scripts/build_scale.ps1
# 输出：scale_release/ 目录 + scale_release.zip
```

### 4.4 一键启动交付包

构建完成后，最终用户只需双击：

```
scale_release/start_delivery.bat
```

该脚本会自动查找 Python、设置 `ASYNC_TASKS_MODE=local`、启动后端，并打开浏览器访问 `http://127.0.0.1:8000/`。

---

## 5. 测试策略

### 5.1 测试框架
- **pytest**（主测试运行器）
- **pytest-asyncio**（异步测试支持）
- **fastapi.testclient.TestClient**（API 集成测试）
- **Playwright**（端到端浏览器自动化）

### 5.2 运行测试

```powershell
# 运行全部测试
python -m pytest

# 仅后端测试
python -m pytest tests/backend/ -v

# 打包脚本测试
python -m pytest tests/test_scale_release_packaging.py -v
python -m pytest tests/test_scale_release_exe_packaging.py -v

# 端到端测试（需前后端均已启动）
python tests/e2e_test.py

# LLM 并发测试
python backend/tests/test_llm_concurrency.py
```

### 5.3 测试组织
- `tests/backend/test_backend_runtime.py`：核心后端 API 与服务测试（使用临时 `.env` 和 SQLite 数据库隔离状态）。
- `tests/backend/test_security_controls.py`：Admin Token、JWT、路由权限测试。
- `tests/backend/test_file_safety.py`：路径遍历与文件名清洗测试。
- `tests/test_scale_release_*.py`：对 PowerShell 打包脚本本身的验证（文件包含/排除、API Key 脱敏、缓存复用等）。

---

## 6. 开发规范

### 6.1 代码风格
- **模块大小限制**：单一模块不超过 **800 行**（项目级硬性规则，见 `.trae/rules/project_rules.md`）。
- **每次修改后更新 README**：如果变更影响了功能、接口或构建方式，必须同步更新相关 `README.md`。
- **任务完成后清理临时产物**：调试或编译产生的临时文件（缓存、日志、中间构建产物）应在提交前清理。
- Python 代码遵循 **PEP 8** 风格，使用类型注解（`from __future__ import annotations`）。
- 前端组件使用 **PascalCase**，变量/函数使用 **camelCase**，遵循 ESLint 规则。

### 6.2 配置管理
- 后端静态配置通过 `backend/.env` 管理，由 `backend/app/config.py` 中的 Pydantic `Settings` 加载。
- 运行时动态配置（模型网关、API Key 等）通过 `~/.config/cli-anything-cad/config.json` 持久化，由 `runtime_config_service.py` 管理。
- 环境变量 `CAD_TRANSLATION_ENV_FILE` 可覆盖默认 `.env` 路径。
- **不要**将真实 API Key 提交到仓库；打包脚本会自动对 `runtime_config.local.json` 中的 `api_key` 进行脱敏处理。

### 6.3 路由与 API 规范
- 后端路由前缀：
  - `/api/projects` — 项目管理
  - `/api/files` — 文件管理
  - `/api/translation` — 现代化翻译接口
  - `/api/cad` — CAD 流水线接口
- 自动生成的 API 文档：
  - Swagger UI：`/api/docs`
  - ReDoc：`/api/redoc`
- 部分 CAD 和项目端点受 `require_admin_access` 保护（通过 `X-Admin-Token` 或 `Authorization: Bearer` 头部）。默认关闭（`ENABLE_ADMIN_GUARD=false`），内部部署时按需开启。

### 6.4 数据库与 ORM
- 默认使用 **SQLite**（`sqlite:///./cad_translation.db`），可通过 `DATABASE_URL` 切换。
- 使用 **SQLAlchemy 2.0** 语法 + Alembic 迁移。
- 主要模型：`Project`、`ProjectFile`、`ProcessingTask`、`TextExtraction`、`TranslationCache`。

### 6.5 异步任务
- Celery 默认使用 **Redis** 作为 broker。
- 若 Redis 不可用，自动降级为 **local_eager** 同步模式（通过 `ASYNC_TASKS_MODE=auto` 探测）。
- 面向用户交付的包统一设置 `ASYNC_TASKS_MODE=local`，避免依赖外部 Redis。

---

## 7. 发布流程

项目有三种并行的发布管道，均由 PowerShell 脚本驱动。**没有 Docker 或 CI/CD**，构建完全在本地完成。

### 管道 A：运行时交付包（ZIP + BAT）
```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_scale.ps1
```
- 产物：`scale_release/` 目录 + `scale_release.zip`
- 需目标机器安装 Python 3.10+。
- 包含：后端运行时、`frontend/dist/`、`tools/libredwg/`、`start_delivery.bat`。

### 管道 B：独立 EXE（PyInstaller / Nuitka）
```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_scale_exe.ps1
# 或
powershell -ExecutionPolicy Bypass -File scripts/build_scale_exe_nuitka.ps1
```
- 产物：`scale_release_exe/launcher.exe`（含嵌入式 Python 运行时 + `runtime_payload.zip`）
- 目标机器**无需**安装 Python。

### 管道 C：Electron 桌面应用
- 在 `scale_release/` 或 `electron_release/` 中运行 `npm run build`（electron-builder）。
- 产物：NSIS 安装程序或 Portable EXE。
- `electron_release/` 是较早的实验性版本，当前主推的是 PyInstaller/Nuitka 管道。

### 构建脚本的通用行为
- 排除开发文件（`frontend/src`、`node_modules`、测试、缓存、`.env`、`.db`）。
- 对 `runtime_config.local.json` 做 API Key 脱敏（清空 `api_key`，标记 `api_key_source: none`）。
- 支持 `-SkipFrontendBuild` 等参数加速测试构建。

---

## 8. 安全注意事项

1. **Admin Guard 默认关闭**：`ENABLE_ADMIN_GUARD=false`。内部使用时如需保护危险端点，必须在 `backend/.env` 中显式开启并设置 `ADMIN_API_TOKEN`。`JWT_SECRET_KEY` **不作为** admin 回退。
2. **文件路径安全**：后端使用 `resolve_within_directory` 和 `get_safe_filename` 防止路径遍历。修改文件下载/上传逻辑时，必须保留这些校验。
3. **API Key 管理**：运行时配置中的 API Key 在公共接口响应中会被掩码（mask）处理。打包时会被脱敏，但开发环境的 `.env` 和本地 JSON 配置文件仍需妥善保管，勿提交到版本控制。
4. **Windows COM 安全**：COM 转换器（`autocad_converter.py`、`haochen_optimized_converter.py`）通过 `win32com.client` 启动 CAD 软件进程，需确保 CAD 软件已安装且版本兼容。
5. **无 HTTPS**：开发/本地交付模式默认使用 HTTP。若需公网部署，应在前置代理（Nginx/Caddy）上配置 TLS，不要直接暴露 uvicorn。

---

## 9. 关键入口与配置速查

| 用途 | 文件路径 |
|------|---------|
| 后端主入口 | `backend/run_server.py` / `backend/app/main.py` |
| 后端环境配置 | `backend/.env`（模板：`backend/.env.example`） |
| 后端依赖 | `backend/requirements.txt` |
| Celery 启动 | `backend/run_celery.py` |
| 前端主入口 | `frontend/src/main.tsx` |
| 前端 API 封装 | `frontend/src/services/api.ts` |
| 前端构建配置 | `frontend/vite.config.ts` |
| CLI 入口 | `cli/cad_cli.py` |
| CLI 安装配置 | `agent-harness/setup.py` + `agent-harness/pyproject.toml` |
| 统一翻译引擎 | `backend/app/services/llm/translation_service.py` |
| CAD 全流程服务 | `backend/app/services/cad_pipeline_service.py` |
| DWG 转换器 | `backend/app/functions/dwg_converter.py` |
| 文字提取器 | `backend/app/functions/text_extractor.py` |
| 文字回填器 | `backend/app/functions/text_applier.py` |
| 运行时配置服务 | `backend/app/services/runtime_config_service.py` |
| 主构建脚本 | `scripts/build_scale.ps1` |
| 项目规则 | `.trae/rules/project_rules.md` |
| 架构文档 | `docs/modern/ARCHITECTURE.md` |
| API 规范 | `docs/modern/BACKEND_API_SPEC.md`、`docs/modern/FRONTEND_API_SPEC.md` |

---

## 10. 常见问题与排障提示

- **前端页面空白 / 路由不匹配**：当前 `App.tsx` 直接挂载了 `TranslationWorkbenchPage`，没有使用 `react-router-dom` 的路由。新增页面时需手动修改 `App.tsx`。
- **Celery 任务不执行**：检查 Redis 是否运行，或显式设置 `ASYNC_TASKS_MODE=local` 使用同步本地模式。
- **DWG 转换失败**：确认目标机器已安装 AutoCAD / 浩辰 CAD / ZWCAD（COM 模式），或已配置 ODA File Converter 路径，或回退到捆绑的 LibreDWG（`tools/libredwg/`）。
- **Excel 编码问题**：历史文件存在 UTF-8 / GBK 编码混杂，处理时需注意 `pandas` 的 `encoding` 参数。
- **打包后 API Key 丢失**：这是预期行为。打包脚本会脱敏 `runtime_config.local.json`，交付后由用户在界面重新配置。
