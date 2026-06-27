from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .doctor import run_doctor
from .exporter import export_document


def parse_export_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Expand Feishu/Lark synced blocks, export Markdown, and render local PDF."
    )
    parser.add_argument(
        "--doc",
        required=True,
        help="Original docx/wiki URL or token accepted by `lark-cli docs +fetch`.",
    )
    parser.add_argument(
        "--output-dir", required=True, help="Directory for output artifacts."
    )
    parser.add_argument(
        "--formats",
        default="markdown,pdf",
        help="Comma-separated export formats. Supported: markdown,pdf",
    )
    parser.add_argument(
        "--title-suffix",
        default="（同步块展开导出）",
        help="Suffix appended to the temporary expanded doc title.",
    )
    parser.add_argument(
        "--file-stem",
        default="",
        help="Optional output filename stem. Defaults to the expanded doc title slug.",
    )
    parser.add_argument(
        "--keep-temp-doc",
        action="store_true",
        help="Keep the temporary expanded doc instead of deleting it after the Markdown export step.",
    )
    parser.add_argument(
        "--theme",
        default="default",
        help="Built-in PDF theme name. Supported: default, company.",
    )
    parser.add_argument(
        "--css",
        default="",
        help="Optional extra CSS file layered on top of the selected theme for PDF output.",
    )
    return parser.parse_args(argv)


def run_main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if argv and argv[0] == "doctor":
        print(json.dumps(run_doctor(), ensure_ascii=False, indent=2))
        return 0

    args = parse_export_args(argv)
    formats = [item.strip() for item in args.formats.split(",") if item.strip()]
    allowed = {"markdown", "pdf"}
    invalid = [fmt for fmt in formats if fmt not in allowed]
    if invalid:
        raise SystemExit(f"unsupported formats: {', '.join(invalid)}")

    result = export_document(
        doc_ref=args.doc,
        output_dir=Path(args.output_dir).expanduser().resolve(),
        formats=formats,
        title_suffix=args.title_suffix,
        file_stem=args.file_stem,
        keep_temp_doc=args.keep_temp_doc,
        theme_name=args.theme,
        override_css=Path(args.css).expanduser().resolve() if args.css else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> None:
    try:
        raise SystemExit(run_main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception as exc:  # pragma: no cover - CLI boundary
        sys.stderr.write(f"{exc}\n")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
