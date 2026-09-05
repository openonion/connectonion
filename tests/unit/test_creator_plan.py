"""No provider, daemon, or credential store is involved in local planning."""

import json
from pathlib import Path

import pytest

from connectonion.useful_tools.creator_plan import CreatorError, confirm_plan
from connectonion.useful_tools.tiktok import prepare_post
from connectonion.useful_tools.youtube import prepare_upload


CHANNEL = "UC" + "a" * 22


@pytest.fixture
def clip(tmp_path):
    path = tmp_path / "sample.mp4"
    path.write_bytes(b"synthetic fixture, never uploaded")
    return path


def test_upload_preview_binds_bytes_account_metadata_and_privacy(clip):
    plan = prepare_upload(str(clip), "Demo #Shorts", CHANNEL)
    assert plan["body"]["status"]["privacyStatus"] == "private"
    assert plan["notify_subscribers"] is False
    assert plan["channel_id"] == CHANNEL
    assert plan["file"]["size"] == clip.stat().st_size
    confirm_plan(plan, plan["confirmation"])
    for options in [{"title": "Changed"}, {"privacy": "public"}, {"channel_id": "UC" + "b" * 22}]:
        args = dict(path=str(clip), title="Demo #Shorts", channel_id=CHANNEL)
        args.update(options)
        with pytest.raises(CreatorError, match="confirmation"):
            confirm_plan(prepare_upload(**args), plan["confirmation"])
    clip.write_bytes(b"changed")
    with pytest.raises(CreatorError, match="confirmation"):
        confirm_plan(prepare_upload(str(clip), "Demo #Shorts", CHANNEL), plan["confirmation"])


def test_confirmation_rejects_tampered_plan(clip):
    plan = prepare_upload(str(clip), "Demo", CHANNEL)
    plan["body"]["status"]["privacyStatus"] = "public"
    with pytest.raises(CreatorError):
        confirm_plan(plan, plan["confirmation"])


def test_tiktok_is_local_plan_not_a_draft_or_publish(clip):
    plan = prepare_post(str(clip), "A literal caption #demo", "@creator")
    assert plan["operation"] == "tiktok.post"
    assert plan["caption"] == "A literal caption #demo"
    assert plan["submit_supported"] is False
    assert plan["account"] == "@creator"
    assert "access_token" not in json.dumps(plan)


@pytest.mark.parametrize("title", ["", " " * 5, "x" * 101, "bad<title"])
def test_invalid_youtube_title_is_local_error(clip, title):
    with pytest.raises(CreatorError):
        prepare_upload(str(clip), title, CHANNEL)


def test_missing_non_video_and_empty_files_rejected(tmp_path):
    for name, content in [("missing.mp4", None), ("document.txt", b"text"), ("empty.mp4", b"")]:
        path = tmp_path / name
        if content is not None:
            path.write_bytes(content)
        with pytest.raises(CreatorError):
            prepare_upload(str(path), "Demo", CHANNEL)
