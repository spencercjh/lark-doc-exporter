# lark-doc-exporter Kitup Skill Install Migration Design

Date: 2026-07-02

## Context

`lark-doc-exporter` already ships a bundled companion skill and exposes
`lark-doc-exporter skill install`, but the current implementation in
`src/lark_synced_export/skill_install.py` is a tool-local installer with its own:

- host detection rules
- overwrite semantics
- metadata file (`.lark-doc-exporter-install.json`)
- rollback / replace logic

At the same time, `kitup` now has a Python SDK on branch `alice/python-sdk`
that standardizes:

- bundle validation
- host-aware target resolution
- install / update / conflict behavior
- `.kitup.json` ownership metadata
- dry-run planning

Spencer wants a `lark-doc-exporter` PR that proves the Python `kitup` branch is
usable in a real client, even before `kitup` is merged/released. That means this
PR can temporarily depend on an unreleased git ref as long as the integration is
real and validated.

## Goals

- Replace `lark-doc-exporter`'s local skill installer with a `kitup`-backed
  implementation.
- Keep the existing CLI surface stable:
  - `lark-doc-exporter skill install`
  - `--host auto|codex|claude|all`
  - `--force`
  - `--dry-run`
- Keep the bundled skill assets local to the `lark-doc-exporter` package.
- Preserve the current supported host scope for this tool:
  - Codex
  - Claude Code
- Prove the integration is actually usable by validating it in this repo.

## Non-Goals

- Converting `lark-doc-exporter` to the full interactive `kitup` workflow UX.
- Expanding this CLI to `scope=user|project`.
- Adding new lifecycle commands such as `skill uninstall`.
- Waiting for a published `kitup` release before opening the PR.
- Preserving the old `.lark-doc-exporter-install.json` format.

## Approaches Considered

### 1. Chosen: adapter around `kitup` install APIs, preserve current CLI

Use `kitup`'s Python install primitives under the existing
`lark-doc-exporter skill install` command, while keeping the current flags and a
small JSON result shape.

Why choose it:

- proves the `kitup` Python SDK works in a real embedding CLI
- minimizes user-visible CLI churn
- removes the most duplicated installer code without forcing workflow prompts
- keeps migration scope reviewable in one draft PR

### 2. Switch CLI directly to raw `kitup` workflow semantics

Expose the `kitup` workflow more literally, including its report/exit model.

Why not choose it:

- larger user-visible surface change
- forces unrelated CLI behavior changes into the same draft PR
- makes it harder to compare current vs migrated `lark-doc-exporter` behavior

### 3. Keep current installer and only borrow internal helper pieces

Reuse small `kitup` pieces but preserve most local install logic.

Why not choose it:

- does not really prove `kitup` #13 is sufficient
- leaves most of the duplicate installer implementation in place
- weakens the demonstration value of the migration PR

## Chosen Design

### 1. Temporary dependency strategy

This PR will temporarily depend on the unreleased Python `kitup` package via a
direct git reference to Spencer's fork / exact commit from `kitup` PR #13.

That keeps the integration honest:

- `lark-doc-exporter` imports the real package, not a copied local module
- reviewers can verify the actual embedding code path
- the dependency can be swapped to a released version later once `kitup` lands

### 2. Host model for this tool

`lark-doc-exporter` should continue to target only:

- `codex`
- `claude-code`

The public CLI flag remains:

- `--host auto|codex|claude|all`

Internally:

- `claude` maps to `claude-code`
- `all` maps to both host ids
- `auto` remains conservative and only works from the host roots this tool
  already treats as supported

To keep that behavior stable, the adapter should use a small
`lark-doc-exporter`-owned host spec file instead of the full default host matrix
from `kitup`.

### 3. Bundled skill source

The source skill payload remains the bundled package asset at:

- `src/lark_synced_export/skill_assets/lark-doc-exporter/SKILL.md`

The adapter should use `importlib.resources.as_file(...)` to obtain a real
filesystem path and then pass that directory to `kitup.directory_bundle(...)`.

This keeps the packaging boundary unchanged: `lark-doc-exporter` still owns the
skill contents; `kitup` owns install semantics.

### 4. Installer execution path

The new `run_skill_install(...)` path should:

1. resolve the bundled skill directory
2. build `kitup.InstallOptions` with:
   - `app_id="lark-doc-exporter"`
   - `scope="user"`
   - mapped host selector
   - `force` from CLI
3. call `kitup.plan_bundled_skill(...)`
4. if `dry_run`, return a normalized preview payload
5. otherwise call `kitup.install_bundled_skill(...)`
6. return a normalized result payload

This PR should not use `run_bundled_skill_install(...)` because the current CLI
does not expose interactive scope/agent prompts and does not need them.

### 5. Metadata and ownership

Installed targets will now be owned through `kitup`'s `.kitup.json` metadata
instead of `.lark-doc-exporter-install.json`.

Consequences:

- existing tests that assert the local metadata file must be updated
- managed upgrade detection should now be delegated to `kitup`
- old tool-local metadata is no longer part of the steady-state contract

For this draft PR, migration of already-installed old metadata is not required.
An old install without `.kitup.json` is treated as unmanaged and requires
`--force`, which is acceptable for the first migration step.

### 6. Result shape

The CLI should keep printing JSON, but the payload may now be adapter-defined
instead of mirroring the old local installer structs exactly.

The adapter result should stay simple:

- `ok`
- `dry_run`
- `targets`

Each target entry should still identify:

- host
- target directory
- action

The exact action labels should be derived from `kitup` plan/report semantics
(`install`, `update`, `overwrite`, `skip`, or conflict-derived errors) rather
than reproducing the old implementation byte-for-byte.

### 7. Validation

The PR must prove the integration is usable.

Required validation:

- `tests/test_skill_install.py`
- `tests/test_cli.py`
- any packaging/config tests affected by the new dependency
- a real dry-run / install path in tests using temp homes

Known baseline nuance:

- full repo `pytest` currently has one pre-existing failure in
  `tests/test_public_doc_e2e.py::test_public_doc_export_e2e` when `lark-cli`
  user auth needs refresh

That auth-dependent e2e failure should be reported as baseline noise, not
treated as caused by the migration.
