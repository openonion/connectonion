from connectonion import browser_preview


def test_default_preview_coordinates_are_exact():
    assert browser_preview.RELEASE_CHANNEL == "preview"
    assert browser_preview.ONIONWRIGHT_VERSION == "0.0.13.dev3"
    assert browser_preview.ONIONWRIGHT_ARTIFACT == (
        "onionwright/0.0.13.dev3/onionwright-0.0.13.dev3-py3-none-any.whl"
    )
    assert browser_preview.api_url() == ("https://browser-preview.oo.openonion.ai")


def test_project_environment_cannot_redirect_the_preview_credential(monkeypatch):
    monkeypatch.setenv(
        "CONNECTONION_BROWSER_PREVIEW_API_URL", "http://127.0.0.1:8000"
    )
    monkeypatch.setenv("OO_API_URL", "https://production.example.test")

    assert browser_preview.api_url() == browser_preview.DEFAULT_API_URL
