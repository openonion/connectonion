import pytest

from connectonion import browser_preview


def test_default_preview_coordinates_are_exact(monkeypatch):
    monkeypatch.delenv(browser_preview.API_URL_ENV, raising=False)

    assert browser_preview.RELEASE_CHANNEL == "preview"
    assert browser_preview.ONIONWRIGHT_VERSION == "0.0.13.dev3"
    assert browser_preview.ONIONWRIGHT_ARTIFACT == (
        "onionwright/0.0.13.dev3/onionwright-0.0.13.dev3-py3-none-any.whl"
    )
    assert browser_preview.api_url() == ("https://browser-preview.oo.openonion.ai")


@pytest.mark.parametrize(
    "value",
    [
        "",
        "http://preview.example.com",
        "ftp://preview.example.com",
        "https://user:pass@preview.example.com",
        "https://preview.example.com/path",
        "https://preview.example.com?channel=preview",
        "https://preview.example.com#preview",
    ],
)
def test_unsafe_preview_origins_fail_closed(monkeypatch, value):
    monkeypatch.setenv(browser_preview.API_URL_ENV, value)

    with pytest.raises(browser_preview.BrowserPreviewConfigError):
        browser_preview.api_url()


@pytest.mark.parametrize(
    "value",
    ["http://127.0.0.1:8000", "http://localhost:8000", "http://[::1]:8000"],
)
def test_local_e2e_may_use_loopback_http(monkeypatch, value):
    monkeypatch.setenv(browser_preview.API_URL_ENV, value + "/")

    assert browser_preview.api_url() == value
