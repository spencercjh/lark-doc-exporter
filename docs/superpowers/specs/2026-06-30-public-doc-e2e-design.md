# lark-doc-exporter Public Document E2E Design

Date: 2026-06-30

## Context

`lark-doc-exporter` now has strong unit and integration coverage around:

- synced-block expansion
- callout normalization and rendering
- CLI argument contracts
- native PDF footer post-processing
- release/version checks

What it still does **not** have is one true end-to-end lane that:

1. exports a real Feishu/Lark document,
2. inspects the produced markdown and final PDF,
3. verifies a few canonical feature points with precise expectations, and
4. can later run in CI once a stable public test document exists.

The current internal regression samples are useful for manual release checks,
but they are not suitable as long-lived repository fixtures. The new scope is
therefore intentionally narrow:

> add one lightweight public-doc E2E framework that is ready for CI now, but
> explicitly skips until a stable public document reference is provided.

The public document is expected to change rarely, but the test intent is still
feature-oriented rather than “diff every byte of every artifact.”

## Assumptions

- v1 covers exactly one canonical public document fixture.
- The future public document is stable enough that snapshot maintenance remains
  rare and deliberate.
- The most important regressions are feature-specific:
  synced blocks, callouts, whiteboards, image localization, native-PDF cleanup,
  and similar exported behaviors.
- This test lane depends on real external export behavior and therefore must
  remain outside the default offline CI/test surface.

## Goals

- Add a single, easy-to-read E2E test entry for one public document.
- Keep the framework pure Python and repo-native.
- Make the CI wiring visible now, even before the public document exists.
- Validate a small set of canonical feature points with precise snapshots.
- Keep failure messages tied to feature names so regressions are easy to triage.

## Non-Goals

- Building a generic multi-document E2E platform.
- Introducing a TOML/YAML manifest layer or custom DSL.
- Diffing whole raw PDF binaries.
- Making this online E2E lane part of default `make ci` / default `pytest -q`.
- Adding snapshot auto-refresh tooling in v1.

## Approaches Considered

### 1. Chosen: one public document + feature-point snapshots

Why choose it:

- keeps the framework extremely small
- preserves precise regression signals where they matter
- avoids whole-artifact diff noise
- matches the real requirement: validate several key exported features, not
  maintain a generalized test platform

### 2. Whole-artifact snapshots

Why not choose it:

- whole markdown / whole extracted PDF text diffs are larger and harder to
  triage
- regressions become less obviously tied to the feature that broke
- more maintenance overhead with little additional value for v1

### 3. Assertion-only feature checks without snapshots

Why not choose it:

- too close to a rule-only test style
- weaker signal for subtle content drift within a feature
- does not match the explicit preference for precise snapshots

## Chosen Design

### 1. Repository Layout and Asset Model

Do **not** add a new test framework or manifest subsystem. Keep the lane as one
thin pytest test plus one small Python config module.

Recommended structure:

- `tests/test_public_doc_e2e.py`
  - the single test entrypoint
  - reads the case config
  - runs the export
  - performs global checks and feature-point checks
- `tests/public_doc_e2e_case.py`
  - static Python configuration for this one public-doc fixture
  - stores the future doc ref, fixed export args, stable JSON expectations, and
    feature-point definitions
- `tests/e2e_snapshots/public_doc/`
  - checked-in golden artifacts for this fixture
  - `result.json`
  - `markdown/<feature>.md`
  - `pdf_text/<feature>.txt`

v1 intentionally does **not** introduce:

- `manifest.toml`
- `conftest.py`
- a reusable matrix runner
- multiple fixture documents

This is not a “testing platform.” It is one fixed public-doc lane with one
fixed configuration file and one readable set of snapshots.

### 2. Python Config Contract and Matching Model

`tests/public_doc_e2e_case.py` should contain a very small, static data model.
It can be plain module-level constants or a tiny typed structure, but it should
stay simple enough to understand without learning a framework.

The configuration should include:

- `DOC_REF`
  - future public document ref
  - `None` until Spencer provides the canonical doc
- `EXPORT_ARGS`
  - v1 should lock the E2E route to:
    - `formats=["markdown", "pdf"]`
    - `pdf_mode="native"`
- `EXPECTED_RESULT`
  - stable CLI result fields to compare exactly
- `FEATURE_POINTS`
  - one list entry per canonical feature under test

Each feature-point entry should stay deliberately “low-tech.” Support only:

- `name`
  - stable slug such as `synced_block`, `callout`, `whiteboard`,
    `image_link_localized`
- `markdown_contains_snapshot`
  - snapshot file containing the markdown fragment that must appear
