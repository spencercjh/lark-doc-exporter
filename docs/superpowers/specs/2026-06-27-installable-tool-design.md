# lark-doc-exporter Installable Tool Design

Date: 2026-06-27

## Context

`lark-doc-exporter` is already a public repository, but it is not yet a real
installable end-user tool. The current runtime still reaches outside the Python
package to repo-relative assets:

- `scripts/render_html_to_pdf.mjs`
- `node_modules/.bin/marked`

That means the current CLI works only inside a checked-out repository after a
local `npm install`. It does not yet satisfy the distribution target Spencer
approved for v1:

- `uvx lark-doc-exporter ...` should be a valid mental model
- `uv tool install ...` should work without a repo checkout
- the package should be publishable to PyPI later
- functionality must not regress

The approved v1 boundary is intentionally narrower than a fully self-contained
desktop-style bundle:

- end users should get a real installable Python tool
- end users should not need the repo checkout
- Chromium/browser availability may still remain an external prerequisite
- no functionality breakage is acceptable

## Goals

- Make the CLI runnable from an installed Python package without depending on
  repo-root files.
- Keep the existing CLI surface and export behavior stable unless a change is
  required for installation correctness.
- Preserve the current Chromium-based PDF route to minimize render drift.
- Keep the built-in `default` and `company` themes.
- Make README usage install-first for end users, while preserving a separate
  repo-local developer flow.
- Add an explicit runtime diagnostic path so users can tell whether they are
  missing `lark-cli` or a browser runtime instead of failing with vague errors.
- Add one installation-style validation that runs outside the repo checkout.

## Non-Goals

- Publishing to PyPI in this task.
- Hiding all runtime prerequisites from users.
- Redesigning themes, output layout, or the temp-doc/Lark export workflow.
- Bundling a private Node/npm runtime into the Python distribution.

## Approaches Considered

### 1. Hide the current Node-based runtime inside the package

Keep `marked + Playwright(Node)` and package enough surrounding machinery so the
user does not notice Node/npm.

Why not choose it:

- keeps the current architecture, but creates the most packaging complexity
- makes wheel/sdist behavior harder to reason about
- buys little for a v1 whose goal is just “really installable”

### 2. Switch the entire PDF route to a non-browser Python PDF engine

Make the whole pipeline “pure Python” all the way to PDF.

Why not choose it:

- highest risk of visual/output regression
- would change the rendering path more than necessary
- increases the chance that “installable” is achieved by trading away output
  fidelity

### 3. Chosen: Python-only package runtime, keep Chromium PDF output

Move the runtime logic that is currently repo-relative into the Python package
itself:

- markdown-to-HTML moves to Python
- PDF rendering moves to Python
- Chromium remains the output engine
- browser availability remains an explicit external prerequisite for v1

This is the smallest path that makes the tool truly installable while keeping
the current rendering strategy intact.

## Chosen Design

### 1. Package Boundary

The installed package must contain everything it needs except its external
runtime prerequisites:

- Python code
- built-in CSS themes
- any HTML/template helpers needed at runtime

The installed package must not depend on:

- repo-root `scripts/`
- repo-root `node_modules/`
- current working directory matching the repo layout

All runtime path resolution should become package-relative rather than
repository-relative.

### 2. Markdown Rendering

The current `marked` CLI dependency will be replaced with a Python-side markdown
renderer that lives inside the package runtime.

Design intent:

- generate an HTML body fragment suitable for the existing theme/CSS pipeline
- preserve the current export path structure: expanded markdown remains the
  intermediate source of truth for PDF generation
- avoid introducing a second markdown dialect or a new user-visible document
  model

This keeps the export pipeline understandable:

1. fetch/expand Lark content
2. export localized markdown
3. render markdown to HTML in Python
4. render HTML to PDF via Chromium

### 3. PDF Rendering

The repo-local Node helper will be replaced by Python-side browser rendering
logic inside the package.

Constraints:

- keep Chromium-based PDF generation
- keep the current PDF options and layout intent (`A4`, print background,
  prefer CSS page size)
- keep theme application in the same conceptual place: HTML + CSS -> PDF

This deliberately preserves the current output strategy instead of changing the
document engine.

### 4. Runtime Diagnostics

The CLI will gain a small runtime diagnostic path, exposed as a `doctor`
subcommand.

`doctor` should check the external prerequisites that can still break the tool:

- `lark-cli`
- browser/Chromium readiness for the PDF path

The command should print actionable next steps instead of generic stack traces.
The point is not to create a large admin surface; it is to make the installed
tool self-diagnosing enough that end users know what is missing.

### 5. User Experience

The main README path should become installation-oriented:

1. install the tool
2. run `lark-doc-exporter doctor`
3. prepare any missing external prerequisite if needed
4. run `lark-doc-exporter ...`

The developer path should remain separate and explicit:

- clone repo
- `uv sync --group dev`
- run tests / local development commands

This keeps end-user instructions short while preserving contributor ergonomics.

## Validation Plan

The “功能不能出问题” requirement is a first-class acceptance criterion.

v1 is only acceptable if all of the following remain true:

- existing focused tests still pass
- theme resolution still works
- the real-doc smoke export still succeeds
- the installed package can be exercised outside the repo checkout

The new validation added for this design should explicitly prove the packaging
boundary:

- build/install the tool into an isolated environment
- run `lark-doc-exporter --help`
- run `lark-doc-exporter doctor`
- run at least one real export path without relying on repo-root assets

The goal is not “the README changed”; the goal is “the installed tool actually
works when the repo is absent”.
