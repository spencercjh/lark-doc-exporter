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

- [ ] Add a temporary direct dependency on the Python `kitup` package from Spencer's fork / exact commit used for validation.
- [ ] Add a tiny host spec JSON file containing only `codex` and `claude-code`, with host roots chosen to preserve the current `lark-doc-exporter` behavior.
- [ ] Run `uv sync` to verify the dependency resolves in this repo.

### Task 2: Replace the local installer implementation with a `kitup` adapter

**Files:**
- Modify: `src/lark_synced_export/skill_install.py`
- Modify: `src/lark_synced_export/cli.py` (only if argument/help text needs small alignment)
- Test: `tests/test_skill_install.py`

- [ ] Remove the duplicated local copy/install/rollback implementation that `kitup` now owns.
- [ ] Build adapter helpers that:
  - map `--host auto|codex|claude|all` to `kitup` selectors
  - load bundled skill assets through `importlib.resources.as_file`
  - call `kitup.plan_bundled_skill(...)` / `kitup.install_bundled_skill(...)`
  - normalize `kitup` reports into a stable JSON result payload
- [ ] Keep non-interactive CLI behavior: `skill install` should remain a direct command, not a prompt-driven workflow.

### Task 3: Update tests to the new ownership and result contract

**Files:**
- Modify: `tests/test_skill_install.py`
- Modify: `tests/test_cli.py` if JSON surface assertions need refresh

- [ ] Update metadata assertions from `.lark-doc-exporter-install.json` to `.kitup.json`.
- [ ] Update force/overwrite expectations to match `kitup` conflict semantics.
- [ ] Preserve coverage for:
  - auto detection
  - explicit host install
  - force overwrite of unmanaged targets
  - dry-run
  - CLI JSON output
- [ ] Remove tests that only exercise deleted local rollback internals, or replace them with equivalent adapter-level behavior tests if still meaningful.

### Task 4: Document the draft dependency and migration behavior

**Files:**
- Modify: `README.md`
- Modify: `src/lark_synced_export/skill_assets/lark-doc-exporter/SKILL.md` only if command wording or expectations changed materially

- [ ] Document that this draft PR temporarily uses `kitup` underneath `skill install`.
- [ ] Keep end-user CLI examples stable unless the JSON/behavior change forces wording updates.
- [ ] Note any migration caveat that old installs without `.kitup.json` now require `--force`.

### Task 5: Validate and prepare the PR

**Files:**
- Modify: draft PR body / review summary (not a repo file)

- [ ] Run targeted tests for the migrated installer surface.
- [ ] Run the largest practical repo validation set and record the pre-existing auth-gated e2e failure separately if it remains.
- [ ] Commit the branch changes with signed conventional commits.
- [ ] Push the branch and open a draft PR against `lark-doc-exporter`.
- [ ] In the PR description, call out:
  - temporary dependency on `kitup` PR #13 commit
  - what behavior was intentionally preserved
  - what metadata / migration behavior changed
