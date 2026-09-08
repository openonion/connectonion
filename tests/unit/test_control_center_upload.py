import httpx
import pytest

from connectonion.network.host.control_center.bundle import Bundle
from connectonion.network.host.control_center.upload import ArtifactUploader
from connectonion.network.host.control_center.runtime import RuntimeErrorState


def test_upload_sends_frozen_bundle_and_checks_origin_revision(monkeypatch, default_backend_url):
    bundle = Bundle({'index.html': b'<h1>fixed</h1>'})
    seen = []
    def handle(request):
        import json
        seen.append(request)
        assert request.headers['authorization'] == 'Bearer synthetic'
        assert json.loads(request.content)['revision'] == bundle.revision
        return httpx.Response(200, json={'revision': bundle.revision,
            'url': 'https://r-' + 'a' * 52 + '.apps.example.net/index.html'})
    uploader = ArtifactUploader('home', 'apps.example.net', token=lambda: 'synthetic',
                                transport=httpx.MockTransport(handle))
    assert uploader(bundle)['revision'] == bundle.revision
    assert len(seen) == 1


@pytest.mark.parametrize('url', ['http://app.test/', 'https://oo.openonion.ai/',
    'https://r-' + 'a' * 52 + '.apps.example.net/changed.html',
    'https://r-' + 'a' * 52 + '.apps.example.net/index.html?token=x'])
def test_invalid_publication_target_cannot_activate(url, default_backend_url):
    bundle = Bundle({'index.html': b'<h1>fixed</h1>'})
    uploader = ArtifactUploader('home', 'apps.example.net', token=lambda: 'synthetic',
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={
            'revision': bundle.revision, 'url': url})))
    with pytest.raises(RuntimeErrorState):
        uploader(bundle)


def test_auth_redirect_is_not_followed_and_failure_is_not_retried(default_backend_url):
    seen = []
    def redirect(request):
        seen.append(request)
        return httpx.Response(307, headers={'Location': 'https://other.test/'})
    uploader = ArtifactUploader('home', 'apps.example.net', token=lambda: 'synthetic',
                                transport=httpx.MockTransport(redirect))
    with pytest.raises(RuntimeErrorState):
        uploader(Bundle({'index.html': b'<h1>fixed</h1>'}))
    assert len(seen) == 1


def test_historical_source_is_read_without_credentials_and_verified_by_manifest(default_backend_url):
    bundle = Bundle({'index.html': b'<h1>fixed</h1>'})
    app = {'revision': bundle.revision, 'url': 'https://r-' + 'a' * 52 + '.apps.example.net/index.html'}
    record = bundle.manifest['files'][0]
    seen = []
    def handle(request):
        seen.append(request)
        assert 'authorization' not in request.headers
        return httpx.Response(200, content=bundle.files['index.html'])
    uploader = ArtifactUploader('home', 'apps.example.net', transport=httpx.MockTransport(handle))
    assert uploader.source(app, record) == bundle.files['index.html']
    uploader.transport = httpx.MockTransport(lambda r: httpx.Response(200, content=b'changed'))
    with pytest.raises(RuntimeErrorState):
        uploader.source(app, record)
    assert len(seen) == 1


@pytest.mark.parametrize('domain', ['openonion.ai', 'apps.openonion.ai', 'connectonion.com', 'example.net:443', 'https://app.test', '*.app.test'])
def test_serving_domain_cannot_share_product_cookies_or_contain_url_syntax(domain):
    with pytest.raises(ValueError):
        ArtifactUploader('home', domain)
