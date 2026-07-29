# cad-translate

`cad-translate` is an installable CLI harness for local CAD translation
workflows.

## Rebuild Status (2026-03-25)

This CAD CLI is being re-centered around the CLI-Anything harness standard
(Click + REPL + JSON output + real backend integration + tests/docs/publish).

`CLI-Anything` itself is treated as a development-time reference/skill package
and is not a runtime dependency of this CLI.

The previous implementation has been archived at `agent-harness/cad-translate_legacy/`.
`cad_legacy` is not part of the runtime surface, is excluded from packaging and
pytest discovery, and should not be imported by new code.

All future CAD specialized features and bugfixes should land in `cli/`.

## Command Surface

The harness-style top-level commands are:

- `onboard`
- `config`
- `project`
- `files`
- `pipeline`
- `tasks`
- `repl` (default when no subcommand is given)

Note: `release` commands still exist, but they are hidden from the top-level `--help`
to keep the minimal harness surface focused.

## Install

```bash
cd agent-harness
pip install -e .
```

Windows note:

- editable install created the launcher under
  `<USER>\AppData\Roaming\Python\Python312\Scripts`
- if `cad-translate` is not found, add that directory to `PATH` or call the
  generated `cad-translate.exe` directly

## Beginner Flow

```bash
cad-translate onboard
cad-translate release build
cad-translate release smoke
```

That is the recommended local release loop:

1. `release build` creates local package artifacts under `agent-harness/dist`
2. `release smoke` checks that the CLI can start and run a smallest useful command

If you want to inspect the package before building:

```bash
cad-translate release package-info
```

## Daily Usage

```bash
cad-translate --help
cad-translate onboard
cad-translate
cad-translate --json project new --name demo
cad-translate config show
cad-translate config get cad.target_language
cad-translate config set cad.target_language ru
cad-translate config validate
cad-translate config set --target-language ru --translation-mode add
cad-translate files list --path .
cad-translate pipeline translate-excel -i ".\output\sample_extracted_texts.xlsx" --target-language en
cad-translate pipeline extract -i ".\sample.dxf" -o ".\output"
cad-translate pipeline apply -i ".\sample.dxf" -e ".\output\sample_extracted_texts.xlsx" -o ".\output" --translation-mode replace
```

Recommended config workflow:

```bash
cad-translate config validate
cad-translate config show
cad-translate config get cad.target_language
cad-translate config set cad.target_language ru
cad-translate config set cad.translation_mode add
```

LLM setup flow:

```bash
cad-translate config llm show
cad-translate config llm test --format openai_compatible --provider openrouter --model stepfun/step-3.5-flash:free --api-key <your-key>
cad-translate config llm init --format openai_compatible --provider openrouter --model stepfun/step-3.5-flash:free --api-key <your-key> --base-url https://openrouter.ai/api/v1 --non-interactive
cad-translate config llm init --format openai_compatible --provider openrouter --model stepfun/step-3.5-flash:free --api-key <your-key> --system-prompt-mode cad_specialized --glossary-file ..\\backend\\DocuTranslate.csv --base-url https://openrouter.ai/api/v1 --non-interactive
cad-translate config llm init --format openai_compatible --provider openrouter --model nvidia/nemotron-3-super-120b-a12b:free --api-key <your-key> --reasoning-enabled --base-url https://openrouter.ai/api/v1 --non-interactive
cad-translate config llm init --format openai_compatible --provider nvidia --model moonshotai/kimi-k2.5 --api-key <your-nvapi-key> --reasoning-enabled --base-url https://integrate.api.nvidia.com/v1 --non-interactive
cad-translate config llm init --format openai_compatible --provider openrouter --model nvidia/nemotron-3-super-120b-a12b:free --api-key <your-openrouter-key> --base-url https://openrouter.ai/api/v1 --fallback-provider nvidia --fallback-model moonshotai/kimi-k2.5 --fallback-api-key <your-nvapi-key> --fallback-base-url https://integrate.api.nvidia.com/v1 --fallback-reasoning-enabled --non-interactive
cad-translate config llm init --format anthropic --provider anthropic --model claude-3-5-haiku-latest --api-key <your-key> --base-url https://api.anthropic.com/v1 --non-interactive
cad-translate config llm init --format google --provider google --model gemini-2.0-flash --api-key <your-key> --base-url https://generativelanguage.googleapis.com/v1beta --non-interactive
cad-translate config llm init --format ollama --provider ollama --model qwen2.5:7b --base-url http://127.0.0.1:11434 --non-interactive
cad-translate config llm init --format lmstudio --provider lmstudio --model local-model --base-url http://127.0.0.1:1234/v1 --non-interactive
cad-translate config llm init --format openai_compatible --provider openrouter --model stepfun/step-3.5-flash:free --api-key <your-key> --system-prompt-mode custom --custom-system-prompt "Translate CAD labels conservatively and preserve tag numbering." --base-url https://openrouter.ai/api/v1 --non-interactive
```

Supported LLM formats:

- `openai_compatible`: OpenAI, OpenRouter, DashScope, SiliconFlow, many gateways
- `nvidia`: NVIDIA direct chat endpoint, useful as a backup when OpenRouter free models are rate-limited
- `anthropic`: Claude native API
- `google`: Gemini / AI Studio native API
- `ollama`: local Ollama server, no API key required
- `lmstudio`: local LM Studio server, API key usually not required

Reasoning support:

- `--reasoning-enabled` adds OpenRouter/OpenAI-compatible `reasoning: {"enabled": true}` to requests
- useful for reasoning-capable models such as `nvidia/nemotron-3-super-120b-a12b:free`
- for `provider=nvidia`, `--reasoning-enabled` sends `chat_template_kwargs: {"thinking": true}`

