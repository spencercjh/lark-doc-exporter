# Remove Legacy Markdown and Rendered PDF Design

## Goal

Turn `lark-doc-exporter` into a URL-only Feishu document exporter with exactly
two supported artifact paths:

- Markdown always comes from `feishu-docx`
- PDF always comes from Feishu native export

This change removes all remaining transitional surfaces around the old
`lark-cli` Markdown exporter and the local rendered-PDF pipeline.

## Why This Change

The repo is still carrying several transitional contracts that no longer match
the desired product direction:

- a deprecated `legacy` Markdown provider still exists in code, docs, help, and
  tests
- provider selection is still exposed through
  `LARK_DOC_EXPORTER_MARKDOWN_PROVIDER`
- bare token inputs are still treated as historical compatibility cases
- rendered PDF keeps Chromium, theme, and extra CSS surfaces alive even though
  native PDF is now sufficient

Those compatibility layers make the product boundary ambiguous. Operators can
still read the tool as "mostly old behavior, with a preferred new path" instead
of "a native-PDF exporter with `feishu-docx` Markdown support."

This milestone makes the contract explicit and removes the transitional story.

## Chosen Product Boundary

The tool will support exactly this outward behavior:

1. `--doc` must be a URL-shaped Feishu/Lark document reference for every run.
2. Markdown output uses `feishu-docx` directly and never falls back to
   `lark-cli`.
3. PDF output uses only the native Feishu export path.
4. Rendered PDF, local HTML/CSS theming, and Chromium runtime requirements are
   removed.

Combined exports remain valid:

- `--formats markdown,pdf` runs the Markdown pipeline and the native-PDF
  pipeline in one command
- the two outputs are produced by different internal stages, not by one shared
  provider-selection layer

## Non-Goals

This milestone does **not** try to:

- remove every `lark-cli` dependency from the repository
- change the current synced-block expansion strategy used for native PDF
- add support for token-only refs, non-doc URLs, or other Feishu resource types
- add new authentication flags to the CLI
- redesign unrelated parts of the JSON result payload outside the fields touched
  by the removed CLI/provider surfaces

## CLI and Input Contract

### URL-only input

The tool should reject any `--doc` input that is not a URL-shaped document
reference.

This rule applies to all supported command shapes:

- markdown-only
- pdf-only
- markdown + pdf

There is no compatibility exception for native-PDF-only runs. Token-only input
should fail fast with an error that clearly says the tool now accepts full
document URLs only.

### Markdown contract

If the run needs Markdown artifacts, the tool must:

1. validate the URL-shaped doc ref
2. validate `feishu-docx` availability
3. validate credentials/config discovery
4. export with `feishu-docx`
5. normalize the produced Markdown/assets into `lark-doc-exporter`'s outward
   layout

There is no provider selection mode and no compatibility fallback.

### PDF contract

PDF output is always native Feishu PDF:

1. fetch XML via `lark-cli`
2. expand synced references
3. create the temp doc
4. export native PDF
5. run the existing footer post-process

The CLI no longer offers a rendered-vs-native decision.

### `--pdf-mode` compatibility decision

This spec treats `--pdf-mode` as a compatibility shell, not as an immediately
deleted argument.

Implementation contract:

- `--pdf-mode native` remains accepted for this release
- omitting `--pdf-mode` behaves the same as `--pdf-mode native`
- any other value, including `rendered`, must fail
- help/docs should describe native PDF as the only supported PDF path and should
  not present `--pdf-mode` as a meaningful choice anymore

This keeps existing command invocations and bundled skill examples from breaking
on argument parsing alone while still removing rendered mode as a product
feature.

### Removed CLI surface

Remove these user-facing options and concepts:

- `LARK_DOC_EXPORTER_MARKDOWN_PROVIDER`
- `legacy` / `auto` / `feishu-docx` provider modes
- `--pdf-mode rendered`
- `--theme`
- `--css`

The help text, README examples, bundled skill docs, and doctor output should be
rewritten so they describe only the supported contract, not the removed one.

## JSON Result Contract

This release must explicitly preserve or remove result fields rather than
letting them drift as a side effect of the implementation.

### Fields to preserve

Keep these result fields because they still describe real behavior after the
change and are already covered by tests/snapshots:

- `ok`
- `doc`
- `expanded_references`
- `temp_doc_token`
- `temp_doc_deleted`
- `temp_doc_url`
- `localized_images`
- `ai_footer_postprocess`
- `warnings`
- `outputs`
- `pdf_mode`
- `pdf_renderer`

Field semantics after the change:

- `pdf_mode` stays present only when `"pdf"` is in `formats`, and its value is
  always `"native"`
- `pdf_renderer` stays present only when `"pdf"` is in `formats`, and its value
  is always `"feishu-native"`
- `temp_doc_*` fields remain meaningful because the native-PDF stage still uses
  temp docs
- `expanded_references` remains meaningful because the native-PDF stage still
  expands synced references

### Fields to remove

Remove these result fields because they only exist to expose the provider
selection story that this spec deletes:

- `markdown_provider`
- `markdown_provider_detail`
- `theme`

There is no replacement `markdown_provider` field because Markdown no longer
has runtime provider choice. The contract becomes structural: Markdown output,
when requested, always comes from `feishu-docx`.

### Combined export behavior

For `--formats markdown,pdf`, the result payload must still reflect both
pipelines in one object:

- Markdown output appears under `outputs["markdown"]`
- PDF output appears under `outputs["pdf"]`
- `pdf_mode="native"` and `pdf_renderer="feishu-native"` remain present
- `temp_doc_*` / `expanded_references` describe the native-PDF half of the run
- there is no Markdown-provider metadata anymore

## Dependency and Credential Contract

### `feishu-docx`

