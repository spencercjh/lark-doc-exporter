from lark_synced_export.exporter import resolve_theme_css


def test_resolve_theme_css_returns_packaged_theme():
    theme_path = resolve_theme_css("default")
    assert theme_path.name == "default.css"
    assert theme_path.is_file()

