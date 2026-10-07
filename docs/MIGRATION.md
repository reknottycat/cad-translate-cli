# 从 standalone 迁移到维护中的 cad-translate

**状态：旧仓兼容/弃用入口；本次仅修改文档，不迁移运行时或用户数据。**
当前维护入口：[cad-translation-web/agent-harness](https://github.com/reknottycat/cad-translation-web/tree/main/agent-harness)。

核对基线：standalone `15659adca42d42c59f274671de9053b0ee83728a`；
canonical `f218e67edb5a53ee4855c96fbc02502e1ed36a7f`。以下比较来自这些版本的源码，
不是对将来版本、第三方脚本或既有 PyPI 发布状态的保证。

## 1. 最小方案与边界

保留 standalone 现有代码、包名、`1.0.1` 版本和所有入口，只将它标明为旧版兼容参考。
新功能与修复进入 canonical 的 `agent-harness` / `backend/app`，不复制实现回来。
不新增自动转发 shim：REPL、onboard、fallback 参数和 JSON 错误契约存在差异，不能无损转发。
也不因代码搜索未返回结果就推断“没有旧用户”。需要某个具体兼容适配时，应先提供调用样例、
预期输出与退出码测试，再单独评审薄适配；不能自动安装、自动迁移配置或吞掉不支持的参数。

本次不改版本号，不创建 tag/release，不执行 PyPI 上传，不删除 Git 历史、配置或任务。
canonical 已明确维护入口，本次无需再改其实现或打包配置。

## 2. 安装引用与包身份

| 已核对入口 | 现状及迁移处理 |
|---|---|
| standalone 根 `README.md` | `pip install -r requirements.txt`、`pip install -e .` 指向旧仓根目录；保留在明确标识的历史说明中 |
| `cli/README.md`、`cli/README_CN.md` | 仍写 `cd agent-harness; pip install -e .`，是沿袭旧布局的说明；不是 standalone 的实际安装目录 |
| `docs/AGENT_GUIDE.md`、`skill/SKILL.md` | 仍有 `python -m cli` / `python -m cli.cad_cli`；只用于旧环境复现，新环境改用 `python -m cad_translate.cli` |
| 旧 `skill/SKILL.md` | 历史正文的 `cli-anything-cad` 包名不是当前两边的 distribution 名称；不要因此重命名同名配置目录 |
| `cli/core/release.py` | 隐藏的 `release build` 调用本地 `python -m build --no-isolation`；其中 `PACKAGE_NAME="cad-translate"` 与旧打包元数据不一致，不可据此识别安装包 |
| canonical 根 README / `agent-harness/README.md` | 完整 checkout 后安装 `backend/requirements.txt` 与 `-e ./agent-harness`；生成的 delivery bundle 则在其 `cli/` 内安装，保持相邻 `backend/` |

| 项目 | standalone | canonical |
|---|---|---|
| distribution | `cad-translate-cli` | `cad-translate` |
| 版本来源 | `pyproject.toml`、`setup.py` 均固定 `1.0.1` | `pyproject.toml` 声明动态版本，`setup.py` 读取相邻 `backend/app/version.py` |
| 同名 console script | `cad-translate = cli.cad_cli:main` | `cad-translate = cad_translate.cli:main` |
| 处理实现 | 仓内 `lib.*` | 直接复用 `backend/app` |

**不要把两个包叠加安装在同一 Python 环境。** 同名 launcher 会产生来源歧义；也不要用卸载其中
一个来假定另一个 launcher 必然完整。使用新的虚拟环境，保留旧环境作回退。
本次未核验包索引是否已有相应发布，不建议裸用 `pip install cad-translate` 作为迁移保证。

完整克隆 canonical，不要只下载 `agent-harness/`：其构建需要相邻的版本文件；运行时后端可通过
`CAD_TRANSLATION_BACKEND_DIR` 定位，但该变量不替代构建时的目录要求。

```bash
git clone https://github.com/reknottycat/cad-translation-web.git
cd cad-translation-web
python -m venv .venv-cad
# 先激活：POSIX 用 source .venv-cad/bin/activate
# Windows PowerShell 用 .\.venv-cad\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
python -m pip install -e ./agent-harness
python -c "from importlib.metadata import distribution; d=distribution('cad-translate'); print(d.metadata['Name'], d.version); print([(e.name, e.value) for e in d.entry_points if e.group == 'console_scripts'])"
python -m cad_translate.cli --version
python -m cad_translate.cli --help
```

期望入口为 `cad_translate.cli:main`。在旧环境识别 distribution 时应查询 `cad-translate-cli`，
不能依赖旧 `release package-info` 的包名或 REPL 横幅版本。
PowerShell 若不激活，可直接调用 `.\.venv-cad\Scripts\python.exe`；POSIX 可用 `.venv-cad/bin/python`。
为复现本次比较，可在新 checkout 安装前检出上面记录的 canonical commit。

## 3. 命令与行为迁移表

| 旧端 | canonical 当前行为 / 操作 |
|---|---|
| `--json`、`--project FILE` | 仍为顶层选项，放在子命令前；不能把“有 JSON 模式”理解成所有 Click 解析错误都保证 JSON |
| 裸 `cad-translate` / `repl` | 裸命令显示帮助，没有 `repl`；改为显式命令，不自动模拟交互会话 |
| `onboard`（含 `--scope project`） | 没有此命令；分开执行 `config set`、`config llm init`、`config validate`。项目配置需明确编辑 `.cli-anything-cadrc`，不存在同名项目引导开关 |
| `project new/open/save/info` | 子命令保留；跨进程不保留会话。后续调用显式传 `--project FILE`；该选项不是自动切换工作目录或项目配置文件的开关 |
| `files list --path`、`files set-input` | 命令保留；`set-input` 不是跨进程持久默认值，流水线仍应传 `-i` |
| `pipeline convert -i [-o] [--backend]` | 主要参数保留 |
| `pipeline extract -i [-o]` | 主要参数保留 |
| `pipeline translate-excel -i [-o] [--source-language] [--target-language] [--translation-mode]` | 主要参数保留 |
| `pipeline apply -i -e [-o] [--translation-mode] [--font-name] [--font-size-reduction]` | 主要参数保留 |
| 文档示例 `--translation-mode newline` | 两边当前 Click 参数和 CAD schema 都只接受 `add/replace`；这是历史文档错误，不是新端删除了可用选项，不自动替换为其他模式 |
| `tasks list/show/delete/clear` | 命令保留，但存储校验与锁实现已变化；迁移验证不执行 delete/clear |
| `config show/get/set/validate` | 命令保留；`config show` 新端不再提供旧端的 `detected_backends`；`set` 默认仍写全局配置，不等价于旧 onboard 的项目 scope |
| `config llm show/init/test` | 命令保留；新 `init` 交互主要询问 URL/model，不应依赖旧 API key 提示流程；密钥通过本地安全配置或环境提供 |
| `config llm init/test --fallback-*` | 新 Click 命令未注册这些旧参数。改用嵌套配置的 `llm.fallback_models`，保留列表顺序；不要因缺少开关就断言后端无 fallback 能力 |
| 隐藏 `release package-info/build/smoke` | 新端没有这组命令；安装验收用本指南，构建交付按 canonical 文档，不自动发布 |
| 无 `--version` / `doctor` | 新端提供；`doctor` 报告路径与配置状态，不代表 CAD 许可证或真实转换已通过 |
| JSON `error_type` | 旧端常见 `artifact_error/usage_error/dependency_error/processing_error`；新端相应受捕获异常使用类名，如 `FileNotFoundError/ValueError/RuntimeError/OSError`。调用方须重新验收错误分支 |

不要承诺流水线结果对象、task 元数据或所有异常行为逐字段兼容。先用副本验证调用方实际读取的字段、
退出码和产物，再切换业务脚本；不要只做字符串替换。

## 4. 配置格式、路径及优先级

| 项目 | 核对结果与迁移注意 |
|---|---|
| 全局 JSON | 两边实际默认均为 `$XDG_CONFIG_HOME/cli-anything-cad/config.json`；未设置 XDG 时为 `~/.config/cli-anything-cad/config.json`；可用 `CAD_TRANSLATION_RUNTIME_CONFIG_FILE` 覆盖 |
| 历史文档路径 | `~/.config/cad-translate/config.json`、`.cad-translaterc` 与当前源码不符；不要按文档路径盲目移动或覆盖实际文件 |
| 项目 JSON | 两边均读取**当前工作目录**的 `.cli-anything-cadrc`，不是自动从 `--project FILE` 所在目录读取 |
| `.env` | 旧端默认旧仓根 `.env`；新端默认 canonical 的 `backend/.env`；两边均支持 `CAD_TRANSLATION_ENV_FILE` |
| 共享 schema | 保留 `cad`、`llm.primary`、`llm.fallback_models`、`include` 等；两端都有纯扁平旧格式归一化，不需另写批量转换器。混合扁平/嵌套文件需单独核验 |
| include / 相对路径 | include 相对于引用它的 JSON 文件；复制配置时需保留或调整 include 路径，并核对术语库、转换器和输出路径，不可仅复制单个 JSON 后假定等价 |
| 新端扩展 | `llm.provider_profiles`、锁与原子写入等不应回灌旧实现；也不要让旧端回写新端已更新的共享配置 |
| 环境覆盖 | 新端 ConfigManager 在 CAD 覆盖之外，还显式纳入 `LLM_*` / `TRANSLATION_PROVIDER` 等变量，并从有效 settings 建立默认值；同一 JSON 不代表两端最终生效值相同 |
| 输出/任务 | 两端均使用配置输出根下 `cad_tasks/`；默认基目录由旧仓根变为 canonical 的 backend。新端增加生命周期锁并校验 task ID。保留旧任务；先在新的 `OUTPUT_DIR` 验证 |

先备份真实的全局配置、当前工作目录的项目配置、include 文件及原输出目录；密钥和配置不要提交到 Git。
配置变量必须在 CLI 进程启动前设置。**虚拟环境只隔离包，不隔离上述共享 JSON。**
将配置副本指向单独的 `CAD_TRANSLATION_RUNTIME_CONFIG_FILE`，项目文件在单独工作目录测试；
`OUTPUT_DIR` 与 `CAD_TRANSLATION_DEFAULT_OUTPUT_DIR` 都指向新的目录，避免任务存储和 CAD 默认输出混用旧路径。

配置的建议形状如下，真实 endpoint、model、fallback 和密钥由用户在本地补齐，不自动猜测：

```json
{
  "cad": {"target_language": "ru", "translation_mode": "replace"},
  "llm": {
    "primary": {"provider": "custom", "format": "openai_compatible"},
    "fallback_models": []
  }
}
```

旧扁平 `provider/model/base_url/...` 对应 `llm.primary`；旧扁平 `fallback_models` 对应
`llm.fallback_models`；CAD 默认项放入 `cad`。这里是迁移说明，不是允许覆盖原文件的自动转换程序。
`config llm init` 和 `config llm test` 会发起连接测试，不属于下面的离线冒烟检查。

## 5. 验证与回退

文档变更验收（在 standalone PR 分支）：

```bash
git diff --check 15659adca42d42c59f274671de9053b0ee83728a...HEAD
git diff --name-only 15659adca42d42c59f274671de9053b0ee83728a...HEAD
git diff --exit-code 15659adca42d42c59f274671de9053b0ee83728a...HEAD -- '*.py' '*.toml' requirements.txt .github
```

只应出现本次文档文件；Python、打包元数据、依赖及 workflow 不应改变。

离线入口检查（canonical 完整 checkout 根目录，使用新虚拟环境的 Python）：将下面代码保存到临时位置
后执行。它只在新建临时目录中运行，不删除该目录、不触及旧配置、不调用 CAD 转换或 LLM API。
`config validate` 只是配置结构检查，不是翻译可用性证明。

```python
import os
from pathlib import Path
import subprocess
import sys
import tempfile

repo = Path.cwd().resolve()
assert (repo / "backend/app/version.py").is_file(), "Run from the canonical repo root"
scratch = Path(tempfile.mkdtemp(prefix="cad-cli-migration-"))
(scratch / ".env").write_text("", encoding="utf-8")
(scratch / "config.json").write_text("{}\n", encoding="utf-8")
env = os.environ.copy()
for key in list(env):
    if key.startswith(("CAD_TRANSLATION_", "LLM_", "DEFAULT_", "DWG_", "ODA_", "LIBREDWG_")):
        env.pop(key)
env.pop("TRANSLATION_PROVIDER", None)
env.update({
    "CAD_TRANSLATION_BACKEND_DIR": str(repo / "backend"),
    "CAD_TRANSLATION_ENV_FILE": str(scratch / ".env"),
    "CAD_TRANSLATION_RUNTIME_CONFIG_FILE": str(scratch / "config.json"),
    "OUTPUT_DIR": str(scratch / "outputs"),
    "CAD_TRANSLATION_DEFAULT_OUTPUT_DIR": str(scratch / "outputs"),
})
for args in (
    ["--version"], ["--help"], ["doctor"],
    ["--json", "config", "show"], ["config", "validate"],
    ["pipeline", "apply", "--help"], ["config", "llm", "init", "--help"],
):
    subprocess.run([sys.executable, "-m", "cad_translate.cli", *args],
                   cwd=scratch, env=env, check=True)
print("Scratch directory retained:", scratch)
```

在 POSIX 可将代码放入 `python - <<'PY' ... PY`；PowerShell 可保存临时 `.py` 后调用虚拟环境的 Python。
随后人工在配置副本上核对 `config show` 的路径和来源、LLM/fallback、术语库、输出目录；
真实 DXF 提取/回填、Windows DWG/COM 和在线 LLM 测试另行执行，保留原输入及输出证据。
回退时使用保留的旧虚拟环境、旧配置和旧输出根；本方案不会要求重新生成旧数据或重写历史。

## 源码证据

- [旧打包定义](https://github.com/reknottycat/cad-translate-cli/blob/15659adca42d42c59f274671de9053b0ee83728a/pyproject.toml)；[旧命令注册](https://github.com/reknottycat/cad-translate-cli/blob/15659adca42d42c59f274671de9053b0ee83728a/cli/cad_cli.py)。
- [旧配置路径](https://github.com/reknottycat/cad-translate-cli/blob/15659adca42d42c59f274671de9053b0ee83728a/lib/config.py)；[旧配置 schema](https://github.com/reknottycat/cad-translate-cli/blob/15659adca42d42c59f274671de9053b0ee83728a/lib/services/config_manager.py)。
- [canonical 打包](https://github.com/reknottycat/cad-translation-web/blob/f218e67edb5a53ee4855c96fbc02502e1ed36a7f/agent-harness/pyproject.toml)；[版本读取](https://github.com/reknottycat/cad-translation-web/blob/f218e67edb5a53ee4855c96fbc02502e1ed36a7f/agent-harness/setup.py)；[命令注册](https://github.com/reknottycat/cad-translation-web/blob/f218e67edb5a53ee4855c96fbc02502e1ed36a7f/agent-harness/cad_translate/cli.py)。
- [canonical 后端桥接](https://github.com/reknottycat/cad-translation-web/blob/f218e67edb5a53ee4855c96fbc02502e1ed36a7f/agent-harness/cad_translate/bridge.py)；[配置路径](https://github.com/reknottycat/cad-translation-web/blob/f218e67edb5a53ee4855c96fbc02502e1ed36a7f/backend/app/config.py)；[配置 schema](https://github.com/reknottycat/cad-translation-web/blob/f218e67edb5a53ee4855c96fbc02502e1ed36a7f/backend/app/services/config_manager.py)；[任务存储](https://github.com/reknottycat/cad-translation-web/blob/f218e67edb5a53ee4855c96fbc02502e1ed36a7f/agent-harness/cad_translate/store.py)。