Markdown readiness now means exactly:

- the `feishu-docx` package is importable
- credentials are available from environment or `~/.feishu-docx/config.json`
- the doc ref is URL-shaped and compatible with `feishu-docx`

If any of those checks fail, the run should fail immediately with a direct
message. The system should not describe the situation as "falling back" or
"continuing in compatibility mode."

### `lark-cli`

`lark-cli` remains required for the native-PDF path. It is no longer described
as a Markdown fallback dependency. Doctor output should reflect that narrower
role.

## Architecture

### 1. Remove provider selection as a concept

`src/lark_synced_export/feishu_docx_bridge.py` should stop answering "which
Markdown provider was selected?" and instead answer narrower questions:

- is this doc ref a supported full URL?
- are `feishu-docx` credentials available?
- is `feishu-docx` importable?
- how should the exporter call be made?

That module becomes a readiness/validation adapter, not a policy router.

### 2. Split the exporter into explicit stages

`src/lark_synced_export/exporter.py` should expose two explicit internal stages:

- **Markdown stage**
  - call `feishu-docx`
  - normalize Markdown/assets
  - normalize user mentions and callouts
- **Native PDF stage**
  - prepare the temp doc from XML
  - export native PDF
  - run footer post-processing

The top-level `export_document()` should orchestrate stages based on requested
formats. It should not branch on a provider enum and should not carry rendered
PDF responsibilities.

### 3. Preserve output layout compatibility where still intentional

Even though the provider changes, the outward Markdown artifact layout should
stay stable:

- Markdown file: `<output-dir>/<stem>.md`
- localized assets: `<output-dir>/images/...`

`feishu-docx`'s raw staging layout should remain an internal detail.

### 4. Delete rendered-only internals

Rendered-PDF-only helpers should be removed rather than left as dead code. This
includes Chromium readiness checks and any helper modules used only for HTML/CSS
rendered PDF generation.

## File-Level Change Boundaries

### Core modules

- `src/lark_synced_export/feishu_docx_bridge.py`
  - remove provider env parsing
  - remove `legacy` selection/fallback code
  - keep URL validation, credential discovery, and `feishu-docx` export helper
- `src/lark_synced_export/exporter.py`
  - remove rendered-PDF path
  - remove provider-based Markdown branching
  - introduce explicit Markdown/native-PDF stage organization
- `src/lark_synced_export/cli.py`
  - remove rendered-only flags and provider language
  - keep command help aligned with URL-only + native-PDF contract
- `src/lark_synced_export/doctor.py`
  - remove Chromium check
  - report only `lark-cli` native-PDF readiness and `feishu-docx` Markdown
    readiness

### Rendered-only cleanup

Delete or fully orphan-check any modules that exist only to support rendered
PDF, such as `pdf_runtime.py` and any HTML render helpers. The repo should not
ship inert rendered-mode machinery after this change.

### Docs and packaging

- `README.md`
  - rewrite usage, prerequisites, doctor guidance, and examples
- `src/lark_synced_export/skill_assets/lark-doc-exporter/SKILL.md`
  - keep bundled skill guidance aligned with the new contract
- `pyproject.toml`
  - bump the version
  - remove rendered-only dependencies if no longer used
- `src/lark_synced_export/__init__.py`
  - update `__version__`
- `uv.lock`
  - refresh the lockfile after dependency changes

## Error Handling

Errors should become more direct after this change:

- invalid doc ref: fail with "full document URL required" style wording
- missing `feishu-docx` package: fail with explicit dependency/setup wording
- missing credentials/config: fail with explicit credential-setup wording
- missing `lark-cli`: fail only in contexts that need native PDF or doctor

Do not reuse wording that implies the run might continue through a deprecated
path. That path no longer exists.

## Testing Strategy

### Rewrite the compatibility tests into strict-contract tests

- `tests/test_feishu_docx_bridge.py`
  - replace auto/fallback/provider-mode assertions with URL validation,
    dependency checks, and credential-discovery assertions
- `tests/test_exporter.py`
  - verify Markdown-only uses only the `feishu-docx` stage
  - verify PDF-only uses only the native-PDF stage
  - verify combined export runs both explicit stages
  - verify token-only / non-URL refs fail across the tool contract
- `tests/test_cli.py`
  - remove assertions for provider env and rendered-mode flags
  - add assertions for the tightened help/argument contract
- `tests/test_doctor.py`
  - remove Chromium coverage
  - assert the narrower readiness messages

### Delete obsolete tests

Delete or rewrite tests that exist only for:

- `legacy` provider selection
- auto fallback behavior
- rendered PDF / Chromium / theme / CSS flows

### Planned regression pass

At minimum, implementation should re-run:

- `make lint`
- `uv run pytest tests/test_feishu_docx_bridge.py tests/test_exporter.py tests/test_cli.py tests/test_doctor.py tests/test_release_version.py -q`
- `uv run pytest tests/test_skill_install.py -q`

In addition, the implementation must verify the spec-touched snapshot/live
surface for the native lane:

- `uv run pytest tests/test_public_doc_e2e.py -q`

If dependency cleanup or repo-wide shared behavior changes, run a broader
`pytest` pass before pushing.

## Release Semantics

This should be treated as a breaking release, not a compatibility patch.

The release narrative should explicitly say that the tool removed:

- the old `lark-cli` Markdown export path
- provider-selection surface
- rendered PDF mode
- token-only input compatibility

The replacement contract should be stated just as explicitly:

- full document URL required
- Markdown via `feishu-docx`
- PDF via native Feishu export

## Review Notes

The implementation plan should assume that another agent will review this spec
before coding begins. The plan should therefore inherit this document as the
single source of truth instead of revisiting product-boundary decisions during
implementation.
