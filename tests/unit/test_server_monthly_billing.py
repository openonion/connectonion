"""Servers billed monthly in arrears (openonion/connectonion#2968, oo-api #291/#292).

Nothing is charged at create; each month is charged when it ends; a destroy
charges the used part of the month. The CLI shows only the backend's numbers,
and against the backend still in production (12 months charged up front, no
`billing` key) it must keep telling that truth instead: never "nothing is
charged now" while a year is about to be charged.
"""

import json
import sys
from unittest.mock import Mock, patch

import pytest

from connectonion.cli.commands import server_commands as sc


MONTHLY = {
    "billing": "monthly_in_arrears", "term_months": 1, "currency": "USD",
    "regions": ["australia-southeast1"], "default_region": "australia-southeast1",
    "default": "e2-small",
    "machine_types": {
        "e2-small": {"usd_month": 30.0, "memory_gb": 2, "description": "2 GB", "usd_12mo": 0.0},
        "e2-standard-4": {"usd_month": 190.0, "memory_gb": 16, "description": "16 GB", "usd_12mo": 0.0},
        "e2-highmem-4": {"usd_month": 250.0, "memory_gb": 32, "description": "32 GB", "usd_12mo": 0.0},
    },
    "disk": {"type": "pd-balanced", "sizes_gb": [20, 100, 200, 500], "default_gb": 20,
             "included_gb": 20, "usd_per_gb_month": 0.18},
    "minimum_balance_months": 1,
}

PREPAID = {
    "term_months": 12, "regions": ["australia-southeast1"],
    "default_region": "australia-southeast1", "default": "e2-small",
    "machine_types": {"e2-small": {"usd_month": 30.0, "usd_12mo": 360.0, "description": "2 GB"}},
}

INVOICE = {
    "number": "SRV-2026-12-000123", "type": "invoice", "status": "paid",
    "issued_at": "2026-12-12T09:10:00+00:00", "currency": "USD",
    "issuer": {"name": "Example Issuer Pty Ltd", "abn": "00 000 000 000",
               "address": "1 Example Street, Sydney NSW 2000", "email": "billing@example.com"},
    "bill_to": {"agent_address": "0xabc", "name": "Fictional Widgets Pty Ltd",
                "address": None, "tax_id": None},
    "server": {"name": "prod", "machine_type": "e2-standard-4", "disk_gb": 200},
    "period": {"start": "2026-11-12T09:00:00+00:00", "end": "2026-12-12T09:00:00+00:00",
               "days": 30, "full_month": True},
    "lines": [
        {"description": "e2-standard-4 server", "months": 1, "unit_usd_month": 190.0, "amount_usd": 190.0},
        {"description": "200 GB pd-balanced disk: 180 GB beyond the 20 GB included", "months": 1,
         "unit_usd_month": 32.4, "amount_usd": 32.4},
    ],
    "total_usd": 222.4,
    "gst_treatment": "No GST itemised. Paid from prepaid ConnectOnion credits.",
    "payment": {"method": "credits", "payment_id": 1, "date": "2026-12-12",
                "note": "Paid from ConnectOnion credits on 2026-12-12, payment id 1"},
}

SUMMARY = {"number": INVOICE["number"], "type": "invoice", "status": "paid",
           "issued_at": INVOICE["issued_at"], "period_start": INVOICE["period"]["start"],
           "period_end": INVOICE["period"]["end"], "amount_usd": 222.4}


@pytest.fixture
def servers_file(tmp_path, monkeypatch):
    path = tmp_path / "servers.yaml"
    monkeypatch.setattr(sc, "SERVERS_FILE", path)
    return path


def _response(status, payload=None):
    payload = payload or {}
    return Mock(status_code=status, content=b"{}", text=json.dumps(payload),
                json=Mock(return_value=payload))


def _out(capsys):
    return " ".join(capsys.readouterr().out.split())


def _prompt(pricing, balance, machine="e2-small", disk_gb=None, tty=True):
    with patch.object(sys.stdin, "isatty", return_value=tty), \
         patch("questionary.confirm") as confirm:
        confirm.return_value.ask.return_value = True
        answer = sc._confirm("prod", machine, "australia-southeast1", pricing, balance, disk_gb)
    return answer, confirm


