"""Mail is a source worked one correspondent at a time: the listing is scanned forward once
into a per-person queue, and a batch is whole people, oldest first, bodies read only then."""

from datetime import datetime, timezone

import pytest

from connectonion.wiki.files import WikiError
from connectonion.wiki.mail import collect_mail

NOW = datetime(2026, 9, 7, tzinfo=timezone.utc)


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
        return [{k: m[k] for k in ("id", "from", "to", "subject", "date")} for m in rows[:max_results]]

    def get_email_body(self, email_id):
        self.bodies_read.append(email_id)
        m = next(m for m in self.messages if m["id"] == email_id)
        return (f"From: {m['from']}\nTo: {', '.join(m['to'])}\nSubject: {m['subject']}\nDate: {m['date']}\n\n"
                f"--- Email Body ---\n\n{m['body']}")


def mail(i, date, sender="alice@example.com", subject="Aurora", body="Let's use Markdown.", to=("me@example.com",)):
    return {"id": f"m{i}", "from": sender, "to": list(to), "subject": subject, "date": date, "body": body}


def subscription(**overrides):
    return {"id": "outlook", "kind": "outlook", "since": "2026-09-01T00:00:00+00:00",
            "enabled": True, "consented": True, "exclude_automated": True, **overrides}


def references(batch):
    return [item["reference"] for item in batch.items]


def test_mail_is_worked_one_correspondent_at_a_time_oldest_person_first():
    """Alice wrote first, so all of Alice comes before any of Bob, even though Bob's
    mail is older than Alice's second one; Carol does not fit and waits whole."""
    client = FakeMail([mail(1, "2026-09-02T09:00:00+00:00"),
                       mail(2, "2026-09-03T09:00:00+00:00", sender="bob@example.com", subject="Beacon"),
                       mail(3, "2026-09-04T09:00:00+00:00"),
                       mail(4, "2026-09-05T09:00:00+00:00", sender="carol@example.com", subject="Coffee"),
                       mail(5, "2026-09-06T09:00:00+00:00", sender="carol@example.com", subject="Coffee")])
    first = collect_mail(subscription(), {}, 4, 100000, client, now=NOW)
    assert references(first) == ["outlook:m1", "outlook:m3", "outlook:m2"]
    assert [i["correspondent"] for i in first.items] == ["alice@example.com"] * 2 + ["bob@example.com"]
    assert first.items[0]["role"] == "other" and first.items[0]["speaker"] == "alice@example.com"
    assert "Subject: Aurora" in first.items[0]["text"] and "Markdown" in first.items[0]["text"]
    assert all(len(i["source"]) == len("outlook:") + 12 for i in first.items)  # short, readable ids
    assert client.bodies_read == ["m1", "m3", "m2"]  # Carol's bodies are not fetched until her turn
    second = collect_mail(subscription(), first.progress, 4, 100000, client, now=NOW)
    assert references(second) == ["outlook:m4", "outlook:m5"]
    third = collect_mail(subscription(), second.progress, 4, 100000, client, now=NOW)
    assert third.items == [] and sorted(client.bodies_read) == ["m1", "m2", "m3", "m4", "m5"]


def test_the_users_own_mail_is_filed_under_the_person_it_went_to():
    """A sent mail's correspondent is its recipient; Exchange lists the owner's own sent
    mail under a legacy DN rather than an address, and that is still the user."""
    client = FakeMail([mail(1, "2026-09-02T09:00:00+00:00"),
                       mail(2, "2026-09-02T10:00:00+00:00", sender="me@example.com", to=("alice@example.com",),
                            body="Agreed, Markdown."),
                       mail(3, "2026-09-02T11:00:00+00:00", sender="/o=first organization/cn=recipients/cn=0003",
                            to=("bob@example.com", "me@example.com"), subject="Beacon", body="Sent from Outlook.")])
    batch = collect_mail(subscription(), {}, 10, 100000, client, now=NOW)
    by_id = {i["reference"]: i for i in batch.items}
    assert by_id["outlook:m2"]["role"] == "user" and by_id["outlook:m2"]["correspondent"] == "alice@example.com"
    assert by_id["outlook:m3"]["role"] == "user" and by_id["outlook:m3"]["correspondent"] == "bob@example.com"
    assert references(batch) == ["outlook:m1", "outlook:m2", "outlook:m3"]


def test_a_correspondent_larger_than_a_batch_is_sliced_oldest_first():
    """A person is split across batches only when they alone are more than a batch;
    otherwise the batch closes and they get the next one whole."""
    client = FakeMail([mail(i, f"2026-09-0{i}T09:00:00+00:00") for i in range(1, 6)]
                      + [mail(9, "2026-09-01T08:00:00+00:00", sender="bob@example.com")])
    first = collect_mail(subscription(), {}, 2, 100000, client, now=NOW)
    assert references(first) == ["outlook:m9"]  # Bob is whole; Alice does not fit beside him
    second = collect_mail(subscription(), first.progress, 2, 100000, client, now=NOW)
    assert references(second) == ["outlook:m1", "outlook:m2"]  # Alice alone exceeds a batch: oldest slice
    third = collect_mail(subscription(), second.progress, 2, 100000, client, now=NOW)
    assert references(third) == ["outlook:m3", "outlook:m4"]
    fourth = collect_mail(subscription(), third.progress, 2, 100000, client, now=NOW)
    assert references(fourth) == ["outlook:m5"]


