"""Mail is a source like a transcript: oldest first, one cursor, bodies read only for the batch."""

from datetime import datetime, timezone

import pytest

from connectonion.wiki.files import WikiError
from connectonion.wiki.mail import collect_mail


class FakeMail:
    """The two calls an adapter needs: a date-bounded ascending listing and one body."""

    def __init__(self, messages, me="me@example.com"):
        self.messages = sorted(messages, key=lambda m: m["date"])
        self.me = me
        self.bodies_read = []

    def my_addresses(self):
        return {self.me}

    def list_between(self, start, end, max_results):
        rows = [m for m in self.messages if start <= m["date"] < end]
        return [{k: m[k] for k in ("id", "from", "subject", "date")} for m in rows[:max_results]]

    def get_email_body(self, email_id):
        self.bodies_read.append(email_id)
        m = next(m for m in self.messages if m["id"] == email_id)
        return f"From: {m['from']}\nTo: {self.me}\nSubject: {m['subject']}\nDate: {m['date']}\n\n--- Email Body ---\n\n{m['body']}"


def mail(i, date, sender="alice@example.com", subject="Aurora", body="Let's use Markdown."):
    return {"id": f"m{i}", "from": sender, "subject": subject, "date": date, "body": body}


def subscription(**overrides):
    return {"id": "outlook", "kind": "outlook", "since": "2026-09-01T00:00:00+00:00",
            "enabled": True, "consented": True, "exclude_automated": True, **overrides}


def test_oldest_mail_first_with_a_cursor_that_never_repeats(tmp_path):
    client = FakeMail([mail(1, "2026-09-03T10:00:00+00:00"), mail(2, "2026-09-02T09:00:00+00:00"),
                       mail(3, "2026-09-05T08:00:00+00:00", sender="me@example.com", body="Agreed, Markdown.")])
    first = collect_mail(subscription(), {}, 2, 100000, client, now=datetime(2026, 9, 7, tzinfo=timezone.utc))
    assert [i["reference"] for i in first.items] == ["outlook:m2", "outlook:m1"]
    assert all(len(i["source"]) == len("outlook:") + 12 for i in first.items)  # short, readable ids
    assert first.items[0]["role"] == "other" and first.items[0]["speaker"] == "alice@example.com"
    assert "Subject: Aurora" in first.items[0]["text"] and "Markdown" in first.items[0]["text"]
    assert first.progress["cursor"] == "2026-09-03T10:00:00+00:00"
    second = collect_mail(subscription(), first.progress, 2, 100000, client, now=datetime(2026, 9, 7, tzinfo=timezone.utc))
    assert [i["reference"] for i in second.items] == ["outlook:m3"]
    assert second.items[0]["role"] == "user"  # the user's own mail speaks as the user
    assert sorted(client.bodies_read) == ["m1", "m2", "m3"]  # each body read exactly once
    third = collect_mail(subscription(), second.progress, 2, 100000, client, now=datetime(2026, 9, 7, tzinfo=timezone.utc))
    assert third.items == []


def test_same_second_mails_are_not_lost_or_repeated(tmp_path):
    same = "2026-09-02T09:00:00+00:00"
    client = FakeMail([mail(1, same), mail(2, same), mail(3, same)])
    first = collect_mail(subscription(), {}, 2, 100000, client, now=datetime(2026, 9, 7, tzinfo=timezone.utc))
    second = collect_mail(subscription(), first.progress, 2, 100000, client, now=datetime(2026, 9, 7, tzinfo=timezone.utc))
    assert sorted(i["reference"] for i in first.items + second.items) == ["outlook:m1", "outlook:m2", "outlook:m3"]


def test_automated_senders_are_skipped_unless_asked_for():
    client = FakeMail([mail(1, "2026-09-02T09:00:00+00:00", sender="no-reply@airbnb.com", subject="Reservation"),
                       mail(2, "2026-09-02T10:00:00+00:00", sender="notification@github.com"),
                       mail(3, "2026-09-02T11:00:00+00:00", sender="bob@example.com")])
    batch = collect_mail(subscription(), {}, 10, 100000, client, now=datetime(2026, 9, 7, tzinfo=timezone.utc))
    assert [i["reference"] for i in batch.items] == ["outlook:m3"]
    assert client.bodies_read == ["m3"]  # skipped mail is never fetched
    everything = collect_mail(subscription(exclude_automated=False), {}, 10, 100000, client,
                              now=datetime(2026, 9, 7, tzinfo=timezone.utc))
    assert len(everything.items) == 3


