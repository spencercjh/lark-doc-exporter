# lark-doc-exporter Companion Skill Install Design

Date: 2026-06-27

## Context

`lark-doc-exporter` is already moving toward an install-first CLI model:

- `uvx --from git+https://github.com/spencercjh/lark-doc-exporter ...`
- `uv tool install git+https://github.com/spencercjh/lark-doc-exporter`

Spencer wants the tool to ship with a companion AI skill that can be installed
for both supported hosts on this machine:

- Codex via `~/.agents/skills`
- Claude Code via `~/.claude/skills`

The companion skill is not part of the exporter runtime itself, so the design
must solve a different problem from the existing installable-tool work:

- keep the exporter CLI behavior stable
- add a host-aware `skill install` flow
- make the installed tool able to materialize the bundled skill without needing
  a repository checkout
- avoid silent writes into unrelated directories

Review feedback from Kimi tightened the design in a few important ways:

- bundled assets should be loaded using package data plus
  `importlib.resources`
- home-directory resolution should use `Path.home()`
- explicit host selection may create missing parent directories, while auto
  mode should remain conservative
- `SKILL.md` must document the actual command surface and prerequisites
- `skill install` should support `--dry-run`

## Goals

- Add an explicit `lark-doc-exporter skill install` command that installs the
  bundled companion skill for Codex and/or Claude Code.
- Keep the existing root export CLI intact:
  `lark-doc-exporter --doc ... --output-dir ...`
- Keep `lark-doc-exporter doctor` focused on exporter runtime readiness rather
  than companion-skill state.
- Ship the skill as package assets so an installed wheel/tool can install the
  skill without access to the repo checkout.
- Make host detection, overwrite behavior, and failure modes explicit and easy
  to understand from CLI output.
- Keep the v1 surface intentionally small and operationally safe.

## Non-Goals

- Auto-installing the skill during `uv tool install` or `uvx`.
- Auto-installing the skill the first time any exporter command runs.
- Fetching the skill from GitHub releases or any remote endpoint.
- Adding a separate `skill upgrade` command in v1.
- Teaching `doctor` to validate companion-skill installation state.
- Building a general-purpose package manager for skills.

## Approaches Considered

### 1. Chosen: bundle skill assets in the Python package and install them explicitly

Package the companion skill inside the Python distribution and expose
`lark-doc-exporter skill install` as the single supported installation path.

Why choose it:

- keeps CLI version and installed skill version aligned
- works from wheel / `uv tool install` without a repo checkout
- remains offline-capable once the CLI is installed
- keeps the skill content as ordinary repo-managed files rather than Python
  string templates

### 2. Generate the skill dynamically from Python strings/templates

Keep only templates in Python code and synthesize `SKILL.md` during install.

Why not choose it:

- pushes long-form skill content into Python implementation files
- makes review and later skill editing harder
- scales poorly once `references/` or richer supporting material is needed

### 3. Fetch the skill from GitHub/releases at install time

Have `skill install` download the latest skill payload from the remote repo or a
release asset.

Why not choose it:

- introduces unnecessary network dependency
- creates version-drift risk between CLI and skill
- adds remote failure modes to a flow that should stay local and predictable

## Chosen Design

### 1. Command Surface

The CLI should keep its current three-mode shape:

- default export mode:
  `lark-doc-exporter --doc ... --output-dir ...`
- diagnostics:
  `lark-doc-exporter doctor`
- companion skill installation:
  `lark-doc-exporter skill install`

This task must not force a migration to an `export` subcommand just because a
new `skill` subcommand is being added. Preserving the current export entrypoint
keeps README examples and current user expectations stable.

### 2. Packaged Skill Assets

The companion skill should be stored as package data inside the Python
distribution, with a layout like:

- `src/lark_synced_export/skill_assets/lark-doc-exporter/SKILL.md`
- `src/lark_synced_export/skill_assets/lark-doc-exporter/references/...`

Implementation-facing constraints:

- assets must be included through package-data configuration
- runtime access must use `importlib.resources` rather than repo-relative paths
- `skill install` must work from an installed tool, not only from a source tree

This is the core packaging boundary: the installed CLI owns the skill payload it
installs.

### 3. Skill Content Boundary

The bundled `SKILL.md` must describe the actual tool that ships today. At a
minimum it should cover:

- tool purpose
- common commands:
  - exporter command
  - `doctor`
  - `skill install`
- relevant parameters at a high level
- prerequisites and environment expectations:
  - `lark-cli`
  - Chromium/browser availability for the PDF path

