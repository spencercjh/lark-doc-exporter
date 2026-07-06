from __future__ import annotations

import argparse
import inspect
import json
import sys
from pathlib import Path

from .doctor import run_doctor
from .exporter import export_document
from .skill_install import run_skill_install


def parse_export_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export Feishu/Lark document URLs to Markdown and native Feishu PDF. "
            "Only native Feishu PDF is supported."
        ),
        epilog=(
            "Other commands:\n"
            "  doctor\n"
            "  skill install [--host {auto,codex,claude,all}] [--force] [--dry-run]\n"
            "\n"
            "Inputs must be full Feishu/Lark document URLs supported by the native-only exporter."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--doc",
        required=True,
        help="Full Feishu/Lark document URL to export.",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory for output artifacts. Default: %(default)s",
    )
    parser.add_argument(
        "--formats",
        default="markdown,pdf",
        help="Comma-separated export formats. Supported: markdown,pdf",
    )
    parser.add_argument(
        "--title-suffix",
        default="",
        help="Suffix appended to the temporary expanded doc title. Default: empty.",
    )
    parser.add_argument(
        "--file-stem",
        default="",
        help="Optional output filename stem. Defaults to the expanded doc title slug.",
    )
    parser.add_argument(
        "--keep-temp-doc",
        action="store_true",
        help="Keep the temporary expanded doc instead of deleting it after the Markdown export step. Default: false.",
    )
    parser.add_argument(
        "--pdf-mode",
        choices=["native"],
        default="native",
        help="PDF pipeline selection. Only native Feishu PDF is supported.",
    )
    return parser.parse_args(argv)


def parse_skill_install_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="lark-doc-exporter skill install",
        description="Install the bundled companion skill into Codex and/or Claude Code.",
    )
    parser.add_argument(
        "--host",
        choices=["auto", "codex", "claude", "all"],
        default="auto",
        help="Install target selection. Auto mode uses only already-detected hosts.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing unmanaged target directory.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned target paths without writing files.",
    )
    return parser.parse_args(argv)


def run_main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if argv and argv[0] == "doctor":
        print(json.dumps(run_doctor(), ensure_ascii=False, indent=2))
        return 0

    if argv[:2] == ["skill", "install"]:
        args = parse_skill_install_args(argv[2:])
        print(
            json.dumps(
                run_skill_install(
                    host=args.host,
                    force=args.force,
                    dry_run=args.dry_run,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if argv and argv[0] == "skill":
        raise SystemExit(
            "unsupported skill command; expected `lark-doc-exporter skill install`"
        )

    args = parse_export_args(argv)
    formats = [item.strip() for item in args.formats.split(",") if item.strip()]
    allowed = {"markdown", "pdf"}
    invalid = [fmt for fmt in formats if fmt not in allowed]
    if invalid:
        raise SystemExit(f"unsupported formats: {', '.join(invalid)}")
    export_kwargs = {
        "doc_ref": args.doc,
        "output_dir": Path(args.output_dir).expanduser().resolve(),
        "formats": formats,
        "title_suffix": args.title_suffix,
        "file_stem": args.file_stem,
        "keep_temp_doc": args.keep_temp_doc,
        "pdf_mode": args.pdf_mode,
    }
    export_signature = inspect.signature(export_document)
    if "theme_name" in export_signature.parameters:
        export_kwargs["theme_name"] = "default"
    if "override_css" in export_signature.parameters:
        export_kwargs["override_css"] = None

    result = export_document(**export_kwargs)
    for warning in result.get("warnings", []):
        sys.stderr.write(f"warning: {warning}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok", False) else 1


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
