# lark-doc-exporter Native PDF AI Footer Removal Design

Date: 2026-06-30

## Context

`lark-doc-exporter` already has a strong temp-doc front half:

- fetch source XML
- expand synced blocks
- normalize XML
- create a temporary Feishu doc

That temp-doc step is already enough to avoid the official/native synced-block
PDF failure on the `WEgB...` sample. However, it does **not** reliably remove
the AI footer notice from service-side native PDF export. The counterexample
`BVXXwgzbZivjQZkr7jmcsGcinGh` proves that:

- the raw original doc does not contain the AI footer sentence in its XML
- the normalized temp-doc XML also does not contain it
- the created temp doc still exports to a native PDF that contains the footer

So the current requirement is narrower and explicit:

> keep Feishu native PDF output, and post-process only the AI footer notice on
> the last page.

This task is therefore about adding a **native-PDF mode with a narrow,
safety-first footer post-processor**, not about changing the existing rendered
PDF path.

## Assumptions

- The AI footer notice remains a last-page footer phenomenon for the v1 scope.
- A candidate PDF library or adapter used during implementation must provide
  word/span-level or equivalent fine-grained text geometry. A backend that only
  exposes coarse paragraph/block rectangles does not satisfy this design.
- The current rendered PDF path remains the default and must continue to work
  exactly as it does today unless the user explicitly selects native mode.

## Goals

- Add an explicit native PDF mode without changing the default rendered mode.
- Keep markdown export behavior unchanged.
- Remove the AI footer notice from native PDF only when the footer is detected
  and geometrically safe to mask.
- Fail loudly, with warnings, when native footer removal cannot be completed
  safely.
- Keep CI coverage mostly offline and deterministic.

## Non-Goals

- Replacing the default rendered PDF path.
- Adding a generic PDF text cleanup subsystem.
- Editing PDF content streams directly.
- Cropping or masking a full bottom strip as the primary strategy.
- Running real Feishu export smoke tests inside default `make ci`.
- Changing theme behavior for the rendered pipeline.

## Approaches Considered

### 1. Chosen: last-page footer detection + narrow bbox mask

Why choose it:

- preserves Feishu native PDF output
- limits edits to one small region on the last page
- gives the clearest safety boundary against正文误伤
- matches the explicit user requirement: fix the footer, not the whole PDF path

### 2. Fixed bottom-band crop or mask

Why not choose it:

- too easy to damage legitimate last-page正文
- the edit region is much larger than the actual problem
- degrades into a blunt layout hack instead of a targeted fix

### 3. Direct PDF content-stream surgery

Why not choose it:

- highest implementation and maintenance risk
- too brittle against font encoding and text-object fragmentation
- unnecessary for a narrow last-page footer problem

## Chosen Design

### 1. Command Surface

Add one new CLI flag:

- `--pdf-mode rendered|native`

Default remains:

- `rendered`

Behavior contract:

- `rendered`: keep the existing pipeline unchanged
  - `doc -> temp doc -> markdown -> local HTML/Chromium -> PDF`
- `native`: use the native PDF path
  - `doc -> temp doc -> native PDF export -> AI footer post-process`

The new mode affects only PDF:

- `--formats markdown`: ignore `--pdf-mode`
- `--formats pdf --pdf-mode native`: produce native PDF with footer handling
- `--formats markdown,pdf --pdf-mode native`:
  - markdown still uses the current markdown pipeline
  - PDF uses the native PDF branch

v1 does **not** add a second explicit footer-removal toggle. Selecting
`--pdf-mode native` implies “attempt AI footer removal.”

Theme/CSS contract:

- `--pdf-mode rendered`: current `--theme` / `--css` behavior stays unchanged
- `--pdf-mode native`:
  - default values may pass through silently
  - explicitly passing a non-default `--theme` or `--css` must raise a CLI
    error instead of being silently ignored

JSON contract:

- native PDF runs must report `pdf_mode`
- native PDF runs must report an `ai_footer_postprocess` object
- that object must at least carry:
  - `status`
  - `warning` or `warnings[]` on failure
  - the preserved raw-native artifact path when failure occurs

### 2. Detection Rules

Detection is intentionally narrow and conservative.

Only inspect:

- the **last page**

Detection is two-stage:

1. extract and normalize last-page text
2. only if that text hits the small footer whitelist, continue to geometry

Normalization requirements:

- Unicode `NFKC`
- strip control characters
- collapse excess whitespace and line breaks
- normalize punctuation differences
- normalize spacing differences around `AI生成`

Canonical footer variants for v1 must stay short and explicit, such as:

- `注:内容由AI生成,请谨慎参考`
- `(注:内容由AI生成,请谨慎参考)`
- `内容由AI生成,请谨慎参考`

Detection must **not** use a broad fuzzy pattern like “any sentence containing
AI / 生成 / 谨慎参考.” If the canonical whitelist is not hit, the result is
`not_found` and the PDF must remain unchanged.

