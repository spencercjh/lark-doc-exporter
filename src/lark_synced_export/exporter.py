from __future__ import annotations

import json
import mimetypes
import os
import re
import subprocess
import tempfile
import urllib.request
from html import escape
from pathlib import Path

from .callout_markdown import normalize_markdown_callouts_file
from .mention_markdown import normalize_markdown_user_mentions_file
from .markdown_runtime import render_markdown_body
from .native_pdf_footer import FAILURE_STATUSES, postprocess_native_pdf
from .pdf_runtime import render_html_to_pdf

THEMES_DIR = Path(__file__).with_name("themes")

REF_RE = re.compile(
    r'<synced_reference\b[^>]*src-block-id="([^"]+)"[^>]*src-token="([^"]+)"[^>]*>\s*</synced_reference>',
    re.S,
)
FRAGMENT_RE = re.compile(r"^\s*<fragment\b[^>]*>(.*)</fragment>\s*$", re.S)
SYNCED_SOURCE_OPEN_RE = re.compile(r"<synced-source\b[^>]*>")
TITLE_RE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.S)
ID_ATTR_RE = re.compile(r'\s+id="[^"]*"')
TOKEN_ATTR_RE = re.compile(r'\s+token="[^"]*"')
SRC_BLOCK_ID_ATTR_RE = re.compile(r'\s+src-block-id="[^"]*"')
SRC_TOKEN_ATTR_RE = re.compile(r'\s+src-token="[^"]*"')
URL_ATTR_RE = re.compile(r'\s+url="([^"]*)"')
IMG_TAG_RE = re.compile(r"<img\b([^>]*)/?>", re.S)
SOURCE_TAG_RE = re.compile(r"<source\b([^>]*)/?>", re.S)
MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\((https://[^)\s]+)\)")

BASE_CSS = """
@page {
  size: A4;
  margin: 16mm 14mm;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: "Noto Sans CJK SC", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
  color: var(--text, #1f2328);
  background: var(--surface, #ffffff);
  line-height: 1.6;
  font-size: 13px;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}

main {
  width: 100%;
  max-width: 920px;
  margin: 0 auto;
}

h1, h2, h3, h4 {
  page-break-after: avoid;
  break-after: avoid;
  line-height: 1.3;
  margin-top: 1.5em;
  margin-bottom: 0.6em;
}

h1 {
  font-size: 26px;
  border-bottom: 1px solid var(--border, #d0d7de);
  padding-bottom: 0.35em;
  margin-top: 0;
}

h2 {
  font-size: 20px;
  border-bottom: 1px solid var(--border, #d0d7de);
  padding-bottom: 0.25em;
}

h3 {
  font-size: 16px;
}

p, ul, ol {
  margin: 0 0 0.9em;
}

a {
  color: var(--accent, #0969da);
  text-decoration: none;
  word-break: break-all;
}

code {
  font-family: "SFMono-Regular", "Consolas", "Liberation Mono", monospace;
  background: var(--code-bg, #f6f8fa);
  padding: 0.15em 0.35em;
  border-radius: 4px;
  font-size: 0.92em;
}

pre {
  background: var(--code-bg, #f6f8fa);
  border: 1px solid var(--border, #d0d7de);
  border-radius: 8px;
  padding: 12px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  page-break-inside: avoid;
  break-inside: avoid;
  margin: 0 0 1em;
}

pre code {
  background: transparent;
  padding: 0;
}

table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  margin: 0 0 1em;
  page-break-inside: avoid;
  break-inside: avoid;
}

th, td {
  border: 1px solid var(--border, #d0d7de);
  padding: 8px 10px;
  vertical-align: top;
  text-align: left;
  word-break: break-word;
}

th {
  background: var(--surface-subtle, #f6f8fa);
  font-weight: 600;
}

img {
  max-width: 100%;
  height: auto;
  display: block;
  margin: 0.75em auto 1em;
  border: 1px solid var(--border, #d0d7de);
  border-radius: 8px;
  page-break-inside: avoid;
  break-inside: avoid;
}

blockquote {
  margin: 0 0 1em;
  padding: 0.1em 1em;
  color: var(--muted, #59636e);
  border-left: 4px solid var(--border, #d0d7de);
}

.callout {
  margin: 0 0 1em;
  padding: 0.9em 1em;
  border-left: 4px solid var(--callout-note-border, var(--border, #d0d7de));
  border-radius: 10px;
  background: var(--callout-note-bg, var(--surface-subtle, #f6f8fa));
  color: var(--callout-note-fg, var(--text, #1f2328));
  page-break-inside: avoid;
  break-inside: avoid;
}

.callout > :first-child {
  margin-top: 0;
}

.callout > :last-child {
  margin-bottom: 0;
}

.callout--note {
  border-left-color: var(--callout-note-border, var(--border, #d0d7de));
  background: var(--callout-note-bg, var(--surface-subtle, #f6f8fa));
  color: var(--callout-note-fg, var(--text, #1f2328));
}

.callout--tip {
  border-left-color: var(--callout-tip-border, var(--accent, #0969da));
  background: var(--callout-tip-bg, var(--surface-subtle, #f6f8fa));
  color: var(--callout-tip-fg, var(--text, #1f2328));
}

.callout--important {
  border-left-color: var(--callout-important-border, var(--accent, #0969da));
  background: var(--callout-important-bg, var(--surface-subtle, #f6f8fa));
  color: var(--callout-important-fg, var(--text, #1f2328));
}

.callout--warning {
  border-left-color: var(--callout-warning-border, var(--accent, #0969da));
  background: var(--callout-warning-bg, var(--surface-subtle, #f6f8fa));
  color: var(--callout-warning-fg, var(--text, #1f2328));
}

.callout--caution {
  border-left-color: var(--callout-caution-border, var(--accent, #0969da));
  background: var(--callout-caution-bg, var(--surface-subtle, #f6f8fa));
  color: var(--callout-caution-fg, var(--text, #1f2328));
}

hr {
  border: 0;
  border-top: 1px solid var(--border, #d0d7de);
  margin: 1.2em 0;
}
""".strip()


def run_json(cmd: list[str], cwd: Path | None = None) -> dict:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True)
    return json.loads(proc.stdout)


def extract_title(xml_text: str) -> str:
    match = TITLE_RE.search(xml_text)
    if not match:
        return "Untitled"
    return re.sub(r"\s+", " ", match.group(1)).strip()


def fetch_full_xml(doc_ref: str) -> str:
    payload = run_json(
        [
            "lark-cli",
            "docs",
            "+fetch",
            "--as",
            "user",
            "--api-version",
            "v2",
            "--doc",
            doc_ref,
            "--detail",
            "full",
            "--format",
            "json",
        ]
    )
    return payload["data"]["document"]["content"]


def fetch_synced_block(
    src_token: str, src_block_id: str, cache: dict[tuple[str, str], str]
) -> str:
    key = (src_token, src_block_id)
    if key in cache:
        return cache[key]

    payload = run_json(
        [
            "lark-cli",
            "docs",
            "+fetch",
            "--as",
            "user",
            "--api-version",
            "v2",
            "--doc",
            src_token,
            "--scope",
            "range",
            "--start-block-id",
            src_block_id,
            "--end-block-id",
            src_block_id,
            "--detail",
            "full",
            "--format",
            "json",
        ]
    )
    content = payload["data"]["document"]["content"]
    match = FRAGMENT_RE.match(content)
    if match:
        content = match.group(1).strip()
    cache[key] = content
    return content


def expand_synced_references(xml_text: str) -> tuple[str, int]:
    cache: dict[tuple[str, str], str] = {}
    total = 0

    for _ in range(12):
        changed = 0

        def repl(match: re.Match[str]) -> str:
            nonlocal changed
            changed += 1
            src_block_id, src_token = match.group(1), match.group(2)
            return fetch_synced_block(src_token, src_block_id, cache)

        xml_text = REF_RE.sub(repl, xml_text)
        total += changed
        if changed == 0:
            return xml_text, total

    raise RuntimeError("synced_reference expansion exceeded max depth")


def parse_attrs(attr_text: str) -> dict[str, str]:
    return {
        name: value for name, value in re.findall(r'([:\w-]+)="([^"]*)"', attr_text)
    }


def render_attr(name: str, value: str) -> str:
    return f' {name}="{value}"'


def normalize_img_tags(xml_text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        attrs = parse_attrs(match.group(1))
        href = attrs.pop("url", None) or attrs.pop("href", None)
        normalized: dict[str, str] = {}
        for key in ("width", "height", "caption", "name"):
            if key in attrs:
                normalized[key] = attrs[key]
        if href:
            normalized["href"] = href
        ordered = []
        for key in ("width", "height", "caption", "name", "href"):
            if key in normalized:
                ordered.append(render_attr(key, normalized[key]))
        return f"<img{''.join(ordered)}/>"

    return IMG_TAG_RE.sub(repl, xml_text)


def normalize_source_tags(xml_text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        attrs = parse_attrs(match.group(1))
        name = attrs.get("name", "attachment")
        url = attrs.get("url")
        if url:
            return f'<p>Attachment: <a href="{url}">{name}</a></p>'
        return f"<p>Attachment: {name}</p>"

    return SOURCE_TAG_RE.sub(repl, xml_text)


def normalize_xml_for_create(xml_text: str, title_suffix: str) -> tuple[str, str]:
    title = extract_title(xml_text)
    new_title = f"{title}{title_suffix}" if title_suffix else title
    xml_text = TITLE_RE.sub(f"<title>{escape(new_title)}</title>", xml_text, count=1)
    xml_text = SYNCED_SOURCE_OPEN_RE.sub("", xml_text)
    xml_text = xml_text.replace("</synced-source>", "")
    xml_text = ID_ATTR_RE.sub("", xml_text)
    xml_text = TOKEN_ATTR_RE.sub("", xml_text)
    xml_text = SRC_BLOCK_ID_ATTR_RE.sub("", xml_text)
    xml_text = SRC_TOKEN_ATTR_RE.sub("", xml_text)
    xml_text = URL_ATTR_RE.sub(r' href="\1"', xml_text)
    xml_text = normalize_img_tags(xml_text)
    xml_text = normalize_source_tags(xml_text)
    return xml_text, new_title


def create_temp_doc(xml_text: str, stage_dir: Path) -> tuple[str, str]:
    content_file = stage_dir / "expanded.xml"
    content_file.write_text(xml_text, encoding="utf-8")
    payload = run_json(
        [
            "lark-cli",
            "docs",
            "+create",
            "--as",
            "user",
            "--api-version",
            "v2",
            "--parent-position",
            "my_library",
            "--content",
            "@expanded.xml",
            "--format",
            "json",
        ],
        cwd=stage_dir,
    )
    document = payload["data"]["document"]
    return document["document_id"], document["url"]


def slugify_filename(name: str) -> str:
    name = re.sub(r"\s+", "-", name.strip())
    name = re.sub(r'[\\/:*?"<>|]', "-", name)
    name = re.sub(r"-{2,}", "-", name)
    return name.strip("-") or "export"


def export_doc(
    temp_doc_token: str, output_dir: Path, file_stem: str, formats: list[str]
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    export_cwd = output_dir.parent
    export_leaf = output_dir.name
    results: dict[str, str] = {}
    suffix_map = {"markdown": "md", "pdf": "pdf"}

    for fmt in formats:
        file_name = f"{file_stem}.{suffix_map[fmt]}"
        cmd = [
            "lark-cli",
            "drive",
            "+export",
            "--as",
            "user",
            "--token",
            temp_doc_token,
            "--doc-type",
            "docx",
            "--file-extension",
            fmt,
            "--file-name",
            file_name,
            "--output-dir",
            export_leaf,
            "--overwrite",
        ]
        payload = run_json(cmd, cwd=export_cwd)
        results[fmt] = payload["data"]["saved_path"]

    return results


def export_markdown(temp_doc_token: str, output_dir: Path, file_stem: str) -> Path:
    result = export_doc(temp_doc_token, output_dir, file_stem, formats=["markdown"])
    return Path(result["markdown"])


def export_native_pdf(temp_doc_token: str, output_dir: Path, file_stem: str) -> Path:
    result = export_doc(temp_doc_token, output_dir, file_stem, formats=["pdf"])
    return Path(result["pdf"])


def delete_temp_doc(temp_doc_token: str) -> None:
    run_json(
        [
            "lark-cli",
            "drive",
            "+delete",
            "--as",
            "user",
            "--file-token",
            temp_doc_token,
            "--type",
            "docx",
            "--yes",
            "--format",
            "json",
        ]
    )


def suffix_from_content_type(content_type: str) -> str:
    if not content_type:
        return ".bin"
    suffix = mimetypes.guess_extension(content_type.split(";")[0].strip())
    return suffix or ".bin"


def localize_markdown_images(
    markdown_path: Path, localized_path: Path, assets_dir: Path
) -> int:
    text = markdown_path.read_text(encoding="utf-8")
    assets_dir.mkdir(parents=True, exist_ok=True)
    image_count = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal image_count
        alt_text, url = match.group(1), match.group(2)
        image_count += 1
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = resp.read()
            suffix = suffix_from_content_type(resp.headers.get("Content-Type", ""))
        local_name = f"image-{image_count}{suffix}"
        local_path = assets_dir / local_name
        local_path.write_bytes(payload)
        rel_path = Path(os.path.relpath(local_path, start=localized_path.parent))
        return f"![{alt_text}]({rel_path.as_posix()})"

    localized = MD_IMAGE_RE.sub(repl, text)
    localized_path.write_text(localized, encoding="utf-8")
    return image_count


def resolve_theme_css(theme_name: str) -> Path:
    theme_path = THEMES_DIR / f"{theme_name}.css"
    if not theme_path.is_file():
        raise FileNotFoundError(f"unknown theme: {theme_name}")
    return theme_path


def build_render_html(
    body_html: Path,
    render_html: Path,
    title: str,
    theme_css: Path,
    override_css: Path | None,
) -> None:
    body = body_html.read_text(encoding="utf-8")
    theme = theme_css.read_text(encoding="utf-8")
    extra = override_css.read_text(encoding="utf-8") if override_css else ""
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
{BASE_CSS}

{theme}

{extra}
  </style>
</head>
<body>
  <main>
{body}
  </main>
</body>
</html>
"""
    render_html.write_text(html, encoding="utf-8")


def export_document(
    doc_ref: str,
    output_dir: Path,
    formats: list[str],
    title_suffix: str,
    file_stem: str,
    keep_temp_doc: bool,
    theme_name: str,
    override_css: Path | None,
    pdf_mode: str = "rendered",
) -> dict:
    if pdf_mode not in {"rendered", "native"}:
        raise ValueError(f"unsupported pdf_mode: {pdf_mode}")
    if override_css and not override_css.is_file():
        raise FileNotFoundError(f"override CSS not found: {override_css}")

    output_dir.mkdir(parents=True, exist_ok=True)

    raw_xml = fetch_full_xml(doc_ref)
    expanded_xml, expanded_count = expand_synced_references(raw_xml)
    normalized_xml, temp_title = normalize_xml_for_create(expanded_xml, title_suffix)
    final_stem = file_stem or slugify_filename(temp_title)

    outputs: dict[str, str] = {}
    warnings: list[str] = []
    ai_footer_postprocess: dict | None = None
    localized_image_count = 0
    theme_css_path: Path | None = None

    with tempfile.TemporaryDirectory(prefix="lark-doc-exporter-") as tmpdir:
        stage_dir = Path(tmpdir)
        temp_doc_token, temp_doc_url = create_temp_doc(normalized_xml, stage_dir)
        try:
            needs_markdown_artifacts = "markdown" in formats or (
                "pdf" in formats and pdf_mode == "rendered"
            )
            localized_markdown_path: Path | None = None

            if needs_markdown_artifacts:
                raw_markdown_path = export_markdown(
                    temp_doc_token, stage_dir, f"{final_stem}.raw"
                )
                render_root = output_dir if "markdown" in formats else stage_dir
                localized_markdown_path = render_root / f"{final_stem}.md"
                assets_dir = render_root / "images"
                localized_image_count = localize_markdown_images(
                    raw_markdown_path, localized_markdown_path, assets_dir
                )
                normalize_markdown_user_mentions_file(localized_markdown_path)
                normalize_markdown_callouts_file(localized_markdown_path)

                if "markdown" in formats:
                    outputs["markdown"] = str(localized_markdown_path)

            if "pdf" in formats:
                output_pdf = output_dir / f"{final_stem}.pdf"
                if pdf_mode == "rendered":
                    assert localized_markdown_path is not None
                    theme_css_path = resolve_theme_css(theme_name)
                    body_html = stage_dir / "body.html"
                    render_html = stage_dir / "render.html"
                    render_markdown_body(localized_markdown_path, body_html)
                    build_render_html(
                        body_html, render_html, temp_title, theme_css_path, override_css
                    )
                    render_html_to_pdf(render_html, output_pdf)
                    outputs["pdf"] = str(output_pdf)
                else:
                    raw_native_pdf = export_native_pdf(
                        temp_doc_token, stage_dir, f"{final_stem}.native-raw"
                    )
                    preserved_raw_pdf = output_dir / f"{final_stem}.native-raw.pdf"
                    if output_pdf.exists():
                        output_pdf.unlink()
                    if preserved_raw_pdf.exists():
                        preserved_raw_pdf.unlink()
                    footer_result = postprocess_native_pdf(
                        raw_native_pdf, output_pdf, preserved_raw_pdf
                    )
                    ai_footer_postprocess = {
                        "status": footer_result.status,
                        "raw_pdf_path": footer_result.raw_pdf_path,
                        "warning": footer_result.warning,
                    }
                    if footer_result.warning:
                        warnings.append(footer_result.warning)
                    if footer_result.final_pdf_path:
                        outputs["pdf"] = footer_result.final_pdf_path
        finally:
            if not keep_temp_doc:
                delete_temp_doc(temp_doc_token)

    native_failure = (
        "pdf" in formats
        and pdf_mode == "native"
        and ai_footer_postprocess is not None
        and ai_footer_postprocess["status"] in FAILURE_STATUSES
    )

    return {
        "ok": not native_failure,
        "doc": doc_ref,
        "expanded_references": expanded_count,
        "temp_doc_token": temp_doc_token,
        "temp_doc_deleted": not keep_temp_doc,
        "temp_doc_url": temp_doc_url,
        "localized_images": localized_image_count,
        "theme": theme_name if "pdf" in formats and pdf_mode == "rendered" else None,
        "pdf_mode": pdf_mode if "pdf" in formats else None,
        "ai_footer_postprocess": ai_footer_postprocess,
        "warnings": warnings,
        "outputs": outputs,
        "pdf_renderer": (
            "feishu-native"
            if "pdf" in formats and pdf_mode == "native"
            else "local-chromium"
            if "pdf" in formats
            else None
        ),
    }