class TestTheConfirmScreen:
    def test_monthly_says_nothing_is_charged_now(self, capsys):
        _prompt(MONTHLY, 500.0, "e2-standard-4", 200)
        out = _out(capsys)

        assert "$222.40 / month" in out
        assert "charged at the end of each month from credits; nothing is charged now" in out
        assert "200 GB pd-balanced" in out
        assert "for 12 months" not in out

    def test_a_balance_below_one_month_never_reaches_the_prompt(self, capsys):
        answer, confirm = _prompt(MONTHLY, 100.0, "e2-standard-4")

        assert answer is False
        assert not confirm.called
        assert "below one month ($190.00)" in _out(capsys)

    def test_the_old_backend_still_says_a_year_is_charged_now(self, capsys):
        """Production today charges 12 months at create. Saying otherwise
        there is the one lie this change could tell."""
        _prompt(PREPAID, 500.0)
        out = _out(capsys)

        assert "$360.00 for 12 months, charged now" in out
        assert "nothing is charged now" not in out

    def test_without_a_terminal_monthly_names_the_monthly_amount(self, capsys):
        answer, _ = _prompt(MONTHLY, 500.0, tty=False)
        out = _out(capsys)

        assert answer is False
        assert "Nothing would be charged now; $30.00 at the end of each month" in out
        assert "--yes" in out


class TestDiskAndMachines:
    def _new(self, pricing, **kwargs):
        with patch("connectonion.cli.commands.project_cmd_lib.load_api_key", return_value="k"), \
             patch.object(sc, "_ensure_ssh_key", return_value="ssh-ed25519 AAAA x"), \
             patch.object(sc, "_fetch_pricing", return_value=pricing), \
             patch.object(sc, "_forget_host_key"), \
             patch.object(sc, "_wait_until_it_accepts_your_key", return_value=True), \
             patch("requests.post", return_value=_response(200, {
                 "ssh_target": "co@203.0.113.10", "billing": "monthly_in_arrears",
                 "charged_usd": 0.0, "usd_month": 222.4,
                 "next_charge_at": "2026-12-12T09:00:00+00:00"})) as post:
            ok = sc.handle_server_new("prod", yes=True, **kwargs)
        return ok, post

    def test_the_disk_size_is_sent(self, servers_file):
        ok, post = self._new(MONTHLY, machine_type="e2-highmem-4", disk_gb=200)

        assert ok is True
        assert post.call_args.kwargs["json"]["disk_gb"] == 200
        assert post.call_args.kwargs["json"]["machine_type"] == "e2-highmem-4"

    def test_a_size_the_backend_does_not_sell_is_refused_before_create(self, servers_file, capsys):
        ok, post = self._new(MONTHLY, disk_gb=50)

        assert ok is False
        post.assert_not_called()
        assert "20, 100, 200, 500" in _out(capsys)

    def test_the_old_backend_refuses_disk_rather_than_ignoring_it(self, servers_file, capsys):
        ok, post = self._new(PREPAID, disk_gb=200)

        assert ok is False
        post.assert_not_called()
        assert "does not offer --disk" in _out(capsys)

    def test_after_create_the_backends_price_and_first_charge_are_shown(self, servers_file, capsys):
        self._new(MONTHLY, machine_type="e2-standard-4", disk_gb=200)
        out = _out(capsys)

        assert "$222.40 / month — first charge 2026-12-12; $0.00 charged now" in out

    def test_an_unknown_machine_lists_what_is_sold_with_prices(self, servers_file, capsys):
        ok, _ = self._new(MONTHLY, machine_type="huge")

        out = _out(capsys)
        assert ok is False
        assert "e2-highmem-4 $250 / month" in out


RUNNING = {"name": "prod", "billing": "monthly_in_arrears", "status": "running",
           "usd_month": 222.4, "next_charge_at": "2026-12-12T09:00:00+00:00",
           "accrued_usd": 74.13, "unpaid_usd": 0.0, "ssh_target": "co@203.0.113.10"}


