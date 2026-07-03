# feishu-docx Markdown Integration Design

## Goal

Replace `lark-doc-exporter`'s primary Markdown export path with the existing
`feishu-docx` Python package while preserving the current
`lark-doc-exporter` CLI surface as much as possible.

The intent is not to maintain a second long-lived Markdown parser in
`lark-doc-exporter`. `lark-doc-exporter` should become a thin product wrapper:

- keep its current CLI / skill / PDF-native value
- delegate rich-block Markdown export to `feishu-docx`
- keep the current `lark-cli`-based Markdown flow only as a compatibility
  fallback, not as the preferred semantic layer

## Why This Change

The current `lark-cli` Markdown export path is now known to be lossy for real
Feishu docs:

- `sheet` can collapse into raw `<sheet></sheet>`
- attachments can collapse into raw `<figure view-type="Card"></figure>`
- document mentions can leak as raw `<cite ...>`
- export behavior can change shape over time (for example async native-PDF task
  results)

The repo already has test evidence for these failure modes. The follow-up
question is no longer whether the current Markdown line is weak; it is how to
stop owning that parser behavior ourselves.

`feishu-docx` is the strongest existing candidate because it already exposes:

- Python API
- CLI
- local asset download
- support claims for `sheet`, `bitable`, `synced block`, `add-ons`,
  `attachments`
- MIT license

## Chosen Product Boundary

Use **Python package integration** (`方案 B`) instead of shelling out to the
`feishu-docx` CLI.

Why this is the right boundary:

- it keeps `lark-doc-exporter`'s current CLI / JSON result shape under our
  control
- it avoids binding our UX to another CLI's flags / stdout contract
- it keeps room for our existing native-PDF path and skill packaging
- it makes later test seams cleaner than subprocess delegation

## Non-Goals

This milestone does **not** try to:

- rewrite `feishu-docx`
- design a new long-term parser inside `lark-doc-exporter`
- remove every `lark-cli` dependency from the repo
- solve every authentication model in one step
- refactor the already-shipped native-PDF footer path

## Release / Dependency Decision

Do **not** depend on released PyPI `feishu-docx==0.2.6` for the first
integration milestone.

Reason:

- local upstream inspection shows `v0.2.6` predates standard-export synced-block
  expansion
- the relevant support landed after the tag (`2170869 feat(docx): expand synced
  blocks in standard export`, later merged at `7517b56`)
- `lark-doc-exporter` cannot regress synced-block behavior while moving to the
  new provider

So the first integration should pin `feishu-docx` to a Git commit that already
contains synced-block expansion. The safest first cut is an exact commit pin,
not a floating branch.

## Architecture

### 1. Introduce a Markdown provider boundary

Add a small internal provider layer instead of wiring `feishu-docx` calls
directly into `export_document()`.

That provider boundary should answer:

- which Markdown engine is selected (`feishu-docx` or legacy `lark-cli`)
- whether required credentials are available
- how the provider writes Markdown + local assets
- what metadata should be returned to the CLI / JSON result

This keeps the current exporter readable and prevents the new integration logic
from tangling with native/rendered PDF code paths.

### 2. Preferred path: direct `feishu-docx` export

For Markdown generation, the preferred path becomes:

1. resolve provider = `feishu-docx`
2. resolve credentials from config / environment
3. call `FeishuExporter.export(...)` on the original doc URL
4. adapt the generated Markdown/assets into `lark-doc-exporter`'s expected
   output layout

Important consequence:

- the primary Markdown path should no longer depend on temp-doc creation
- synced-block expansion comes from `feishu-docx`, not from our current XML
  rewrite path

### 3. Compatibility fallback: current legacy Markdown path

Keep the existing `lark-cli` temp-doc Markdown path as a compatibility fallback
when `feishu-docx` cannot be used because credentials/config are missing.

That fallback is still valuable because current users may already have
`lark-cli` configured but no `feishu-docx` credential setup.

However, the fallback must be treated as exactly that:

- not the preferred engine
- not the future semantic core
- clearly surfaced in the result payload so users know which engine ran

The system should **not** silently fall back when `feishu-docx` was selected
and then failed during actual export. Silent fallback is acceptable only for
"provider unavailable because no credentials/config were discoverable" in auto
mode. Real provider execution failures should remain hard failures.

### 4. Credential bridge rules

This is the core design constraint.

`feishu-docx` expects one of:

- `app_id` + `app_secret` (+ auth mode)
- direct access token

`lark-doc-exporter` today assumes:

- a ready `lark-cli` identity
- no app credential surface in its own CLI

The first milestone should keep the `lark-doc-exporter` CLI surface stable and
bridge credentials by **discovery**, not by adding a wide new flag surface.

Credential discovery order for the `feishu-docx` provider:

1. `FEISHU_APP_ID` / `FEISHU_APP_SECRET` / optional `FEISHU_AUTH_MODE`
2. existing `~/.feishu-docx/config.json`
3. otherwise: provider unavailable

Deliberately out of scope for milestone one:

- scraping tokens out of `lark-cli` internal state
- adding first-class `--app-id` / `--app-secret` flags to `lark-doc-exporter`
- trying to make `feishu-docx` consume a `lark-cli` session directly

Those paths either increase maintenance burden or couple us to private
implementation details.

### 5. Provider selection policy

Add an internal selection policy with one external environment override:

- default mode: `auto`
- env override: `LARK_DOC_EXPORTER_MARKDOWN_PROVIDER=auto|feishu-docx|legacy`

Behavior:

