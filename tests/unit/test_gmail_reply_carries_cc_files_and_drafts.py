"""co gmail reply keeps the thread and still carries a CC, a file, everyone, or waits as a draft (#3260).

The case behind it (names changed): Dana asked in an existing thread for a
corrected signed letter, with Sam copied. `reply` took only a body, so the
answer went out through `draft create` as a new thread the partner received
without the conversation it answered.
"""
import base64
import email
from unittest.mock import MagicMock

from connectonion.useful_tools.gmail import Gmail

ORIGINAL = [
    ("From", "Dana Partner <dana@uni.example.edu>"),
    ("To", "Me <me@mybiz.com>, Lee Office <lee@uni.example.edu>"),
    ("Cc", "Sam Colleague <sam@mybiz.com>"),
    ("Subject", "Signed letter"),
    ("Message-ID", "<letter@uni.example.edu>"),
]


def _gmail(tmp_path, headers=ORIGINAL):
    gmail = Gmail.__new__(Gmail)
    gmail._attachment_root = tmp_path.resolve()
    gmail._allow_external_attachments = False
    service = MagicMock()
    service.users().messages().get().execute.return_value = {
        "threadId": "T1", "payload": {"headers": [{"name": k, "value": v} for k, v in headers]}}
    service.users().messages().send().execute.return_value = {"id": "S1"}
    service.users().drafts().create().execute.return_value = {"id": "D1"}

    def stored_draft():
        created = service.users().drafts().create.call_args.kwargs["body"]["message"]
        updated = service.users().drafts().update.call_args
        raw = updated.kwargs["body"]["message"]["raw"] if updated else created["raw"]
        return {"id": "D1", "message": {"raw": raw, "threadId": created.get("threadId")}}
    service.users().drafts().get().execute.side_effect = lambda *a, **k: stored_draft()
    gmail._get_service = lambda: service
    gmail.my_addresses = lambda: {"me@mybiz.com"}
    gmail._require_draft_write_scope = lambda: None
    service.users().messages().send.reset_mock()  # the setup above called it once
    return gmail, service


def _decoded(body):
    return email.message_from_bytes(base64.urlsafe_b64decode(body["raw"] + "=" * (-len(body["raw"]) % 4)))


def _sent(service):
    body = service.users().messages().send.call_args.kwargs["body"]
    return _decoded(body), body


def _files(message):
    return {part.get_filename(): part.get_payload(decode=True) for part in message.walk() if part.get_filename()}


def test_a_reply_carries_a_cc_and_a_file_and_stays_in_its_thread(tmp_path):
    (tmp_path / "letter-signed.pdf").write_bytes(b"%PDF-1.7 corrected")
    gmail, service = _gmail(tmp_path)

    gmail.reply("M1", "Corrected copy attached.", cc="sam@mybiz.com",
                attachments=[str(tmp_path / "letter-signed.pdf")])

    message, body = _sent(service)
    assert body["threadId"] == "T1"
    assert message["To"] == "Dana Partner <dana@uni.example.edu>"
    assert message["Cc"] == "sam@mybiz.com"
    assert message["Subject"] == "Re: Signed letter"
    assert message["In-Reply-To"] == "<letter@uni.example.edu>"
    assert _files(message) == {"letter-signed.pdf": b"%PDF-1.7 corrected"}


def test_reply_all_keeps_everyone_but_me_once(tmp_path):
    gmail, service = _gmail(tmp_path)

    gmail.reply("M1", "Thanks both", reply_all=True, cc="sam@mybiz.com, new@example.com")

    message, _ = _sent(service)
    assert message["To"] == "Dana Partner <dana@uni.example.edu>"
    assert " ".join(message["Cc"].split()) == (
        "Lee Office <lee@uni.example.edu>, Sam Colleague <sam@mybiz.com>, new@example.com")


def test_reply_all_to_my_own_mail_follows_up_with_its_recipients(tmp_path):
    gmail, service = _gmail(tmp_path, [
        ("From", "Me <me@mybiz.com>"), ("To", "dana@uni.example.edu"),
        ("Cc", "sam@mybiz.com, me@mybiz.com"), ("Subject", "Quote"), ("Message-ID", "<q@mybiz.com>")])

    gmail.reply("M1", "Following up", reply_all=True)

    message, _ = _sent(service)
    assert message["To"] == "dana@uni.example.edu"
    assert message["Cc"] == "sam@mybiz.com"


def test_a_draft_reply_waits_unsent_in_the_thread_and_keeps_it_when_a_file_is_staged(tmp_path):
    (tmp_path / "letter-signed.pdf").write_bytes(b"%PDF-1.7 corrected")
    gmail, service = _gmail(tmp_path)

    saved = gmail.reply("M1", "Corrected copy attached.", cc="sam@mybiz.com", draft=True,
                        attachments=[str(tmp_path / "letter-signed.pdf")])

    service.users().messages().send.assert_not_called()
    created = service.users().drafts().create.call_args.kwargs["body"]["message"]
    assert created["threadId"] == "T1"
    assert _decoded(created)["In-Reply-To"] == "<letter@uni.example.edu>"
    updated = service.users().drafts().update.call_args.kwargs["body"]["message"]
    assert updated["threadId"] == "T1"
    message = _decoded(updated)
    assert (message["To"], message["Cc"], message["Subject"]) == (
        "Dana Partner <dana@uni.example.edu>", "sam@mybiz.com", "Re: Signed letter")
    assert _files(message) == {"letter-signed.pdf": b"%PDF-1.7 corrected"}
    assert saved["id"] == "D1" and [item["name"] for item in saved["attachments"]] == ["letter-signed.pdf"]


def test_a_file_outside_the_project_is_refused_before_anything_is_sent(tmp_path):
    outside = tmp_path.parent / "outside-3260.pdf"
    outside.write_bytes(b"%PDF")
    gmail, service = _gmail(tmp_path / "project")
    (tmp_path / "project").mkdir()

    try:
        gmail.reply("M1", "x", attachments=[str(outside)])
    except PermissionError as error:
        assert "outside the project" in str(error)
    else:
        raise AssertionError("an attachment outside the project was accepted")
    finally:
        outside.unlink()
    service.users().messages().send.assert_not_called()
