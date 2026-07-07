---
name: lark-doc-exporter
description: Use when a user wants to export a Feishu/Lark doc URL into localized Markdown and native PDF, or needs this companion skill installed into Codex or Claude Code.
---

# lark-doc-exporter

Use this tool when a user wants to:

- export a Feishu/Lark doc URL into localized Markdown
- export native Feishu PDF output
- check whether `lark-cli` is ready for native PDF and whether `feishu-docx` is
  ready for Markdown
- install this companion skill into supported AI hosts

## Prerequisites

- `lark-cli` available on `PATH` with a configured session for native PDF
- `feishu-docx` available for Markdown export
- the `lark-doc-exporter` command installed if the user wants repeated local use

## Common commands

```bash
lark-doc-exporter \
  --doc "<full-doc-url>" \
  --output-dir exports/demo \
  --formats markdown,pdf \
  --pdf-mode native
```

Expands synced blocks, exports Markdown, localizes images, and uses native Feishu PDF plus footer handling.

```bash
lark-doc-exporter doctor
```

Checks whether `lark-cli` is ready for native PDF and whether `feishu-docx` is ready for Markdown.

```bash
lark-doc-exporter skill install --dry-run
lark-doc-exporter skill install --host codex
lark-doc-exporter skill install --host all --force
```

Installs this companion skill into supported AI hosts. Auto mode installs only into detected hosts; explicit `--host` may create the host skill root.

## Key parameters

- `--pdf-mode native`: compatibility shell for the only supported PDF path
- `--formats markdown,pdf`: choose output formats
- `--keep-temp-doc`: keep the temporary expanded Feishu doc for inspection
- `skill install --host codex|claude|all`: select install targets
- `skill install --force`: overwrite an unknown existing target directory
- `skill install --dry-run`: print planned writes without changing the filesystem

## Guidance

- Use full URL document refs, not bare tokens.
- Markdown comes from `feishu-docx`; PDF comes from native Feishu export.
- Treat `--pdf-mode native` as a compatibility shell for the native-only contract.
- Use `doctor` before the first export on a new machine, or when readiness is unclear.
- Use `--dry-run` before `skill install` when the user wants to verify target paths.