def test_new_mail_after_a_sync_joins_its_correspondent_next_time():
    client = FakeMail([mail(1, "2026-09-02T09:00:00+00:00")])
    first = collect_mail(subscription(), {}, 10, 100000, client, now=datetime(2026, 9, 3, tzinfo=timezone.utc))
    assert references(first) == ["outlook:m1"]
    client.messages.append(mail(2, "2026-09-04T09:00:00+00:00", body="Second thoughts."))
    client.messages.append(mail(3, "2026-09-04T10:00:00+00:00", sender="bob@example.com"))
    second = collect_mail(subscription(), first.progress, 10, 100000, client, now=NOW)
    assert references(second) == ["outlook:m2", "outlook:m3"]
    assert second.items[0]["correspondent"] == "alice@example.com"
    assert sorted(client.bodies_read) == ["m1", "m2", "m3"]  # nothing is fetched twice


def test_same_second_mails_are_not_lost_or_repeated():
    same = "2026-09-02T09:00:00+00:00"
    client = FakeMail([mail(1, same), mail(2, same), mail(3, same)])
    first = collect_mail(subscription(), {}, 2, 100000, client, now=NOW)
    second = collect_mail(subscription(), first.progress, 2, 100000, client, now=NOW)
    assert sorted(references(first) + references(second)) == ["outlook:m1", "outlook:m2", "outlook:m3"]


def test_automated_senders_are_skipped_unless_asked_for():
    client = FakeMail([mail(1, "2026-09-02T09:00:00+00:00", sender="no-reply@airbnb.com", subject="Reservation"),
                       mail(2, "2026-09-02T10:00:00+00:00", sender="notification@github.com"),
                       mail(3, "2026-09-02T11:00:00+00:00", sender="bob@example.com"),
                       mail(4, "2026-09-02T12:00:00+00:00", sender="automated@airbnb.com"),
                       mail(5, "2026-09-02T13:00:00+00:00", sender="weshine@substack.com"),
                       mail(6, "2026-09-02T14:00:00+00:00", sender="sfvibe@mail.beehiiv.com")])
    batch = collect_mail(subscription(), {}, 10, 100000, client, now=NOW)
    assert references(batch) == ["outlook:m3"]
    assert client.bodies_read == ["m3"]  # skipped mail is never fetched
    everything = collect_mail(subscription(exclude_automated=False), {}, 10, 100000, client, now=NOW)
    assert len(everything.items) == 6


def test_lookback_and_body_limit_are_honoured():
    client = FakeMail([mail(1, "2026-08-01T09:00:00+00:00"), mail(2, "2026-09-02T09:00:00+00:00", body="x" * 5000)])
    batch = collect_mail(subscription(), {}, 10, 1500, client, now=NOW)
    assert references(batch) == ["outlook:m2"]  # August is before `since`
    assert "truncated" in batch.items[0]["text"] and len(batch.items[0]["text"]) < 1500


def test_unconsented_mail_is_never_listed():
    client = FakeMail([mail(1, "2026-09-02T09:00:00+00:00")])
    with pytest.raises(WikiError):
        collect_mail(subscription(consented=False), {}, 10, 100000, client, now=NOW)
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
    batch = collect_mail(subscription(), {}, 10, 100000, client, now=NOW)
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


def test_one_correspondent_can_be_pulled_on_its_own():
    """"Sync my mail with Vern" is the most natural thing to ask for and there was no
    way to say it. The queue is already per person, so the ask is a filter on whose
    turn it is -- and everyone else keeps their place for the next pass."""
    client = FakeMail([mail(1, "2026-09-02T09:00:00+00:00"),
                       mail(2, "2026-09-03T09:00:00+00:00", sender="bob@example.com", subject="Beacon"),
                       mail(3, "2026-09-04T09:00:00+00:00")])
    batch = collect_mail(subscription(), {}, 10, 100000, client, now=NOW, only="alice@example.com")
    assert references(batch) == ["outlook:m1", "outlook:m3"]
    assert client.bodies_read == ["m1", "m3"]  # Bob's body is never fetched
    rest = collect_mail(subscription(), batch.progress, 10, 100000, client, now=NOW)
    assert references(rest) == ["outlook:m2"]  # Bob was not consumed, only passed over


def test_a_correspondent_can_be_named_by_part_of_their_address():
    client = FakeMail([mail(1, "2026-09-02T09:00:00+00:00", sender="Vern Chan <vern.chan@unsw.edu.au>")])
    batch = collect_mail(subscription(), {}, 10, 100000, client, now=NOW, only="vern")
    assert references(batch) == ["outlook:m1"]
    assert collect_mail(subscription(), {}, 10, 100000, client, now=NOW, only="nobody").items == []