- `auto`: use `feishu-docx` when credentials/config are available, otherwise
  fall back to legacy
- `feishu-docx`: require the provider and fail with a clear credential/setup
  message if unavailable
- `legacy`: force the old `lark-cli` Markdown path

This keeps the visible CLI stable while still giving operators a controlled
escape hatch.

### 6. Output-layout compatibility

`feishu-docx` writes Markdown plus a sibling asset directory named after the
file stem. Current `lark-doc-exporter` documentation and tests assume a simpler
`images/` asset output.

The integration should preserve `lark-doc-exporter`'s current outward contract:

- final Markdown path stays `<output-dir>/<stem>.md`
- localized assets stay under `<output-dir>/images/`

So the provider adapter should normalize the `feishu-docx` output layout:

- export into a stage directory first
- move/copy assets into `images/`
- rewrite relative asset links in the final Markdown accordingly

Do not expose `feishu-docx`'s raw asset-folder layout directly in the first
milestone.

### 7. PDF interaction rules

The Markdown-provider change must not destabilize the PDF work that already
landed.

Rules:

- `--pdf-mode native` stays on the current `lark-cli` native-PDF path
- `--pdf-mode rendered` should render from the selected Markdown provider's
  output
- `markdown-only` runs should not create temp docs when `feishu-docx` is used
- `native PDF` runs may still create temp docs even if Markdown came from
  `feishu-docx`

That means the exporter result may legitimately represent a mixed pipeline:

- Markdown provider = `feishu-docx`
- PDF renderer = `feishu-native` or `local-chromium`

### 8. Doctor / documentation / attribution

`doctor` should gain an additional optional check describing whether
`feishu-docx` credentials/config are discoverable for the preferred Markdown
path.

It should not become a hard requirement for the overall doctor result, because:

- native PDF still depends on `lark-cli`
- legacy fallback may still be intentionally used

Documentation updates must do three things:

1. explain that rich Markdown export now prefers `feishu-docx`
2. explain how credentials are discovered (`FEISHU_*` env or
   `~/.feishu-docx/config.json`)
3. add a visible license / attribution note for the integrated MIT project

The repo should carry a small explicit third-party notice instead of hiding this
only in commit history.

## File-Level Design

Planned new / modified boundaries:

- `src/lark_synced_export/exporter.py`
  - stop owning a single hard-coded Markdown path
  - call a provider adapter
  - preserve current PDF-native and rendered-PDF result contract
- `src/lark_synced_export/feishu_docx_bridge.py` (new)
  - optional import wrapper
  - credential discovery
  - provider selection
  - stage export + asset-layout normalization
- `src/lark_synced_export/doctor.py`
  - add optional `feishu-docx` readiness / credential-discovery check
- `src/lark_synced_export/cli.py`
  - keep visible CLI surface stable
  - optionally add a hidden/env-only provider override mention only if needed
- `pyproject.toml`
  - add `feishu-docx` git dependency pin
- `README.md`
  - update requirements, provider behavior, credential setup, attribution
- `THIRD_PARTY_NOTICES.md` (new)
  - record `feishu-docx` MIT attribution and source
- tests
  - add provider-selection and credential-discovery coverage
  - add exporter-path tests for auto/preferred/fallback behavior
  - preserve current native-PDF and skill-install coverage

## Testing Strategy

### Unit tests

- credential discovery:
  - env beats config
  - config works when env is absent
  - missing config marks provider unavailable
- provider selection:
  - `auto` chooses `feishu-docx` when credentials exist
  - `auto` falls back to legacy when credentials do not exist
  - forced `feishu-docx` fails clearly when unavailable
- asset normalization:
  - provider-generated asset paths are rewritten to `images/`

### Exporter integration tests

- `markdown` only + `feishu-docx`
- `markdown,pdf` + rendered PDF using `feishu-docx` markdown
- `markdown,pdf` + native PDF where markdown comes from `feishu-docx` but PDF
  still comes from native exporter
- forced legacy mode regression

### Existing evidence preservation

Do not weaken:

- current `public_doc_e2e` evidence surface
- current async native-PDF export regression coverage
- current doctor / native-PDF / skill-install contracts

## Failure Semantics

If `feishu-docx` is selected in `auto` mode but credentials are missing:

- emit a warning or explicit result field noting fallback to legacy provider
- continue with the current legacy Markdown path

If `feishu-docx` is explicitly forced and unavailable:

- fail clearly with setup guidance

If `feishu-docx` starts exporting and then fails:

- fail the command
- do not silently retry under legacy

That boundary is important because provider runtime bugs should be visible, not
silently masked.

## First-Milestone Success Criteria

This milestone is successful if:

- `lark-doc-exporter` can export Markdown through `feishu-docx` without changing
  its main CLI shape
- users with `feishu-docx` credentials/config automatically get the new
  preferred path
- users without those credentials still have a working legacy fallback
- native PDF behavior stays intact
- the repo carries an explicit MIT attribution notice for `feishu-docx`
- tests pin provider choice, credential discovery, and PDF interaction

## Rejected Alternatives

### Shell out to `feishu-docx` CLI

Rejected because it gives us less control over:

- result JSON shape
- error boundaries
- staging / asset-layout normalization
- long-term test seams

### Depend on released `feishu-docx==0.2.6`

Rejected for milestone one because the release predates synced-block support in
standard export, and that is too important a regression risk.

### Read tokens out of `lark-cli` private state

Rejected because it would couple this integration to private local-auth
implementation details that we do not want to maintain.
