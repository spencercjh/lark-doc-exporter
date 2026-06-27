# lark-doc-exporter

Export Feishu/Lark docs with synced blocks expanded into:

- Markdown with localized images
- Themeable locally rendered PDF

The PDF path deliberately avoids the Feishu `docs_ai -> export pdf` route so the
final file does not include the AI disclaimer injected by that server-side path.

## Requirements

- `lark-cli` configured with a user session
- Python 3.14
- A working Chrome/Chromium runtime, or the ability to install one with `uvx --from playwright playwright install chromium`

If you use `uvx` / `uv tool install`, `uv` can provision the required Python for
the tool environment automatically.

## Quick Start

```bash
uvx --from git+https://github.com/spencercjh/lark-doc-exporter lark-doc-exporter doctor
```

If Chromium is missing, prepare it once:

```bash
uvx --from playwright playwright install chromium
```

Then run an export without cloning the repo:

```bash
uvx --from git+https://github.com/spencercjh/lark-doc-exporter lark-doc-exporter \
  --doc "https://dynamia-ai.feishu.cn/wiki/WEgBwqGYOiBoQikRzjncvJDonAg" \
  --output-dir exports/demo \
  --formats markdown,pdf \
  --theme default
```

## Install As A Tool

For repeated use, install the command once:

```bash
uv tool install git+https://github.com/spencercjh/lark-doc-exporter
```

Then use it directly:

```bash
lark-doc-exporter doctor
lark-doc-exporter skill install --dry-run
lark-doc-exporter skill install

lark-doc-exporter \
  --doc "https://dynamia-ai.feishu.cn/wiki/WEgBwqGYOiBoQikRzjncvJDonAg" \
  --output-dir exports/demo \
  --formats markdown,pdf \
  --theme default
```

Auto mode installs the companion skill into every detected supported host:

- Codex: `~/.agents/skills/lark-doc-exporter`
- Claude Code: `~/.claude/skills/lark-doc-exporter`

Use `--host codex`, `--host claude`, or `--host all` to target specific hosts. `--dry-run` previews the install plan and target directories without writing files. Use `--force` only when you intentionally want to replace an existing unmanaged target directory.

## Chromium Setup

- `doctor` reports whether both `lark-cli` and Chromium are ready.
- If you already have a browser binary, you can point the exporter at it with `LARK_DOC_EXPORTER_CHROMIUM=/path/to/chromium`.
- If `LARK_DOC_EXPORTER_CHROMIUM` is set to a missing path, the command fails explicitly instead of silently falling back.

## Output

- `markdown` keeps the localized Markdown file in the output directory.
- `pdf` is rendered locally from the localized Markdown via HTML/CSS + Chromium.
- `images/` contains same-run localized image assets used by the Markdown/PDF.

## Themes

Built-in themes:

- `default`
- `company`

You can also layer custom CSS on top:

```bash
lark-doc-exporter \
  --doc "https://dynamia-ai.feishu.cn/wiki/WEgBwqGYOiBoQikRzjncvJDonAg" \
  --output-dir exports/company \
  --formats pdf \
  --theme company \
  --css /path/to/your-company-print.css
```

## Development

```bash
git clone https://github.com/spencercjh/lark-doc-exporter
cd lark-doc-exporter
uv sync --python 3.14 --group dev
make fmt
make ci

# Optional runtime/environment check (not part of required CI)
uv run lark-doc-exporter doctor
```

## Notes

- The current implementation still uses a temporary Feishu doc to translate the
  expanded XML into fresh Markdown.
- The temporary doc is deleted by default after the Markdown export step. Use
  `--keep-temp-doc` only when you need to inspect that intermediate document.
- Feishu image `authcode` URLs expire quickly, so image localization happens in
  the same run as the Markdown export.
