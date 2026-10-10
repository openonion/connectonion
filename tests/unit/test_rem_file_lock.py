"""The cross-process maintenance lock refuses a second holder on every OS."""

import pytest

from connectonion.rem.files import RemError, _file_lock


def test_file_lock_refuses_a_second_holder(tmp_path):
    root = tmp_path / "rem"
    with _file_lock(root, wait=0):
        with pytest.raises(RemError):
            with _file_lock(root, wait=0):
                pass
