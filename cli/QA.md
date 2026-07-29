# cli-anything-cad QA Report

## Scope

This report summarizes the currently known issues, risks, and operational
limitations observed in the local CAD CLI harness as of 2026-03-16.

## Rebuild Note (2026-03-25)

The CAD CLI is currently being rebuilt to align with the CLI-Anything harness
standard. The previous implementation has been archived at
`agent-harness/cad-translate_legacy/` and is intentionally excluded from the
runtime surface, packaging, and pytest discovery.

`CLI-Anything` itself is treated as a development-time reference/skill package
and is not a runtime dependency of this CLI.

This QA report is still useful as a problem inventory, but some items may shift
in priority as the harness skeleton is simplified first, then CAD-specific
features are reintroduced on top of the new structure.

## High Priority Issues

### 1. HaoChen COM can be detected but still fail during save

- Symptom:
  the backend probe may report `haochen_com` as detected, but actual conversion
  can still fail later if the local HaoChen installation is present but not
  licensed for save/export.
- Impact:
  automatic backend selection may still try HaoChen first unless it is disabled
  explicitly.
- Current mitigation:
  backend probing plus fallback order reduces user impact, and disabled backends
  are skipped.
- Recommended next step:
  add a stronger save-capability probe and auto-demote backends that fail a
  lightweight health conversion.

### 2. OpenRouter free models remain vulnerable to upstream rate limiting

- Symptom:
  live translation requests can still return `429` even when config and
  connectivity are correct.
- Impact:
  large translation batches may pause, retry, or fall back more often than
  expected.
- Current mitigation:
  primary/fallback model probing is implemented and NVIDIA direct provider is
  supported as a backup.
- Recommended next step:
  add per-provider retry policy tuning and a user-visible provider health
  summary command.

### 3. Project-level config exists structurally but write tooling is still global-first

- Symptom:
  the config system resolves `.cli-anything-cadrc`, but current `config set`
  writes to the global main config file.
- Impact:
  users can read project overrides, but cannot yet conveniently write them via
  CLI.
- Current mitigation:
  manual project config files already work.
- Recommended next step:
  add `--scope project|global` to `config set/unset`.

## Medium Priority Issues

### 4. DWG backend capability is not yet surfaced as a clear matrix

- Symptom:
  users do not yet get an explicit summary of which backend is best for image
  retention, speed, or local availability.
- Impact:
  troubleshooting backend behavior still depends on reading docs or trial/error.
- Current mitigation:
  `config show` exposes detected backends and disabled backends.
- Recommended next step:
  add a `doctor` or `backends inspect` command with capability notes.

### 5. Large Excel translation batches are slower and less deterministic than CAD steps

- Symptom:
  extraction/apply are stable locally, but online translation speed depends on
  model latency and provider behavior.
- Impact:
  users may assume the whole pipeline is stalled, when the delay is actually in
  the LLM stage.
- Current mitigation:
  glossary support, prompt modes, and model fallback already reduce failure
  rates.
- Recommended next step:
  add progress indicators, per-batch logging, and resumable translation output.

### 6. Config editing is still command-line centric

- Symptom:
  `config show/get/set/validate` are available, but there is no `config unset`
  or `config edit`.
- Impact:
  removing values or quickly fixing nested config remains less convenient than
  it could be.
- Recommended next step:
  add `config unset` and `config open`.

## Low Priority Issues

### 7. Documentation is split across several Markdown files

- Symptom:
  operational details live in `README.md`, `TEST.md`, and now this QA report.
- Impact:
  onboarding is fine, but there is still some duplication.
- Recommended next step:
  add a shorter top-level doc index or command reference table.

### 8. Warning debt remains in dependencies and older schemas

- Symptom:
  test runs still emit Pydantic v1-style validator warnings, SQLAlchemy
  deprecation warnings, and openpyxl datetime warnings.
- Impact:
  not blocking, but it adds noise and hides real regressions.
- Recommended next step:
  schedule a dependency cleanup pass.

## Current Overall Assessment

- CAD local workflow:
  usable
- DXF extract/apply:
  stable
- DWG auto conversion:
  usable with fallback, but backend capability varies
- LLM configuration:
  strong
- LLM batch reliability:
  acceptable with fallback, still provider-dependent
- Configuration architecture:
  now in good shape, but project-scope write support is the next missing piece
