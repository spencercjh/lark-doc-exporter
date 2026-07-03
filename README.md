# lark-doc-exporter

Export Feishu/Lark docs with synced blocks expanded into:

- Markdown with localized images
- Recommended native Feishu PDF with AI-footer post-processing
- Optional locally rendered PDF when you need theme/CSS control

## Requirements

- Base requirements:
  - Python 3.14
  - `lark-cli` configured with a user session for native PDF and the legacy Markdown fallback
- For preferred `feishu-docx` Markdown export:
  - set `FEISHU_APP_ID` / `FEISHU_APP_SECRET` (and optionally `FEISHU_AUTH_MODE`, `FEISHU_IS_LARK`)
  - or configure `~/.feishu-docx/config.json`
- For `--pdf-mode native`:
  - no Chromium runtime is required
  - PyMuPDF is already bundled through this package dependency
- For `--pdf-mode rendered`:
  - a working Chrome/Chromium runtime, or the ability to install one with `uvx --from playwright playwright install chromium`

If you use `uvx` / `uv tool install`, `uv` can provision the required Python for
the tool environment automatically.

## Markdown Provider

`lark-doc-exporter` now prefers `feishu-docx` for Markdown generation when the
doc ref is URL-shaped and `FEISHU_*` credentials (or `~/.feishu-docx/config.json`)
are available.

Provider selection is controlled by `LARK_DOC_EXPORTER_MARKDOWN_PROVIDER`:

- `auto` (default): prefer `feishu-docx`, otherwise fall back to the legacy
  temp-doc + `lark-cli` Markdown path
- `feishu-docx`: require the new provider and fail fast if credentials are missing
- `legacy`: force the previous temp-doc + `lark-cli` Markdown path

Notes:

- bare Feishu tokens still fall back to `legacy`, because `feishu-docx` needs a
  URL-shaped doc ref to infer the document type
- native PDF still uses the temp-doc + `lark-cli` route even when Markdown came
  from `feishu-docx`
- the integrated `feishu-docx` attribution lives in `THIRD_PARTY_NOTICES.md`

## Quick Start

```bash
uv tool install lark-doc-exporter
lark-doc-exporter \
  --doc "https://dynamia-ai.feishu.cn/wiki/BVXXwgzbZivjQZkr7jmcsGcinGh" \
  --output-dir exports/native \
  --formats markdown,pdf \
  --pdf-mode native
```

That is the recommended PDF path unless you explicitly need local `--theme` /
`--css` control.

## Rendered PDF Mode

Use rendered mode only when you need local styling control:

```bash
uvx --from playwright playwright install chromium

lark-doc-exporter \
  --doc "https://dynamia-ai.feishu.cn/wiki/WEgBwqGYOiBoQikRzjncvJDonAg" \
  --output-dir exports/rendered \
  --formats markdown,pdf \
  --theme default \
  --pdf-mode rendered
```

If you already have a browser binary, you can point the exporter at it with
`LARK_DOC_EXPORTER_CHROMIUM=/path/to/chromium`.

## Environment Check

```bash
lark-doc-exporter doctor
```

`doctor` always checks `lark-cli`, and it also reports Chromium readiness for
`--pdf-mode rendered`. It now also reports whether the preferred `feishu-docx`
Markdown provider is ready or whether the run will stay on the legacy fallback.
Native mode does not require Chromium, so missing Chromium no longer makes the
overall doctor result fail.

## One-off Run

If you do not want a persistent tool install:

```bash
uvx lark-doc-exporter \
  --doc "https://dynamia-ai.feishu.cn/wiki/BVXXwgzbZivjQZkr7jmcsGcinGh" \
  --output-dir exports/native \
  --formats markdown,pdf \
  --pdf-mode native
```

## Install As A Tool

After installing the released package, companion-skill operations stay the same:

```bash
lark-doc-exporter skill install --dry-run
lark-doc-exporter skill install
```

Auto mode installs the companion skill into every detected supported host:

- Codex: `~/.agents/skills/lark-doc-exporter`
- Claude Code: `~/.claude/skills/lark-doc-exporter`

Use `--host codex`, `--host claude`, or `--host all` to target specific hosts. `--dry-run` previews the install plan and target directories without writing files. Use `--force` only when you intentionally want to replace an existing unmanaged target directory.

## Output

- `markdown` keeps the localized Markdown file in the output directory.
- `pdf` uses Feishu native PDF plus footer handling (`--pdf-mode native`) or local HTML/CSS + Chromium (`--pdf-mode rendered`).
- `images/` contains same-run localized image assets used by the Markdown/PDF.
- `markdown_provider` in the JSON result reports whether the run used
  `feishu-docx` or `legacy`.

### Native PDF Mode

Prefer this mode unless you need local theme/CSS control:

```bash
lark-doc-exporter \
  --doc "https://dynamia-ai.feishu.cn/wiki/BVXXwgzbZivjQZkr7jmcsGcinGh" \
  --output-dir exports/native \
  --formats pdf \
  --pdf-mode native
```

Native mode rules:

- only the PDF branch changes; markdown stays on the current markdown pipeline
- explicit non-default `--theme` / `--css` are rejected
- success states are `removed` and `not_found`
- failure states emit warnings and keep `<stem>.native-raw.pdf` for inspection

## Themes

Themes and custom CSS apply only to `--pdf-mode rendered`.

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

## Development / Unreleased

Use the Git URL or a local checkout only when you intentionally need unreleased code:

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

- Markdown now prefers `feishu-docx` and only uses the temporary Feishu doc
  when the run stays on `legacy` or when native PDF still needs the expanded
  temp doc.
- When a temp doc is created, it is deleted by default after the export step.
  Use `--keep-temp-doc` only when you need to inspect that intermediate
  document.
- Feishu image `authcode` URLs expire quickly, so image localization happens in
  the same run as the Markdown export.
