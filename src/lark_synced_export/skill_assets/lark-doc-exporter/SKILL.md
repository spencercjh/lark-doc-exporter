---
name: lark-doc-exporter
description: Export Feishu/Lark docs with synced blocks expanded into Markdown plus rendered or native PDFs, and install this companion skill into Codex or Claude Code.
---

# lark-doc-exporter

Use this tool when a user wants to:

- export a Feishu/Lark doc into localized Markdown
- render a themeable local PDF from that Markdown or use native Feishu PDF mode
- check whether `lark-cli` and Chromium are ready
- install this companion skill into supported AI hosts

## Prerequisites

- `lark-cli` available on `PATH` with a user session configured
- Chromium available locally, or install it with `uvx --from playwright playwright install chromium`
- the `lark-doc-exporter` command installed if the user wants repeated local use

## Common commands

```bash
lark-doc-exporter doctor
```

Checks whether `lark-cli` and Chromium are ready for local export work.

```bash
lark-doc-exporter \
  --doc "<doc-url-or-token>" \
  --output-dir exports/demo \
  --formats markdown,pdf \
  --theme default \
  --pdf-mode rendered
```

Expands synced blocks, exports Markdown, localizes images, and optionally renders a local PDF or uses native Feishu PDF plus footer handling.

```bash
lark-doc-exporter skill install --dry-run
lark-doc-exporter skill install --host codex
lark-doc-exporter skill install --host all --force
```

Installs this companion skill into supported AI hosts. Auto mode installs only into detected hosts; explicit `--host` may create the host skill root.

## Key parameters

- `--formats markdown,pdf`: choose output formats
- `--theme default|company`: pick the built-in PDF theme
- `--css /path/to/extra.css`: layer extra print CSS on top of the chosen theme
- `--pdf-mode rendered|native`: choose local rendered PDF or native Feishu PDF plus footer handling
- `--keep-temp-doc`: keep the temporary expanded Feishu doc for inspection
- `skill install --host codex|claude|all`: select install targets
- `skill install --force`: overwrite an unknown existing target directory
- `skill install --dry-run`: print planned writes without changing the filesystem

## Guidance

- Prefer `doctor` before the first export on a new machine.
- Use `--dry-run` before `skill install` when the user wants to verify target paths.
- Use `--pdf-mode native` when the user wants Feishu native PDF layout plus AI-footer handling.
