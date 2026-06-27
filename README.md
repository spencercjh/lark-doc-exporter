# lark-doc-exporter

Export Feishu/Lark docs with synced blocks expanded into:

- Markdown with localized images
- Themeable local-rendered PDF

The PDF path deliberately avoids the Feishu `docs_ai -> export pdf` route so the
final file does not include the AI disclaimer injected by that server-side path.

## Requirements

- `lark-cli` configured with a user session
- Python 3.11+
- Node.js 20+

## Install

```bash
cd /home/azureuser/spencercjh/lark-doc-exporter
uv sync --group dev
npm install
npx playwright install chromium
```

`uv` manages the Python environment and dependencies. The PDF renderer still
uses the existing Node.js toolchain for `marked` and Playwright Chromium.

## Usage

```bash
uv run lark-doc-exporter \
  --doc "https://dynamia-ai.feishu.cn/wiki/WEgBwqGYOiBoQikRzjncvJDonAg" \
  --output-dir exports/demo \
  --formats markdown,pdf \
  --theme default
```

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
uv run lark-doc-exporter \
  --doc "https://dynamia-ai.feishu.cn/wiki/WEgBwqGYOiBoQikRzjncvJDonAg" \
  --output-dir exports/company \
  --formats pdf \
  --theme company \
  --css /path/to/your-company-print.css
```

## Development

```bash
uv run pytest
```

## Notes

- The current implementation still uses a temporary Feishu doc to translate the
  expanded XML into fresh Markdown.
- The temporary doc is deleted by default after the Markdown export step. Use
  `--keep-temp-doc` only when you need to inspect that intermediate document.
- Feishu image `authcode` URLs expire quickly, so image localization happens in
  the same run as the Markdown export.
