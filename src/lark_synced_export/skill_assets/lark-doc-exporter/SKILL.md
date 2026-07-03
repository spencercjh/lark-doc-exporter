---
name: lark-doc-exporter
description: Use when a user wants to export a Feishu/Lark doc into localized Markdown and PDF, prefers native PDF as the recommended path, or needs this companion skill installed into Codex or Claude Code.
---

# lark-doc-exporter

Use this tool when a user wants to:

- export a Feishu/Lark doc into localized Markdown
- prefer `feishu-docx` for richer Markdown blocks while keeping a legacy fallback
- use native Feishu PDF mode as the default recommended PDF path
- render a local PDF only when they explicitly need `--theme` / `--css`
- check whether `lark-cli` is ready, or whether Chromium is ready for rendered mode
- install this companion skill into supported AI hosts

## Prerequisites

- `lark-cli` available on `PATH` with a user session configured for native PDF and legacy fallback
- `feishu-docx` becomes the preferred Markdown provider when `FEISHU_APP_ID` / `FEISHU_APP_SECRET` or `~/.feishu-docx/config.json` are configured
- the `lark-doc-exporter` command installed if the user wants repeated local use
- native mode does not require Chromium
- Chromium is needed only for rendered mode, and you can install it with `uvx --from playwright playwright install chromium`

## Common commands

```bash
lark-doc-exporter \
  --doc "<doc-url-or-token>" \
  --output-dir exports/demo \
  --formats markdown,pdf \
  --pdf-mode native
```

Expands synced blocks, exports Markdown, localizes images, and uses native Feishu PDF plus footer handling.

```bash
lark-doc-exporter \
  --doc "<doc-url-or-token>" \
  --output-dir exports/rendered \
  --formats markdown,pdf \
  --theme default \
  --pdf-mode rendered
```

Use rendered mode only when the user explicitly needs local theme/CSS control.

```bash
lark-doc-exporter doctor
```

Checks whether `lark-cli` is ready, whether Chromium is available for rendered mode, and whether the preferred `feishu-docx` Markdown provider is ready or will fall back to legacy.

```bash
lark-doc-exporter skill install --dry-run
lark-doc-exporter skill install --host codex
lark-doc-exporter skill install --host all --force
```

Installs this companion skill into supported AI hosts. Auto mode installs only into detected hosts; explicit `--host` may create the host skill root.

## Key parameters

- `--pdf-mode rendered|native`: choose native Feishu PDF or local rendered PDF
- `--formats markdown,pdf`: choose output formats
- `--theme default|company`: pick the built-in PDF theme for rendered mode
- `--css /path/to/extra.css`: layer extra print CSS on top of the rendered theme
- `--keep-temp-doc`: keep the temporary expanded Feishu doc for inspection
- `skill install --host codex|claude|all`: select install targets
- `skill install --force`: overwrite an unknown existing target directory
- `skill install --dry-run`: print planned writes without changing the filesystem
- `LARK_DOC_EXPORTER_MARKDOWN_PROVIDER=auto|feishu-docx|legacy`: choose the Markdown provider

## Guidance

- Prefer `--pdf-mode native` unless the user explicitly needs local styling control.
- Prefer the default `auto` Markdown-provider mode for URL-shaped docs when `FEISHU_APP_ID` / `FEISHU_APP_SECRET` (or `~/.feishu-docx/config.json`) are available.
- Use `LARK_DOC_EXPORTER_MARKDOWN_PROVIDER=legacy` when the user only has a bare token, needs the exact old behavior, or is debugging provider differences.
- Use rendered mode only when `--theme` / `--css` are the real requirement.
- Use `doctor` before the first rendered export on a new machine, or when Chromium setup is unclear.
- Use `--dry-run` before `skill install` when the user wants to verify target paths.
- If the user asks about attribution or licensing for the integrated provider, point them to `THIRD_PARTY_NOTICES.md`.
