# lark-doc-exporter

Export Feishu/Lark document URLs with synced blocks expanded into:

- localized Markdown via `feishu-docx`
- native Feishu PDF with AI-footer post-processing

## Requirements

- Python 3.14
- `lark-cli` configured for the native PDF path
- `feishu-docx` available for Markdown export

If you use `uvx` or `uv tool install`, `uv` can provision the required Python
for the tool environment automatically.

## Contract

`lark-doc-exporter` is now a native-only exporter:

- inputs must be full document URLs
- Markdown always comes from `feishu-docx`
- PDF always comes from Feishu native export
- `--pdf-mode native` remains accepted only as a compatibility shell

There is no rendered mode, theme selection, custom CSS support, or token-only
input path.

## Quick Start

```bash
uv tool install lark-doc-exporter
lark-doc-exporter \
  --doc "https://dynamia-ai.feishu.cn/wiki/BVXXwgzbZivjQZkr7jmcsGcinGh" \
  --output-dir exports/native \
  --formats markdown,pdf \
  --pdf-mode native
```

## Environment Check

```bash
lark-doc-exporter doctor
```

`doctor` checks whether `lark-cli` is ready for native PDF and whether
`feishu-docx` is ready for Markdown.

## One-off Run

```bash
uvx lark-doc-exporter \
  --doc "https://dynamia-ai.feishu.cn/wiki/BVXXwgzbZivjQZkr7jmcsGcinGh" \
  --output-dir exports/native \
  --formats markdown,pdf \
  --pdf-mode native
```

## Install As A Tool

```bash
lark-doc-exporter skill install --dry-run
lark-doc-exporter skill install
```

Auto mode installs the companion skill into every detected supported host:

- Codex: `~/.agents/skills/lark-doc-exporter`
- Claude Code: `~/.claude/skills/lark-doc-exporter`

Use `--host codex`, `--host claude`, or `--host all` to target specific hosts.
`--dry-run` previews the install plan and target directories without writing
files. Use `--force` only when you intentionally want to replace an existing
unmanaged target directory.

## Output

- `markdown` writes the localized Markdown file into the output directory.
- `pdf` writes the native Feishu PDF with footer post-processing.
- `images/` contains same-run localized image assets used by the Markdown.

For combined `markdown,pdf` runs, the JSON result keeps the native PDF metadata
fields and includes both output paths.

## Native PDF Mode

```bash
lark-doc-exporter \
  --doc "https://dynamia-ai.feishu.cn/wiki/BVXXwgzbZivjQZkr7jmcsGcinGh" \
  --output-dir exports/native \
  --formats pdf \
  --pdf-mode native
```

Native mode rules:

- omitting `--pdf-mode` behaves the same as `--pdf-mode native`
- any non-native `--pdf-mode` value is rejected
- success states are `removed` and `not_found`
- failure states emit warnings and keep `<stem>.native-raw.pdf` for inspection

## Development

Use the Git URL or a local checkout only when you intentionally need unreleased
code:

```bash
uvx --from git+https://github.com/spencercjh/lark-doc-exporter lark-doc-exporter doctor

git clone https://github.com/spencercjh/lark-doc-exporter
cd lark-doc-exporter
uv sync --python 3.14 --group dev
make fmt
make ci

# Optional runtime/environment check (not part of required CI)
uv run lark-doc-exporter doctor
```

## Notes

- when a temp doc is created for the native PDF stage, it is deleted by default
  after the export step
- use `--keep-temp-doc` only when you need to inspect that intermediate
  document
- Feishu image `authcode` URLs expire quickly, so image localization happens in
  the same run as the Markdown export
