from pathlib import Path

from lark_synced_export.pdf_runtime import check_chromium_ready, render_html_to_pdf


class FakePage:
    def __init__(self, calls: dict):
        self.calls = calls

    def goto(self, url: str, wait_until: str) -> None:
        self.calls["goto"] = {"url": url, "wait_until": wait_until}

    def emulate_media(self, media: str) -> None:
        self.calls["media"] = media

    def pdf(self, **kwargs) -> None:
        self.calls["pdf"] = kwargs


class FakeBrowser:
    def __init__(self, calls: dict):
        self.calls = calls

    def new_page(self) -> FakePage:
        return FakePage(self.calls)

    def close(self) -> None:
        self.calls["browser_closed"] = True


class FakeChromium:
    def __init__(self, calls: dict):
        self.calls = calls

    def launch(self, **kwargs):
        self.calls["launch"] = kwargs
        return FakeBrowser(self.calls)


class FakePlaywrightContext:
    def __init__(self, calls: dict):
        self.calls = calls
        self.chromium = FakeChromium(calls)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_render_html_to_pdf_prefers_explicit_browser(monkeypatch, tmp_path: Path):
    calls: dict = {}
    input_html = tmp_path / "render.html"
    output_pdf = tmp_path / "demo.pdf"
    input_html.write_text("<html><body>demo</body></html>", encoding="utf-8")

    monkeypatch.setenv("LARK_DOC_EXPORTER_CHROMIUM", "/custom/chromium")
    monkeypatch.setattr(
        "lark_synced_export.pdf_runtime.Path.is_file",
        lambda self: str(self) == "/custom/chromium",
    )
    monkeypatch.setattr(
        "lark_synced_export.pdf_runtime.sync_playwright",
        lambda: FakePlaywrightContext(calls),
    )

    render_html_to_pdf(input_html, output_pdf)

    assert calls["launch"]["executable_path"] == "/custom/chromium"
    assert calls["goto"]["url"] == input_html.resolve().as_uri()
    assert calls["goto"]["wait_until"] == "load"
    assert calls["media"] == "print"
    assert calls["pdf"]["format"] == "A4"
    assert calls["pdf"]["print_background"] is True
    assert calls["pdf"]["prefer_css_page_size"] is True


def test_check_chromium_ready_returns_helpful_failure(monkeypatch):
    class BrokenContext:
        def __enter__(self):
            raise RuntimeError("no browser")

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.delenv("LARK_DOC_EXPORTER_CHROMIUM", raising=False)
    monkeypatch.setattr(
        "lark_synced_export.pdf_runtime.sync_playwright",
        lambda: BrokenContext(),
    )

    ok, detail = check_chromium_ready()

    assert ok is False
    assert "uvx --from playwright playwright install chromium" in detail


def test_resolve_browser_executable_rejects_missing_env_override(monkeypatch):
    calls: dict = {}
    monkeypatch.setenv("LARK_DOC_EXPORTER_CHROMIUM", "/missing/chromium")
    monkeypatch.setattr("lark_synced_export.pdf_runtime.Path.is_file", lambda self: False)
    monkeypatch.setattr(
        "lark_synced_export.pdf_runtime.sync_playwright",
        lambda: FakePlaywrightContext(calls),
    )

    ok, detail = check_chromium_ready()
    assert ok is False
    assert "LARK_DOC_EXPORTER_CHROMIUM" in detail