class TestServerLs:
    def _ls(self, billed, balance):
        with patch.object(sc, "_fetch_billed_servers", return_value=billed), \
             patch("connectonion.cli.commands.project_cmd_lib.load_api_key", return_value="k"), \
             patch.object(sc, "_fetch_balance", return_value=balance):
            assert sc.handle_server_list() is True

    def test_next_charge_and_accrued_are_shown(self, servers_file, capsys):
        self._ls([RUNNING], 500.0)
        out = _out(capsys)

        assert "$222.40/mo · next charge 2026-12-12 · $74.13 so far" in out
        assert "covers the next month" in out

    def test_unpaid_and_suspended_are_named(self, servers_file, capsys):
        owing = {**RUNNING, "unpaid_usd": 30.0}
        stopped = {**RUNNING, "name": "lab", "status": "suspended", "next_charge_at": None}
        going = {**RUNNING, "name": "old", "status": "deleting"}
        self._ls([owing, stopped, going], 500.0)
        out = _out(capsys)

        assert "$30.00 unpaid" in out
        assert "suspended for non-payment" in out
        assert "being deleted" in out

    def test_a_balance_short_of_the_next_month_warns(self, servers_file, capsys):
        self._ls([RUNNING], 100.0)
        out = _out(capsys)

        assert "does not cover the next month" in out
        assert "before 2026-12-12" in out

    def test_a_server_on_the_old_term_shows_its_prepaid_date(self, servers_file, capsys):
        self._ls([{"name": "legacy", "billing": "prepaid_12_months",
                   "prepaid_until": "2027-07-31T00:00:00+00:00"}], 500.0)

        assert "prepaid until 2027-07-31" in _out(capsys)

    def test_the_old_backend_shows_the_expiry_and_no_balance_claim(self, servers_file, capsys):
        with patch.object(sc, "_fetch_balance") as balance:
            with patch.object(sc, "_fetch_billed_servers", return_value=[
                    {"name": "prod", "expires_at": "2027-07-31T00:00:00+00:00"}]):
                sc.handle_server_list()

        out = _out(capsys)
        assert "until 2027-07-31" in out
        assert "covers" not in out
        balance.assert_not_called()


class TestServerDestroy:
    def _destroy(self, record, result):
        with patch("connectonion.cli.commands.project_cmd_lib.load_api_key", return_value="k"), \
             patch.object(sc, "_fetch_billed_servers", return_value=[record] if record else None), \
             patch("questionary.text") as text, \
             patch("requests.delete", return_value=_response(200, result)):
            text.return_value.ask.return_value = "prod"
            return sc.handle_server_destroy("prod")

    def test_the_warning_says_the_used_part_is_charged(self, servers_file, capsys):
        self._destroy(RUNNING, {"billing": "monthly_in_arrears", "charged_usd": 111.2,
                                "unpaid_usd": 0.0, "invoice_number": "SRV-2026-11-000124"})
        out = _out(capsys)

        assert "used part of this month (about $74.13) is charged now" in out
        assert "$111.20 charged for the used part of this month" in out
        assert "SRV-2026-11-000124" in out
        assert "refunded" not in out

    def test_an_amount_the_balance_could_not_pay_is_said_to_be_owed(self, servers_file, capsys):
        self._destroy(RUNNING, {"billing": "monthly_in_arrears", "charged_usd": 0.0,
                                "unpaid_usd": 111.2, "invoice_number": None})

        assert "$111.20 for the used part of this month could not be paid" in _out(capsys)

    def test_the_old_backend_still_reports_its_refund(self, servers_file, capsys):
        self._destroy({"name": "prod", "expires_at": "2027-07-31"},
                      {"refunded_usd": 150.41, "charged_usd": 360.0})
        out = _out(capsys)

        assert "unused part of the term is refunded" in out
        assert "$150.41 of $360.00 refunded" in out

    def test_an_unknown_record_promises_neither_charge_nor_refund(self, servers_file, capsys):
        self._destroy(None, {"refunded_usd": 0.0})

        assert "settled now and shown below" in _out(capsys)


