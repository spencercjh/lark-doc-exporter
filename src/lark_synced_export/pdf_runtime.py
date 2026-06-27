from __future__ import annotations

import os
import shutil
from pathlib import Path

from playwright.sync_api import sync_playwright


BROWSER_CANDIDATES = (
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
    "microsoft-edge",
)


def resolve_browser_executable() -> str | None:
    explicit = os.environ.get("LARK_DOC_EXPORTER_CHROMIUM")
    if explicit:
        browser_path = Path(explicit).expanduser()
        if not browser_path.is_file():
            raise FileNotFoundError(
                f"`LARK_DOC_EXPORTER_CHROMIUM` points to a missing browser executable: {browser_path}"
            )
        return str(browser_path)

    for name in BROWSER_CANDIDATES:
        candidate = shutil.which(name)
        if candidate:
            return candidate

    return None


def launch_browser(playwright):
    executable = resolve_browser_executable()
    if executable:
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        return browser, executable

    browser = playwright.chromium.launch(headless=True)
    return browser, "playwright-managed"


def check_chromium_ready() -> tuple[bool, str]:
    try:
        with sync_playwright() as playwright:
            browser, source = launch_browser(playwright)
            browser.close()
        return True, f"Chromium is available via {source}."
    except Exception as exc:  # noqa: BLE001 - diagnostic probe surfaces any failure as a hint
        return (
            False,
            "Chromium is not ready. Install a system Chrome/Chromium binary or run "
            "`uvx --from playwright playwright install chromium`. "
            f"Original error: {exc}",
        )


def render_html_to_pdf(input_html: Path, output_pdf: Path) -> None:
    with sync_playwright() as playwright:
        browser, _source = launch_browser(playwright)
        try:
            page = browser.new_page()
            page.goto(input_html.resolve().as_uri(), wait_until="load")
            page.emulate_media(media="print")
            page.pdf(
                path=str(output_pdf.resolve()),
                format="A4",
                print_background=True,
                prefer_css_page_size=True,
            )
        finally:
            browser.close()