- `pdf_text_contains_snapshot`
  - snapshot file containing the extracted-PDF text fragment that must appear
- `markdown_forbid`
  - raw strings that must not appear in final markdown
- `pdf_forbid`
  - raw strings that must not appear in extracted final PDF text

Do **not** create a matcher DSL or abstract predicate system.

The comparison rules are:

#### 2.1 Stable CLI result snapshot

Do not snapshot the full CLI JSON payload. Instead, extract and compare only
stable, user-meaningful fields such as:

- `ok`
- `pdf_mode`
- `ai_footer_postprocess.status`

Do not snapshot:

- absolute output paths
- temp paths
- other incidental runtime-specific fields

#### 2.2 Markdown feature snapshots

Do not diff the entire markdown artifact. Instead:

- load the final markdown output
- for each feature point, verify that the corresponding snapshot fragment is
  present exactly as expected

This keeps the regression signal precise while limiting noise.

#### 2.3 PDF feature snapshots

Do not snapshot raw PDF bytes. Instead:

- read the final PDF
- extract text
- apply only light normalization
- verify that each feature snapshot fragment is present

Allowed normalization should stay conservative:

- normalize line endings
- collapse repeated whitespace
- trim obvious extraction-edge spacing noise

Do not apply heavier semantic cleanup that could hide a real regression.

#### 2.4 Forbidden-marker checks

Each feature point may also define forbidden residue markers. This is how v1
should catch “export succeeded but leaked raw placeholders” failures.

Examples:

- markdown forbid:
  - `<synced_reference`
  - `<callout`
  - `authcode/?code=`
- PDF forbid:
  - AI footer text
  - unsupported placeholder strings

### 3. Execution Flow, Skip Contract, and CI Wiring

The E2E execution flow should be fixed and easy to trace:

1. load `tests/public_doc_e2e_case.py`
2. if `DOC_REF is None`, immediately `pytest.skip("public doc fixture not configured")`
3. otherwise run one real export using the fixed v1 export arguments
4. validate the stable CLI result fields
5. read final markdown and extracted final PDF text
6. run feature-point `contains` and `forbid` checks
7. fail immediately on the first mismatch, with the feature name in the error

The runtime boundary is important:

#### 3.1 Separate from the default offline test surface

This lane must **not** run as part of normal repository offline testing.

Recommended shape:

- give the test an explicit marker such as `@pytest.mark.e2e_public_doc`
- run it only when a dedicated job or explicit local pytest invocation targets
  it

Reason:

- it depends on a real Feishu/Lark document and live export behavior
- it should not make the default test surface flaky or online-dependent

#### 3.2 Visible skip before the public doc exists

The CI job should be added now, even before the fixture is configured.

Before `DOC_REF` is set:

- the job still runs
- the test entry still executes
- the result is explicitly `skipped`

This avoids a second future plumbing step. Once the public document ref is
filled in, the same job naturally becomes a real E2E execution path.

#### 3.3 Feature-oriented failure reporting

Failures should be reported from the feature-point perspective, not as one large
undifferentiated diff.

Examples:

- `feature synced_block: markdown snapshot missing`
- `feature whiteboard: forbidden marker '<whiteboard' still present in markdown`
- `feature ai_footer: forbidden marker found in extracted pdf text`

This keeps the lane maintainable for future triage.

#### 3.4 No snapshot refresh tool in v1

v1 should not include an automatic snapshot update command.

Reason:

- the lane covers only one document and a small number of canonical features
- automatic refresh makes it too easy to overwrite the baseline without real
  review
- manual snapshot maintenance is still cheap at this scale

If refresh tooling is ever added, it should come only after the public fixture
has proven stable in actual use.

## Validation Plan

When this design is implemented, validation should include:

- normal repository baseline:
  - `make ci`
- focused local execution of the new test entry while `DOC_REF` is unset:
  - verify explicit `skip`
- focused local execution with a configured public-doc fixture once Spencer
  provides one:
  - verify stable result snapshot matching
  - verify markdown feature snapshots
  - verify PDF text feature snapshots
  - verify forbidden-marker checks
- explicit CI-job verification:
  - job exists before the fixture is configured
  - job is visibly `skipped` while `DOC_REF` is unset

## Scope Boundary

This design intentionally stops at a narrow v1:

- one public document
- one pytest entrypoint
- one Python case file
- one checked-in snapshot set
- one dedicated CI job

It should not expand during implementation into:

- a generic matrix runner
- multiple documents
- automatic snapshot refresh tooling
- online E2E folded into default `make ci`
- a standalone manifest or plugin framework
