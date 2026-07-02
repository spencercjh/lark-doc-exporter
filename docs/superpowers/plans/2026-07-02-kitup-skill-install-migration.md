# Kitup Skill Install Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `lark-doc-exporter`'s local companion-skill installer with a `kitup`-backed adapter while keeping the current CLI entrypoint and proving the integration works in a draft PR.

**Architecture:** Keep `lark-doc-exporter` as the owner of bundled skill assets and CLI flags, but delegate install planning/execution to `kitup` through a thin adapter. Use a `lark-doc-exporter`-specific host spec to preserve the current supported host set and conservative auto-detection semantics.

**Tech Stack:** Python 3.14, uv, pytest, setuptools package data, direct git dependency on `kitup`

---

### Task 1: Pin `kitup` and package the migration inputs

**Files:**
- Modify: `pyproject.toml`
- Create: `src/lark_synced_export/kitup_hosts.json`
- Test: `tests/test_skill_install.py`

- [x] Add a temporary direct dependency on the Python `kitup` package from Spencer's fork / exact commit used for validation.
- [x] Add a tiny host spec JSON file containing only `codex` and `claude-code`, with host roots chosen to preserve the current `lark-doc-exporter` behavior.
- [x] Run `uv sync` to verify the dependency resolves in this repo.

### Task 2: Replace the local installer implementation with a `kitup` adapter

**Files:**
- Modify: `src/lark_synced_export/skill_install.py`
- Modify: `src/lark_synced_export/cli.py` (only if argument/help text needs small alignment)
- Test: `tests/test_skill_install.py`

- [x] Remove the duplicated local copy/install/rollback implementation that `kitup` now owns.
- [x] Build adapter helpers that:
  - map `--host auto|codex|claude|all` to `kitup` selectors
  - load bundled skill assets through `importlib.resources.as_file`
  - call `kitup.plan_bundled_skill(...)` / `kitup.install_bundled_skill(...)`
  - normalize `kitup` reports into a stable JSON result payload
- [x] Keep non-interactive CLI behavior: `skill install` should remain a direct command, not a prompt-driven workflow.

### Task 3: Update tests to the new ownership and result contract

**Files:**
- Modify: `tests/test_skill_install.py`
- Modify: `tests/test_cli.py` if JSON surface assertions need refresh

- [x] Update metadata assertions from `.lark-doc-exporter-install.json` to `.kitup.json`.
- [x] Update force/overwrite expectations to match `kitup` conflict semantics.
- [x] Preserve coverage for:
  - auto detection
  - explicit host install
  - force overwrite of unmanaged targets
  - dry-run
  - CLI JSON output
  - legacy managed-install migration to `.kitup.json`
- [x] Remove tests that only exercise deleted local rollback internals, or replace them with equivalent adapter-level behavior tests if still meaningful.

### Task 4: Document the draft dependency and migration behavior

**Files:**
- Modify: `README.md`
- Modify: `src/lark_synced_export/skill_assets/lark-doc-exporter/SKILL.md` only if command wording or expectations changed materially

- [x] Document that this draft PR temporarily uses `kitup` underneath `skill install`.
- [x] Keep end-user CLI examples stable unless the JSON/behavior change forces wording updates.
- [x] Update the migration note after the legacy metadata bridge landed: old managed installs should upgrade without requiring `--force`.

### Task 5: Validate and prepare the PR

**Files:**
- Modify: draft PR body / review summary (not a repo file)

- [x] Run targeted tests for the migrated installer surface.
- [x] Run the largest practical repo validation set and record the result.
- [x] Commit the branch changes with signed conventional commits.
- [ ] Push the branch and update the draft PR against `lark-doc-exporter`.
- [ ] In the PR/thread summary, call out:
  - temporary dependency on `kitup` PR #13 commit
  - what behavior was intentionally preserved
  - what metadata / migration behavior changed