The skill should be useful immediately after installation without depending on
tribal knowledge or repo-only context.

### 4. Host Detection and Targets

The installer should use `Path.home()` and support these host roots:

- Codex: `~/.agents/skills`
- Claude Code: `~/.claude/skills`

Install targets are:

- `~/.agents/skills/lark-doc-exporter`
- `~/.claude/skills/lark-doc-exporter`

Default behavior in `auto` mode:

- if both host roots exist, install to both
- if only one exists, install only there
- if neither exists, fail with a clear unsupported-host message

Explicit-host behavior:

- `--host codex` targets only the Codex path
- `--host claude` targets only the Claude Code path
- `--host all` targets both paths
- when the user explicitly selects a host, the installer may create the missing
  parent directory for that host

This keeps auto mode conservative while still allowing intentional setup for a
specific host.

### 5. Install, Conflict, and Upgrade Semantics

`skill install` should act as both install and upgrade:

- if the target directory does not exist, create it and install the packaged
  skill
- if the target directory exists and is known to have been installed by
  `lark-doc-exporter`, allow in-place upgrade
- if the target directory exists but is user-managed or from an unknown source,
  fail by default and require `--force`

Ownership should be tracked by a lightweight metadata file stored in the
installed skill directory, e.g.:

- `.lark-doc-exporter-install.json`

The metadata should record enough to make upgrades explainable:

- tool name
- tool version
- install time
- target host

No separate `upgrade` command is needed in v1. Re-running
`lark-doc-exporter skill install` is the only supported lifecycle command.

### 6. Parameter Surface

The v1 `skill install` parameter surface should stay minimal:

- `--host codex|claude|all`
  - default: `auto`
- `--force`
- `--dry-run`

`--dry-run` is justified because the command writes into user home directories
and should support previewing the exact target paths before changing them.

No additional package-manager-like controls should be added in v1.

### 7. CLI Messaging

The help and runtime messages should make the flow self-explanatory:

- top-level help should expose `doctor` and `skill install`
- `skill install --help` should explain host selection and overwrite behavior
- success output should list the exact installed paths
- failure output should clearly distinguish:
  - no supported host detected
  - existing unknown/user-managed directory
  - `--force` required

The user should not need to inspect source code to understand what happened.

### 8. README Positioning

README should treat companion-skill installation as a standard setup step after
tool installation, for example:

```bash
uv tool install git+https://github.com/spencercjh/lark-doc-exporter
lark-doc-exporter skill install
```

The README should also document:

- what the command installs
- that auto mode installs to every detected supported host
- that `--host` can restrict installation to a specific host
- that `--dry-run` previews writes

This should appear near the install flow, not be buried as an advanced
postscript.

### 9. doctor Boundary

`doctor` should remain responsible only for exporter runtime readiness:

- `lark-cli`
- Chromium/browser availability

Companion-skill installation should remain outside `doctor` in v1 because skill
presence is not a prerequisite for document export itself. Combining them would
blur two separate readiness models:

- “can I run the exporter?”
- “have I installed the companion skill for an AI host?”

## Validation Plan

The validation strategy should prove both packaging correctness and safe local
install behavior.

### Unit-Level Coverage

- host detection logic
- path resolution logic
- metadata read/write logic
- conflict detection
- `--force` override behavior
- `--dry-run` no-write behavior

### CLI-Level Coverage

- install succeeds into mocked Codex directory
- install succeeds into mocked Claude Code directory
- `--host codex`
- `--host claude`
- `--host all`
- auto mode failure when no host roots exist
- conflict failure when unknown target already exists
- forced overwrite with `--force`

### Package-Level Smoke Coverage

After building/installing the tool into an isolated environment:

- run `lark-doc-exporter skill install --dry-run`
- run `lark-doc-exporter skill install`
- verify the installed skill came from package assets rather than repo-local
  files

This must be validated outside the repo checkout to prove that the package
boundary is real.

## Acceptance Criteria

This design is only successful if all of the following are true:

1. After `uv tool install ...`, the installed command can run
   `lark-doc-exporter skill install`.
2. The installer reads bundled skill assets from the package, not from
   repository-relative paths.
3. Auto mode detects and installs to supported host roots correctly.
4. Explicit `--host` can target a host even if its parent directory must be
   created.
5. Unknown/user-managed target directories are protected unless `--force` is
   used.
6. `--dry-run` reports intended writes without mutating the filesystem.
7. README is sufficient for a first-time user to install the tool and companion
   skill.
8. Existing export behavior and `doctor` behavior do not regress.
