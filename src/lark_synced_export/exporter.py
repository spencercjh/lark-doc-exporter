from __future__ import annotations

import json
import mimetypes
import os
import re
import subprocess
import tempfile
import time
import urllib.request
from html import escape
from pathlib import Path

from .callout_markdown import normalize_markdown_callouts_file
from .feishu_docx_bridge import (
    export_markdown_with_feishu_docx,
    normalize_feishu_docx_assets,
    require_feishu_docx_credentials,
    validate_markdown_doc_ref,
)
from .mention_markdown import normalize_markdown_user_mentions_file
from .native_pdf_footer import FAILURE_STATUSES, postprocess_native_pdf

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


def run_json(cmd: list[str], cwd: Path | None = None) -> dict:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True)
    return json.loads(proc.stdout)


LARK_CLI_IDENTITY_ENV = "LARK_DOC_EXPORTER_IDENTITY"
EXPORT_TASK_POLL_INTERVAL_SECONDS = 2.0
# Native export tasks can take longer on GitHub-hosted runners than on local
# machines; keep the poll budget comfortably above observed CI latency.
EXPORT_TASK_POLL_TIMEOUT_SECONDS = 300.0


def resolve_lark_cli_identity() -> str:
    raw_identity = os.environ.get(LARK_CLI_IDENTITY_ENV, "")
    if not raw_identity.strip():
        return "user"
    identity = raw_identity.strip().lower()
    if identity not in {"user", "bot"}:
        raise ValueError(
            f"{LARK_CLI_IDENTITY_ENV} must be 'user' or 'bot'; got {raw_identity!r}"
        )
    return identity


def extract_title(xml_text: str) -> str:
    match = TITLE_RE.search(xml_text)
    if not match:
        return "Untitled"
    return re.sub(r"\s+", " ", match.group(1)).strip()