Unified config model:

- the single main config file lives at
  `~/.config/cad-translate/config.json`
- project-local overrides live only in the current working directory as
  `.cad-translaterc`
- the config schema is nested and validated before use:
  - `cad.target_language`
  - `cad.translation_mode`
  - `cad.font_name`
  - `cad.font_size_reduction`
  - `cad.default_output_dir`
  - `cad.converter_backend`
  - `llm.primary`
  - `llm.fallback_models`
  - `llm.system_prompt_mode`
  - `llm.glossary_file`
- config precedence is:
  `CLI flags > environment variables > project config > user global config > built-in defaults`
- nested config is deep-merged, so setting one field does not wipe sibling fields
- config fragments can be imported with `include` inside the main JSON file
- the unified config file is local machine/runtime state and should not be committed

Config commands:

- `config show` shows the effective merged config summary plus the global and project config paths
- `config get cad.target_language` reads a single resolved value using dot-path syntax
- `config set cad.target_language ru` writes one validated value by dot-path
- `config set --target-language ru --translation-mode add` writes validated CAD defaults into the main global config file
- `config validate` validates the effective merged config and reports schema errors before a run
- path-based `config set` accepts JSON-compatible values when needed, for example
  booleans, numbers, arrays, or objects

CAD config behavior:

- `cad-translate config set --target-language ru` saves Russian as the default target language
- `cad-translate config set --translation-mode add` means translated CAD text is inserted below the original text
- `cad-translate config set --translation-mode replace` means translated CAD text replaces the original text
- `pipeline apply` can override that default for one run with `--translation-mode add|replace`
- `pipeline translate-excel` uses the saved default target language unless you pass `--target-language` explicitly

Primary and fallback behavior:

- `config llm init` can save one primary model plus one simple fallback from CLI flags
- fallback settings are written as `fallback_models` in the runtime JSON config
- before each translation request, the CLI/backend probes the primary model first
- if the primary model is unavailable, missing a key, or returns retryable upstream failures such as `429` or `5xx`, the service automatically moves to the next fallback model
- current fallback chain is visible in `cad-translate config llm show`

Supported system prompt modes:

- `default`: built-in general translation prompt, plus optional inferred terminology hints from the first task samples
- `cad_specialized`: built-in CAD-focused prompt for labels, tags, units, and drawing consistency
- `custom`: your own full system prompt

Glossary behavior:

- if `backend/DocuTranslate.csv` exists, it is auto-detected in `default` mode unless you override it
- user-supplied glossary files can be `csv`, `xlsx`, or `xls`
- glossary terms are converted into a compact AI-readable rule block before each translation request

## Dependencies

- Python runtime dependencies from `setup.py`
- local backend source under `backend/`
- one of the DWG conversion backends below

DWG conversion backends:

- default mode is `auto`
- `auto` tries `haochen_com -> autocad_com -> oda`
- `haochen_com` uses the copied in-project script at
  `backend/app/services/haochen_optimized_converter.py`
- `autocad_com` uses the copied in-project script at
  `backend/app/services/autocad_converter.py`
- `oda` uses local `ODAFileConverter.exe`

Background-mode note:

- the CLI only does local background work
- if `ODA File Converter` is missing, the CLI reports the official install page
  instead of opening a browser for you
- the copied COM converter scripts set CAD visibility to hidden when they
  launch a new COM application instance

Operational caveats:

- `haochen_com` may be detected but still fail at save-time if the local HaoChen
  license is unavailable
- `autocad_com` and `haochen_com` remain Windows-only
- free OpenRouter models can still hit upstream `429` limits, so a fallback
  provider is strongly recommended
- large Excel translation batches are still slower than CAD extraction/apply and
  are bounded by upstream model latency

## Command Groups

- `project`: create, open, save, inspect lightweight CLI project state
- `files`: scan local directories and set an active input file
- `pipeline`: convert, extract, and apply CAD processing steps
- `tasks`: inspect generated task artifacts
- `config`: inspect current session-oriented defaults
- `config set`: save default target language, translation mode, font, and other CAD defaults into the unified runtime JSON config
- `release`: build, inspect, and smoke-test the local package
- `repl`: default interactive mode

## Testing

```bash
python -m pytest cli/tests/test_core.py -v
python -m pytest cli/tests/test_full_e2e.py -v -s
python -m pytest tests/backend/test_backend_runtime.py -k "translation_config_can_be_updated_and_read_back or translation_test_connection_uses_models_endpoint or translation_test_connection_supports_ollama_without_api_key or llm_translate_text_applies_cad_prompt_and_glossary or llm_translate_text_supports_excel_glossary or llm_translate_batch_uses_inferred_preferences_in_default_mode or llm_openai_request_includes_reasoning_when_enabled or nvidia_provider_uses_provider_specific_env_key_and_kimi_default_model or llm_nvidia_request_uses_chat_template_kwargs_when_reasoning_enabled" -v -s
```

Rebuild note:

- tests are expected to import and validate only `cad-translate`
- the archived tree `cad-translate_legacy` is intentionally excluded

Manual DWG converter check:

```bash
cad-translate pipeline convert -i ".\1360001401 施工图.dwg" -o ".\output\auto_manual_check"
```

Installed-command verification:

```bash
$env:CLI_ANYTHING_FORCE_INSTALLED='1'
python -m pytest cli/tests/test_full_e2e.py::TestCLISubprocess -v -s
```

See also:

- `QA.md` for current issues and known limitations
- `improve.md` for recommended next engineering steps