def test_lookback_and_body_limit_are_honoured():
    client = FakeMail([mail(1, "2026-08-01T09:00:00+00:00"), mail(2, "2026-09-02T09:00:00+00:00", body="x" * 5000)])
    batch = collect_mail(subscription(), {}, 10, 1500, client, now=datetime(2026, 9, 7, tzinfo=timezone.utc))
    assert [i["reference"] for i in batch.items] == ["outlook:m2"]  # August is before `since`
    assert "truncated" in batch.items[0]["text"] and len(batch.items[0]["text"]) < 1500


def test_unconsented_mail_is_never_listed():
    client = FakeMail([mail(1, "2026-09-02T09:00:00+00:00")])
    with pytest.raises(WikiError):
        collect_mail(subscription(consented=False), {}, 10, 100000, client, now=datetime(2026, 9, 7, tzinfo=timezone.utc))
    assert client.bodies_read == []


def test_quoted_reply_chains_are_cut_off():
    """A reply carries the whole thread below it; the maintainer already saw those mails."""
    from connectonion.wiki.mail import strip_quoted
    body = ("Thanks Alice, Friday works.\n\nBest,\nAaron\n\n"
            "On Tue, 2 Sep 2026 at 09:00, Alice Chen <alice@example.com> wrote:\n> Can we do Friday?\n> ...")
    assert strip_quoted(body).strip() == "Thanks Alice, Friday works.\n\nBest,\nAaron"
    outlook = "Agreed.\n\n________________________________\nFrom: Alice <alice@example.com>\nSent: Tuesday\nSubject: Re: Aurora\n\nCan we?"
    assert strip_quoted(outlook).strip() == "Agreed."
    assert strip_quoted("No quote here.") == "No quote here."
    client = FakeMail([mail(1, "2026-09-02T09:00:00+00:00", body=body)])
    batch = collect_mail(subscription(), {}, 10, 100000, client, now=datetime(2026, 9, 7, tzinfo=timezone.utc))
    assert "Can we do Friday" not in batch.items[0]["text"] and "Friday works" in batch.items[0]["text"]


def test_quotes_are_cut_even_when_the_client_flattened_the_body_to_one_line():
    """Outlook's HTML-to-text turns a mail into one long line, so `^From: … Sent:` and
    `wrote:$` never matched and every reply carried the whole thread beneath it."""
    from connectonion.wiki.mail import strip_quoted
    flat = ("Hi Aaron,I'm connecting you with Helena and Natalie.Thank you,Vern Chan UNSW Global Program Manager"
            "From: Vern Chan <vern.chan@unsw.edu.au>Sent: 10 July 2026 11:56To: xietianle Subject: US Students Dear Aaron,Thank you for your interest")
    assert strip_quoted(flat).endswith("Program Manager") and "Dear Aaron,Thank you for your interest" not in strip_quoted(flat)
    flat2 = "Agreed, Friday works. On Tue, 2 Sep 2026 at 09:00, Alice Chen <alice@example.com> wrote: Can we do Friday?"
    assert strip_quoted(flat2).strip() == "Agreed, Friday works."


def test_signature_link_noise_is_dropped():
    """Booking links and newsletter links in signatures are tokens, not facts."""
    from connectonion.wiki.mail import strip_noise
    body = ("Thanks,Vern Chan Subscribe to Our Fortnightly Newsletter <https://unswfounders.typeform.com/newsletter>"
            "https://outlook.office.com/bookwithme/user/34b2cc480b9d4541a2f837bc47adae32@unsw.edu.au?anonymous&ismsaljsauthenabled&ep=bwmEmailSignature"
            "Book a time <https://outlook.office.com/bookwithme/user/34b2cc480b9d4541a2f837bc47adae32@unsw.edu.au?anonymous>with me")
    cleaned = strip_noise(body)
    assert "bookwithme" not in cleaned and "typeform" not in cleaned
    assert "Vern Chan" in cleaned and "Book a time" in cleaned
    assert strip_noise("see https://example.com/docs for details") == "see https://example.com/docs for details"