class TestServerInvoice:
    def _invoice(self, pricing=MONTHLY, **kwargs):
        def get(url, **_):
            path = url.split("/api/v1")[1]
            if path == "/servers/prod/invoices":
                return _response(200, {"invoices": [SUMMARY]})
            if path == f"/servers/prod/invoices/{INVOICE['number']}":
                return _response(200, INVOICE)
            if path == "/invoices":
                return _response(200, {"month": "2026-12", "invoices": [INVOICE]})
            return _response(404, {"detail": "Not Found"})

        with patch("connectonion.cli.commands.project_cmd_lib.load_api_key", return_value="k"), \
             patch.object(sc, "_fetch_pricing", return_value=pricing), \
             patch("requests.get", side_effect=get) as calls:
            return sc.handle_server_invoice(**kwargs), calls

    def test_without_a_month_it_lists(self, capsys):
        ok, _ = self._invoice(name="prod")
        out = _out(capsys)

        assert ok is True
        assert "SRV-2026-12-000123" in out
        assert "co server invoice prod --month 2026-12" in out

    def test_a_month_prints_the_backends_total_and_lines(self, capsys):
        ok, _ = self._invoice(name="prod", month="2026-12")
        out = _out(capsys)

        assert ok is True
        assert "Total USD $222.40" in out
        assert "180 GB beyond the 20 GB included" in out
        assert "Fictional Widgets Pty Ltd" in out

    def test_a_month_with_no_invoice_says_so(self, capsys):
        ok, _ = self._invoice(name="prod", month="2026-10")

        assert ok is True
        assert "No invoices for prod issued in 2026-10" in _out(capsys)

    def test_all_reads_the_accounts_month(self, capsys):
        ok, calls = self._invoice(every=True, month="2026-12")

        assert ok is True
        assert calls.call_args.kwargs["params"] == {"month": "2026-12"}

    def test_json_is_the_backends_document(self, capsys):
        self._invoice(name="prod", month="2026-12", as_json=True)

        assert json.loads(capsys.readouterr().out) == {"invoices": [INVOICE]}

    def test_the_pdf_carries_the_backends_total(self, tmp_path):
        from pypdf import PdfReader

        target = tmp_path / "prod.pdf"
        ok, _ = self._invoice(name="prod", month="2026-12", pdf=str(target))

        text = PdfReader(target).pages[0].extract_text()
        assert ok is True
        assert "SRV-2026-12-000123" in text
        assert "$222.40" in text

    def test_pdf_alone_writes_the_latest_invoice(self, tmp_path):
        """The invoice email says `co server invoice <name> --pdf <number>.pdf`."""
        from pypdf import PdfReader

        target = tmp_path / "SRV-2026-12-000123.pdf"
        ok, _ = self._invoice(name="prod", pdf=str(target))

        assert ok is True
        assert len(PdfReader(target).pages) == 1

    def test_the_old_backend_says_it_issues_none(self, capsys):
        ok, calls = self._invoice(pricing=PREPAID, name="prod")

        assert ok is False
        assert "does not issue server invoices yet" in _out(capsys)
        calls.assert_not_called()

    def test_a_malformed_month_is_refused_locally(self, capsys):
        ok, calls = self._invoice(name="prod", month="2026-13")

        assert ok is False
        calls.assert_not_called()


class TestTheCreateRequest:
    def _post(self, pricing, response):
        with patch("connectonion.cli.commands.project_cmd_lib.load_api_key", return_value="k"), \
             patch.object(sc, "_ensure_ssh_key", return_value="ssh-ed25519 AAAA x"), \
             patch.object(sc, "_fetch_pricing", return_value=pricing), \
             patch("requests.post", return_value=response) as post:
            ok = sc.handle_server_new("prod", yes=True)
        return ok, post.call_args.kwargs["json"]

    def test_the_monthly_backend_gets_the_billing_acknowledgement(self, servers_file):
        _, body = self._post(MONTHLY, _response(400, {"detail": "x"}))

        assert body["billing"] == "monthly_in_arrears"

    def test_the_old_backend_gets_nothing_new(self, servers_file):
        _, body = self._post(PREPAID, _response(400, {"detail": "x"}))

        assert "billing" not in body
        assert "disk_gb" not in body

    def test_unpaid_months_block_a_create_with_the_amount(self, servers_file, capsys):
        message = "Your servers owe $30.00; top up before creating another."
        ok, _ = self._post(MONTHLY, _response(402, {"detail": {
            "error": "unpaid_server_months", "unpaid_usd": 30.0, "message": message}}))
        out = _out(capsys)

        assert ok is False
        assert "owe $30.00" in out
        assert message in out
        assert "Nothing was created or charged" in out

    def test_an_unknown_refusal_is_shown_in_the_backends_words(self, servers_file, capsys):
        message = "Something new the backend refuses."
        ok, _ = self._post(MONTHLY, _response(409, {"detail": {"error": "x", "message": message}}))

        assert ok is False
        assert message in _out(capsys)
