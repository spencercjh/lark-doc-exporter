# lark-doc-exporter PyPI Publish Design

Date: 2026-06-29

## Context

`lark-doc-exporter` is already a real Python package and a real installable
tool, but the public installation path is still centered on source-distribution
commands:

- `uvx --from git+https://github.com/spencercjh/lark-doc-exporter ...`
- `uv tool install git+https://github.com/spencercjh/lark-doc-exporter`

That makes the first-run UX longer than necessary. Spencer approved the target
end-state for this task:

- the primary public install path should be `uv tool install lark-doc-exporter`
- one-off usage should be `uvx lark-doc-exporter ...`
- release credentials should use **PyPI Trusted Publishing**
- release triggering should use **manual version bump + manual `vX.Y.Z` tag**

The repository already has the right core shape for a narrow release task:

- package metadata in `pyproject.toml`
- package version also exposed in `src/lark_synced_export/__init__.py`
- one build entrypoint: `uv build`
- one test/build entrypoint: `make ci`
- an existing normal CI workflow that should remain the ordinary development
  gate

This task is intentionally about **release/distribution plumbing**, not about
changing exporter behavior.

## Assumptions

- The PyPI project name `lark-doc-exporter` is available to this repository, or
  can be created through the Trusted Publishing pending-publisher path.
- If the package name is already owned by an unrelated third party, stop the
  implementation and escalate the naming decision instead of partially
  implementing the workflow.

## Goals

- Make `uv tool install lark-doc-exporter` the primary public installation path.
- Make `uvx lark-doc-exporter ...` the primary one-off execution path.
- Add a dedicated release workflow that publishes to PyPI with GitHub OIDC /
  Trusted Publishing.
- Keep release validation aligned with existing repository commands instead of
  inventing a second CI/build surface.
- Enforce version/tag consistency so a published artifact cannot drift from the
  tagged source.
- Keep release permissions minimal and avoid long-lived PyPI credentials.

## Non-Goals

- Introducing semantic-release, release bots, or automatic changelog
  generation.
- Publishing to TestPyPI.
- Automatically creating GitHub Releases.
- Redesigning the existing ordinary Python CI workflow.
- Changing exporter logic, skill-install logic, or `doctor` behavior.
- Adding npm / `npx` / `bunx` distribution.

## Approaches Considered

### 1. Chosen: manual version bump + manual `v*` tag + tag-triggered PyPI publish

Why choose it:

- matches the current size and maturity of the repository
- reuses `make ci` and `uv build` exactly as they exist today
- adds the shortest path from the current repo to a first-class package-name
  install command
- avoids release automation complexity that is out of scope for this task

### 2. Manual version bump + GitHub Release-triggered publish

Why not choose it:

- adds another user action without improving the core install path
- makes release semantics more complicated than this repo currently needs

### 3. Automatic semantic versioning / changelog / publish

Why not choose it:

- too much process/automation weight for a repo of this size
- expands a narrow distribution task into repository-wide release governance

## Chosen Design

### 1. Release Trigger Model

Publishing must happen only on manually pushed version tags matching `v*`,
specifically the intended `vX.Y.Z` shape.

The PyPI workflow must **not** trigger from:

- `push` to `main`
- `workflow_dispatch`
- GitHub Release publication

This keeps ordinary development CI and official public release clearly
separated.

### 2. Dedicated Publish Workflow

Add a new workflow at:

- `.github/workflows/publish-pypi.yml`

This workflow is dedicated to official PyPI publication and must remain
separate from the ordinary Python CI workflow.

It should be a single-job workflow with a narrow, linear release path:

1. checkout the tagged commit
2. set up Python 3.14
3. set up `uv`
4. run `uv sync --python 3.14 --group dev`
5. verify tag/package version consistency
6. run `make ci`
7. remove any existing `dist/`
8. run `uv build`
9. run a minimal wheel smoke check
10. publish to PyPI using Trusted Publishing

The workflow must reuse existing repository entrypoints:

- validation entrypoint: `make ci`
- build entrypoint: `uv build`

It must not create a second parallel build/test contract.

### 3. PyPI Trusted Publishing

PyPI must be configured to trust:

- the GitHub repository `spencercjh/lark-doc-exporter`
- the publish workflow identity used by `.github/workflows/publish-pypi.yml`

Repository-side publish credentials must use GitHub OIDC instead of a stored
`PYPI_TOKEN`.

Workflow permissions must be minimized to:

- `contents: read`
- `id-token: write`

No additional publish workflow permissions should be granted unless a concrete
implementation need appears during rollout.

### 4. Version and Tag Contract

Versioning remains manual for this repository.

Before a release:

1. update the package version in `pyproject.toml`
2. update `src/lark_synced_export/__init__.py`
3. commit the version bump
4. create and push a matching `vX.Y.Z` tag

The publish workflow must fail if:

- the git tag does not start with `v`
- the tag version does not exactly match the package version

The workflow should treat version mismatch as a hard stop before build/publish.

### 5. README Public Install Path

`README.md` should be reordered around released-package usage.

The first-class user path becomes:

- `uv tool install lark-doc-exporter`
- `lark-doc-exporter doctor`

The one-off path becomes:

- `uvx lark-doc-exporter ...`

GitHub source-install commands should remain available only under explicit
development or unreleased-version guidance, not as the primary Quick Start
path.

### 6. Smoke Check Design

The publish workflow should include a minimal wheel smoke check, but it must be
strictly limited to “the installed console script starts.”

The approved smoke-check command is:

- `lark-doc-exporter --help`

Commands that depend on external runtime prerequisites must not be part of
publish success criteria. In particular:

- `lark-doc-exporter doctor` is **not** allowed in publish smoke validation
  because it requires `lark-cli` and Chromium readiness
- `lark-doc-exporter skill install --dry-run` is **not** the default publish
  smoke check because host auto-detection may fail on a clean runner

### 7. Scope Boundary

This task should touch only the release/distribution surface:

- add `.github/workflows/publish-pypi.yml`
- update `README.md`
- optionally add a very small version-check helper if inline shell validation is
  judged too brittle

This task should not broaden into:

- `.github/workflows/python-ci.yml` redesign
- `Makefile` changes
- exporter behavior changes
- skill-install behavior changes
- npm distribution

### 8. Failure and Recovery Model

The release model should be operationally simple:

- if publish validation fails before upload, fix the issue and publish a new tag
- if Trusted Publishing configuration is wrong, fix the identity/configuration
  and publish a new tag
- if a package is already published and a small issue is found afterward,
  release the next patch version

Deleting published packages is not part of the ordinary rollback model.

## Validation Plan

### Local Validation

Before merging the implementation:

- `make ci`
- `uv build`
- install the produced wheel in an isolated tool environment
- run `lark-doc-exporter --help`
- `git diff --check`

The local isolated install check exists to prove that the released wheel really
supports the intended package-name installation path.

### Publish Workflow Validation

The publish workflow itself must validate:

- tag/package version equality
- ordinary repository checks through `make ci`
- a fresh wheel build from the tagged commit
- a minimal console-script smoke check through `lark-doc-exporter --help`

Only after those checks pass should PyPI upload occur.

## Acceptance Criteria

- Users can install the released tool with `uv tool install lark-doc-exporter`.
- Users can run the released tool one-off with `uvx lark-doc-exporter ...`.
- PyPI publication uses Trusted Publishing instead of a long-lived PyPI token.
- The release workflow only runs on version tags.
- The release workflow fails hard when the git tag and package version differ.
- The release workflow validates a fresh wheel before upload.
- The README’s public path is package-name installation, not Git URL
  installation.
