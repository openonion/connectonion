"""An image is an upload, and the upload limit applies to it.

`host.yaml` states the rule and where it applies:

    max_file_size: 10          # MB per file (both WebSocket and HTTP)

`validate_files()` enforces it, and both input paths call it — for `files`.
The same handlers take `images` beside `files`:

    def handle_input(storage, prompt, session=None, connection=None,
                     images=None, files=None):
        validate_files(files, config)
        return input_handler(..., images, files)

`images` is a list of base64 strings that goes straight to `agent.input()` and
on to the model. Nothing measures it — not here, not in `input_handler`, and
uvicorn sets no request-size cap of its own. A client that has passed the trust
gate can hand the host a body of any size, and the agent holds it in memory and
forwards it.

That is a smaller hole than it first looks — it needs an authenticated caller,
so the trust gate is doing its job — but "authenticated" includes contact level,
which onboarding with an invite code grants. On the 1-2GB VPS `co server new`
provisions, one large image is enough to end the process, and the operator sees
an agent that died with no explanation.

The fix is not a new limit. It is applying the one that already exists and is
already advertised in `/info` as `max_file_size_mb`.
"""

import base64

import pytest

from connectonion.network.host.config import validate_files, validate_images


CONFIG = {"max_file_size": 1, "max_files_per_request": 3}


def _image_of(mb: float) -> str:
    """A base64 data URL of roughly the given decoded size."""
    return "data:image/png;base64," + base64.b64encode(b"x" * int(mb * 1024 * 1024)).decode()


class TestAnImageTooLarge:

    def test_is_refused(self):
        with pytest.raises(ValueError):
            validate_images([_image_of(2)], CONFIG)

    def test_the_error_says_which_limit(self):
        with pytest.raises(ValueError, match="max_file_size"):
            validate_images([_image_of(2)], CONFIG)

    def test_the_error_says_the_size_in_mb(self):
        with pytest.raises(ValueError, match=r"2\.\d ?MB"):
            validate_images([_image_of(2)], CONFIG)


class TestWhatIsStillAccepted:

    def test_an_image_under_the_limit(self):
        validate_images([_image_of(0.5)], CONFIG)

    def test_no_images_at_all(self):
        validate_images(None, CONFIG)
        validate_images([], CONFIG)

    def test_a_raw_base64_string_without_the_data_url_prefix(self):
        """Clients send both shapes."""
        validate_images([base64.b64encode(b"x" * 1024).decode()], CONFIG)

    def test_something_that_is_not_base64_is_not_a_crash(self):
        """A malformed image is the model's problem to report, not a traceback
        out of the size check."""
        validate_images(["not base64 at all !!!"], CONFIG)


class TestTheCountLimitToo:

    def test_too_many_images_is_refused(self):
        with pytest.raises(ValueError, match="max_files_per_request"):
            validate_images([_image_of(0.1)] * 4, CONFIG)


class TestFilesAreUnaffected:

    def test_a_file_under_the_limit_still_passes(self):
        validate_files([{"name": "a.txt", "data": b"x" * 1024}], CONFIG)

    def test_a_file_over_the_limit_still_fails(self):
        with pytest.raises(ValueError, match="File too large"):
            validate_files([{"name": "big.bin", "data": b"x" * 2 * 1024 * 1024}], CONFIG)