def fetch_full_xml(doc_ref: str, lark_cli_identity: str) -> str:
    payload = run_json(
        [
            "lark-cli",
            "docs",
            "+fetch",
            "--as",
            lark_cli_identity,
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
    src_token: str,
    src_block_id: str,
    cache: dict[tuple[str, str], str],
    lark_cli_identity: str,
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
            lark_cli_identity,
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


def expand_synced_references(xml_text: str, lark_cli_identity: str) -> tuple[str, int]:
    cache: dict[tuple[str, str], str] = {}
    total = 0

    for _ in range(12):
        changed = 0

        def repl(match: re.Match[str]) -> str:
            nonlocal changed
            changed += 1
            src_block_id, src_token = match.group(1), match.group(2)
            return fetch_synced_block(
                src_token,
                src_block_id,
                cache,
                lark_cli_identity,
            )

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


def create_temp_doc(
    xml_text: str, stage_dir: Path, lark_cli_identity: str
) -> tuple[str, str]:
    content_file = stage_dir / "expanded.xml"
    content_file.write_text(xml_text, encoding="utf-8")
    payload = run_json(
        [
            "lark-cli",
            "docs",
            "+create",
            "--as",
            lark_cli_identity,
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
    temp_doc_token: str,
    output_dir: Path,
    file_stem: str,
    formats: list[str],
    lark_cli_identity: str,
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
            lark_cli_identity,
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
        data = payload.get("data", {})
        saved_path = data.get("saved_path")
        if saved_path:
            results[fmt] = saved_path
            continue

        ticket = data.get("ticket")
        if not ticket:
            raise RuntimeError(
                "lark-cli drive +export returned neither saved_path nor ticket: "
                f"{json.dumps(payload, ensure_ascii=False)}"
            )

        deadline = time.monotonic() + EXPORT_TASK_POLL_TIMEOUT_SECONDS
        last_task_payload: dict | None = None
        while time.monotonic() < deadline:
            task_payload = run_json(
                [
                    "lark-cli",
                    "drive",
                    "+task_result",
                    "--as",
                    lark_cli_identity,
                    "--scenario",
                    "export",
                    "--ticket",
                    str(ticket),
                    "--file-token",
                    temp_doc_token,
                ]
            )
            last_task_payload = task_payload
            task_data = task_payload.get("data", {})
            if task_data.get("failed"):
                raise RuntimeError(
                    "lark-cli drive +task_result reported export failure: "
                    f"{json.dumps(task_payload, ensure_ascii=False)}"
                )
            if task_data.get("ready"):
                exported_file_token = task_data.get("file_token")
                if not exported_file_token:
                    raise RuntimeError(
                        "lark-cli drive +task_result reported ready without file_token: "
                        f"{json.dumps(task_payload, ensure_ascii=False)}"
                    )
                download_payload = run_json(
                    [
                        "lark-cli",
                        "drive",
                        "+export-download",
                        "--as",
                        lark_cli_identity,
                        "--file-token",
                        exported_file_token,
                        "--file-name",
                        file_name,
                        "--output-dir",
                        export_leaf,
                        "--overwrite",
                    ],
                    cwd=export_cwd,
                )
                download_saved_path = download_payload.get("data", {}).get("saved_path")
                if not download_saved_path:
                    raise RuntimeError(
                        "lark-cli drive +export-download returned no saved_path: "
                        f"{json.dumps(download_payload, ensure_ascii=False)}"
                    )
                results[fmt] = download_saved_path
                break
            time.sleep(EXPORT_TASK_POLL_INTERVAL_SECONDS)
        else:
            raise RuntimeError(
                "timed out waiting for lark-cli export task to complete: "
                f"ticket={ticket}, last_payload={json.dumps(last_task_payload or payload, ensure_ascii=False)}"
            )

    return results


def export_native_pdf(
    temp_doc_token: str,
    output_dir: Path,
    file_stem: str,
    lark_cli_identity: str,
) -> Path:
    result = export_doc(
        temp_doc_token,
        output_dir,
        file_stem,
        formats=["pdf"],
        lark_cli_identity=lark_cli_identity,
    )
    return Path(result["pdf"])


def delete_temp_doc(temp_doc_token: str, lark_cli_identity: str) -> None:
    try:
        run_json(
            [
                "lark-cli",
                "drive",
                "+delete",
                "--as",
                lark_cli_identity,
                "--file-token",
                temp_doc_token,
                "--type",
                "docx",
                "--yes",
                "--format",
                "json",
            ]
        )
    except subprocess.CalledProcessError as exc:
        try:
            payload = json.loads(exc.stdout)
        except json.JSONDecodeError:
            raise

        error = payload.get("error")
        if (
            isinstance(error, dict)
            and error.get("code") == 1061007
            and "file has been delete" in str(error.get("message", "")).lower()
        ):
            return
        raise


def prepare_temp_doc_stage(
    doc_ref: str,
    title_suffix: str,
    stage_dir: Path,
    lark_cli_identity: str,
) -> tuple[int, str, str, str]:
    raw_xml = fetch_full_xml(doc_ref, lark_cli_identity)
    expanded_xml, expanded_count = expand_synced_references(raw_xml, lark_cli_identity)
    normalized_xml, temp_title = normalize_xml_for_create(expanded_xml, title_suffix)
    temp_doc_token, temp_doc_url = create_temp_doc(
        normalized_xml, stage_dir, lark_cli_identity
    )
    return expanded_count, temp_title, temp_doc_token, temp_doc_url


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


def run_markdown_stage(
    doc_ref: str,
    stage_dir: Path,
    output_dir: Path,
    file_stem: str,
) -> tuple[Path, int, str]:
    validate_markdown_doc_ref(doc_ref)
    credentials = require_feishu_docx_credentials(doc_ref)
    raw_markdown_path, raw_assets_dir = export_markdown_with_feishu_docx(
        doc_ref,
        stage_dir,
        file_stem or None,
        credentials,
    )
    final_stem = file_stem or raw_markdown_path.stem
    localized_markdown_path = output_dir / f"{final_stem}.md"
    localized_count = normalize_feishu_docx_assets(
        raw_markdown_path,
        raw_assets_dir,
        localized_markdown_path,
        output_dir / "images",
    )
    normalize_markdown_user_mentions_file(localized_markdown_path)
    normalize_markdown_callouts_file(localized_markdown_path)
    return localized_markdown_path, localized_count, final_stem


def run_native_pdf_stage(
    doc_ref: str,
    stage_dir: Path,
    output_dir: Path,
    title_suffix: str,
    file_stem: str,
    keep_temp_doc: bool,
    lark_cli_identity: str,
) -> dict[str, object]:
    validate_markdown_doc_ref(doc_ref)
    expanded_count, temp_title, temp_doc_token, temp_doc_url = prepare_temp_doc_stage(
        doc_ref,
        title_suffix,
        stage_dir,
        lark_cli_identity,
    )
    output_stem = file_stem or slugify_filename(temp_title)
    output_pdf = output_dir / f"{output_stem}.pdf"
    raw_native_pdf = export_native_pdf(
        temp_doc_token,
        stage_dir,
        f"{output_stem}.native-raw",
        lark_cli_identity,
    )
    preserved_raw_pdf = output_dir / f"{output_stem}.native-raw.pdf"
    if output_pdf.exists():
        output_pdf.unlink()
    if preserved_raw_pdf.exists():
        preserved_raw_pdf.unlink()
    footer_result = postprocess_native_pdf(raw_native_pdf, output_pdf, preserved_raw_pdf)
    return {
        "expanded_references": expanded_count,
        "temp_doc_token": temp_doc_token,
        "temp_doc_url": temp_doc_url,
        "temp_doc_deleted": not keep_temp_doc,
        "output_pdf": footer_result.final_pdf_path,
        "ai_footer_postprocess": {
            "status": footer_result.status,
            "raw_pdf_path": footer_result.raw_pdf_path,
            "warning": footer_result.warning,
        },
        "warnings": [footer_result.warning] if footer_result.warning else [],
    }


def export_document(
    doc_ref: str,
    output_dir: Path,
    formats: list[str],
    title_suffix: str,
    file_stem: str,
    keep_temp_doc: bool,
    theme_name: str,
    override_css: Path | None,
    pdf_mode: str = "native",
) -> dict:
    if pdf_mode != "native":
        raise ValueError(f"unsupported pdf_mode: {pdf_mode}")

    output_dir.mkdir(parents=True, exist_ok=True)
    lark_cli_identity = resolve_lark_cli_identity()

    outputs: dict[str, str] = {}
    warnings: list[str] = []
    ai_footer_postprocess: dict | None = None
    localized_image_count = 0
    expanded_count: int | None = None
    temp_doc_token: str | None = None
    temp_doc_url: str | None = None
    temp_doc_deleted = True

    with tempfile.TemporaryDirectory(prefix="lark-doc-exporter-") as tmpdir:
        stage_dir = Path(tmpdir)
        if "markdown" in formats:
            localized_markdown_path, localized_image_count, _ = run_markdown_stage(
                doc_ref,
                stage_dir,
                output_dir,
                file_stem,
            )
            outputs["markdown"] = str(localized_markdown_path)

        if "pdf" in formats:
            native_pdf_stage = run_native_pdf_stage(
                doc_ref,
                stage_dir,
                output_dir,
                title_suffix,
                file_stem,
                keep_temp_doc,
                lark_cli_identity,
            )
            expanded_count = native_pdf_stage["expanded_references"]
            temp_doc_token = native_pdf_stage["temp_doc_token"]
            temp_doc_url = native_pdf_stage["temp_doc_url"]
            temp_doc_deleted = native_pdf_stage["temp_doc_deleted"]
            ai_footer_postprocess = native_pdf_stage["ai_footer_postprocess"]
            warnings.extend(native_pdf_stage["warnings"])
            if native_pdf_stage["output_pdf"]:
                outputs["pdf"] = native_pdf_stage["output_pdf"]
            if temp_doc_token and not keep_temp_doc:
                delete_temp_doc(temp_doc_token, lark_cli_identity)

    native_failure = (
        "pdf" in formats
        and ai_footer_postprocess is not None
        and ai_footer_postprocess["status"] in FAILURE_STATUSES
    )

    return {
        "ok": not native_failure,
        "doc": doc_ref,
        "expanded_references": expanded_count,
        "temp_doc_token": temp_doc_token,
        "temp_doc_deleted": temp_doc_deleted,
        "temp_doc_url": temp_doc_url,
        "localized_images": localized_image_count,
        "pdf_mode": "native" if "pdf" in formats else None,
        "ai_footer_postprocess": ai_footer_postprocess,
        "warnings": warnings,
        "outputs": outputs,
        "pdf_renderer": "feishu-native" if "pdf" in formats else None,
    }