### 3. Geometry and Mask Safety Contract

If text matching succeeds, masking is only allowed when the matched footer
looks like a real last-page footer cluster.

Mask target:

- the **smallest matched footer text cluster**
- not the whole bottom strip
- not an arbitrary large page region

Cluster rules:

- merge only nearby same-line spans/fragments
- if matched pieces split into multiple clearly separate clusters, stop and
  treat the result as unsafe

Footer-zone requirement:

- the candidate cluster must lie within the bottom `20%` of the last page

Footer-shape guardrails:

- height must remain single-line-like:
  - `height <= max(36pt, 5% page height)`
- width must not look like a full正文 paragraph:
  - `width <= 80% page width`

Mask rectangle:

- `union_bbox(cluster)` plus only tiny padding
- x padding: about `4-6pt`
- y padding: about `2-4pt`

Safety stop conditions:

- expanded mask overlaps any non-footer text bbox
- only coarse paragraph/block geometry is available
- matched fragments do not form one clear footer cluster
- candidate cluster is outside the footer zone
- candidate cluster is multi-line / paragraph-like

Any of those conditions must stop masking and surface `unsafe_geometry`.

### 4. Failure Model and Warning Contract

Native mode is not allowed to silently fall back to rendered PDF.

Success states:

- `removed`
  - footer detected
  - geometry safe
  - mask applied
  - post-mask verification confirms footer gone
- `not_found`
  - canonical footer not detected on the last page
  - no modification applied

Both success states must:

- exit `0`
- produce final `<stem>.pdf`

Failure states:

- `detection_failed`
- `unsafe_geometry`
- `mask_failed`

All failure states must:

- exit `1`
- emit an explicit warning in stderr
- include the same warning in JSON output
- include both the failure reason and the preserved raw-native PDF path in that
  warning

Artifact contract:

- export raw native PDF first
- only publish final `<stem>.pdf` on success
- on failure, preserve the raw artifact as `<stem>.native-raw.pdf`
- do **not** also publish a misleading success-looking `<stem>.pdf`

Combined-format contract:

- if `--formats markdown,pdf --pdf-mode native` writes markdown successfully but
  PDF post-processing fails, the overall command still fails
- markdown may remain on disk
- raw native PDF debug artifact may remain on disk
- JSON must report the PDF-side failure clearly

Exit-code contract stays simple:

- `0` = success
- `1` = failure

Detailed reason belongs in stderr and JSON status, not in a larger exit-code
taxonomy.

### 5. Testing Strategy

The test surface should be split into three automated layers and one manual
acceptance layer.

#### 5.1 Pure rule unit tests

These do not need real PDFs. They should lock:

- footer text normalization
- whitelist match vs non-match behavior
- bottom-20%-zone gating
- split-cluster rejection
- overlap rejection

The text-match and geometry-check logic should be factored into pure functions
so most rule coverage stays in ordinary pytest.

#### 5.2 Post-process integration tests

These should exercise the native-PDF footer-removal state machine with stubbed
or monkeypatched PDF backends.

They must lock:

- `removed` success behavior
- `not_found` success behavior
- `detection_failed` / `unsafe_geometry` / `mask_failed` failure behavior
- warning emission on failure
- artifact naming and publish semantics
- JSON result structure
- `markdown,pdf` partial-failure behavior

#### 5.3 CLI regression tests

These should lock the user-visible interface:

- default remains `--pdf-mode rendered`
- `--pdf-mode native` only changes the PDF branch
- markdown branch remains unchanged under combined-format requests
- explicit non-default `--theme` / `--css` under native mode is rejected
- JSON includes native-mode and footer-postprocess status fields
- JSON includes warning fields on failure

#### 5.4 Manual smoke tests

Real Feishu export checks must stay out of default `make ci`.

Keep a small manual acceptance set:

- positive AI-footer sample:
  - `BVXXwgzbZivjQZkr7jmcsGcinGh`
  - expected: `removed`
- no-footer sample:
  - `CBecwNJO7ieT1BkNIXeclJyCnPh`
  - expected: `not_found`
- anti-footgun sample:
  - last-page正文 close to the footer zone
  - expected: `unsafe_geometry` + warning

If a real anti-footgun sample is not yet available, v1 may start with a
synthetic PDF fixture for that acceptance case and replace it later with a real
document sample.

## Validation Plan

Before publish/review of the implementation branch, validation should include:

- focused pytest coverage for the new pure rule layer
- focused pytest coverage for post-process integration behavior
- CLI regression tests for `--pdf-mode native`
- normal repository gate:
  - `make ci`
- manual smoke verification for the approved acceptance set outside default CI

## Scope Boundary

This design intentionally fixes only the native-PDF AI footer problem.

It should not expand into:

- rendered-pipeline redesign
- broader PDF cleanup features
- generalized document-layout rewriting
- mandatory online test execution in ordinary CI
