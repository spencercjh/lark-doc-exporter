# lark-doc-exporter Python CI Design

Date: 2026-06-27

## Context

`lark-doc-exporter` now ships as a Python 3.13, `uv`-first tool with a small
test suite and buildable package artifacts, but it still has no unified CI
surface.

Today the repo has:

- tests runnable through `uv run pytest`
- package builds runnable through `uv build`
- a runtime diagnostic command, `lark-doc-exporter doctor`

What it does **not** have yet:

- a single canonical local CI entrypoint
- a formatting/linting policy
- a GitHub Actions workflow that mirrors local verification closely

Spencer clarified the intended CI boundary:

- CI should be **offline-only**
- CI should include **format** and **lint**
- CI should **not** depend on a Feishu/Lark login state
- CI should prefer a **Makefile** local entrypoint
- GitHub Actions should stay as close as possible to the local workflow

## Goals

- Add a single canonical local CI interface based on `make`.
- Add one GitHub Actions workflow that reuses the same logical steps as local
  CI instead of inventing a separate command surface.
- Standardize formatting and linting for the Python codebase.
- Keep required CI offline-only and deterministic.
- Keep the CI shape simple enough that contributors can run the exact same
  checks locally before pushing.

## Non-Goals

- Running authenticated real-doc export smoke tests in required CI.
- Testing `lark-cli` login state or real Chromium availability as a required
  GitHub check.
- Adding release, publish, or PyPI upload workflows in this task.
- Introducing multiple CI layers (for example separate shell wrappers plus
  Makefile plus workflow-specific command duplication).

## Approaches Considered

### 1. Standalone shell script as the canonical CI entrypoint

Create something like `scripts/ci.sh` and have both local developers and GitHub
Actions call that script.

Why not choose it:

- works technically, but conflicts with Spencer's explicit preference for
  `Makefile`
- still adds an extra indirection layer when `make` is sufficient for this repo

### 2. Chosen: `Makefile` as the single local/CI command surface

Create a small `Makefile` whose targets express the canonical verification
steps:

- `fmt`
- `lint`
- `test`
- `build`
- `ci`

Then make GitHub Actions install the toolchain and call `make ci`.

Why this is the right fit:

- matches Spencer's preference
- keeps the local entrypoint obvious
- keeps workflow logic thin
- minimizes drift between local usage and GitHub

### 3. GitHub Actions with duplicated inline commands, plus optional local docs

Write the workflow directly with `uv run ruff ...`, `uv run pytest ...`, and
`uv build`, while documenting equivalent local commands in README.

Why not choose it:

- produces two sources of truth
- makes future changes easier to forget in one environment
- fails the “尽可能让他们逻辑一样” requirement

## Chosen Design

### 1. Canonical CI Entry Point

The repository will gain a root-level `Makefile` that becomes the only intended
CI command surface.

Targets:

- `make fmt`
- `make lint`
- `make test`
- `make build`
- `make ci`

Behavior:

- `fmt` applies formatting locally
- `lint` is read-only and fails on style or lint violations
- `test` runs the Python test suite
- `build` verifies sdist/wheel creation
- `ci` runs the required offline verification chain in order

This means both humans and GitHub Actions invoke the same target names, instead
of memorizing raw `uv` command sequences.

### 2. Formatting and Linting Policy

The repo will standardize on `ruff` for both formatting and linting.

Formatting:

- `uv run ruff format .`

Linting:

- `uv run ruff format --check .`
- `uv run ruff check .`

Why `ruff`:

- one tool instead of Black + isort + flake8 layering
- fast enough to keep local CI cheap
- appropriate for a small Python 3.13 codebase

The `pyproject.toml` file will be updated so the `dev` dependency group includes
`ruff`, and any minimal repo-specific `tool.ruff` configuration will live there
too.

### 3. Required CI Scope

Required CI remains offline-only.

Included in required CI:

- formatting check
- lint check
- unit tests
- package build

Excluded from required CI:

- `lark-doc-exporter doctor`
- any command that requires a real `lark-cli` session
- any command that depends on a real browser runtime or Playwright install state
- real export smoke tests against Feishu/Lark docs

This boundary matters because task `#3` is about stable required CI, not about
end-to-end environment integration.

### 4. GitHub Actions Workflow Shape

The repo will gain a single workflow, for example:

- `.github/workflows/python-ci.yml`

Workflow responsibilities:

1. check out the repo
2. install `uv`
3. provision Python `3.13`
4. run `uv sync --python 3.13 --group dev`
5. run `make ci`

Important constraint:

- the workflow should **not** restate raw lint/test/build commands if that can
  be avoided
- the workflow should call `make ci` so command drift stays concentrated in one
  place

The workflow may still need setup-only steps that do not exist locally, such as
installing `uv` and selecting Python `3.13`. That setup asymmetry is acceptable
because the actual verification logic still flows through `make`.

### 5. README and Contributor Flow

The README development section will be extended so local contributors see the
same CI surface GitHub uses.

Expected developer flow:

1. `uv sync --python 3.13 --group dev`
2. `make fmt` while editing
3. `make ci` before push

This keeps the local story simple and makes the GitHub workflow unsurprising.

## File-Level Impact

Expected repo changes in implementation:

- create `Makefile`
- create `.github/workflows/python-ci.yml`
- modify `pyproject.toml`
- modify `README.md`

No application runtime files should need behavior changes for this task unless
linting exposes an actual code issue.

## Validation Plan

The implementation is only acceptable if all of the following are true:

- `uv sync --python 3.13 --group dev` installs a working dev environment
- `make fmt` succeeds locally
- `make lint` succeeds locally
- `make test` succeeds locally
- `make build` succeeds locally
- `make ci` succeeds locally
- the GitHub Actions workflow runs the same logical chain and goes green on the
  branch

For this task, “local and GitHub logic are close enough” means:

- both use Python `3.13`
- both use `uv` for environment setup
- both use the same `make` targets for actual checks
- GitHub-specific setup steps are limited to environment bootstrap, not custom
  duplicated verification logic

## Future Follow-Up (Explicitly Deferred)

If authenticated smoke testing becomes desirable later, it should be added as a
separate optional workflow or manual dispatch path, not folded into required
offline CI.
