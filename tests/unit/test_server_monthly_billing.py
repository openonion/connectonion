"""Servers billed monthly in advance (openonion/connectonion#2968, oo-api #291/#292).

Nothing is charged at create; each month is charged when it ends; a destroy
refunds the unused part of the month. The CLI shows only the backend's numbers,
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
    "billing": "monthly_prepaid", "term_months": 1, "currency": "USD",
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
    def test_monthly_says_the_first_month_is_charged_now(self, capsys):
        _prompt(MONTHLY, 500.0, "e2-standard-4", 200)
        out = _out(capsys)

        assert "$222.40 / month" in out
        assert "first month charged now, then at the start of each month from credits" in out
        assert "$500.00 → $277.60 after the first month" in out
        assert "200 GB pd-balanced" in out
        assert "for 12 months" not in out

    def test_a_balance_below_one_month_never_reaches_the_prompt(self, capsys):
        answer, confirm = _prompt(MONTHLY, 100.0, "e2-standard-4")

        assert answer is False
        assert not confirm.called
        assert "below the first month ($190.00), which is charged now" in _out(capsys)

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
        assert "$30.00 would be charged now, then $30.00 at the start of each month" in out
        assert "--yes" in out


class TestDiskAndMachines:
    def _new(self, pricing, **kwargs):
        with patch("connectonion.cli.commands.project_cmd_lib.load_api_key", return_value="k"), \
             patch.object(sc, "_ensure_ssh_key", return_value="ssh-ed25519 AAAA x"), \
             patch.object(sc, "_fetch_pricing", return_value=pricing), \
             patch.object(sc, "_forget_host_key"), \
             patch.object(sc, "_wait_until_it_accepts_your_key", return_value=True), \
             patch("requests.post", return_value=_response(200, {
                 "ssh_target": "co@203.0.113.10", "billing": "monthly_prepaid",
                 "charged_usd": 222.4, "usd_month": 222.4,
                 "paid_until": "2026-12-12T09:00:00+00:00",
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

        assert "$222.40 / month — $222.40 charged now, paid until 2026-12-12; renews from credits" in out

    def test_an_unknown_machine_lists_what_is_sold_with_prices(self, servers_file, capsys):
        ok, _ = self._new(MONTHLY, machine_type="huge")

        out = _out(capsys)
        assert ok is False
        assert "e2-highmem-4 $250 / month" in out


RUNNING = {"name": "prod", "billing": "monthly_prepaid", "status": "running",
           "usd_month": 222.4, "period_start": "2026-11-12T09:00:00+00:00",
           "paid_until": "2026-12-12T09:00:00+00:00",
           "next_charge_at": "2026-12-12T09:00:00+00:00", "accrued_usd": 74.13,
           "refund_if_destroyed_usd": 148.27, "unpaid_usd": 0.0,
           "ssh_target": "co@203.0.113.10"}
# A running server in its grace days: the month in progress could not be charged.
IN_GRACE = {**RUNNING, "paid_until": None, "refund_if_destroyed_usd": 0.0, "unpaid_usd": 222.4}


class TestServerLs:
    def _ls(self, billed, balance):
        with patch.object(sc, "_fetch_billed_servers", return_value=billed), \
             patch("connectonion.cli.commands.project_cmd_lib.load_api_key", return_value="k"), \
             patch.object(sc, "_fetch_balance", return_value=balance):
            assert sc.handle_server_list() is True

    def test_paid_until_and_renewal_are_shown(self, servers_file, capsys):
        self._ls([RUNNING], 500.0)
        out = _out(capsys)

        assert "$222.40/mo · paid until 2026-12-12, renews from credits" in out
        assert "covers the next month" in out

    @pytest.fixture(autouse=True)
    def _no_pricing(self):
        with patch.object(sc, "_fetch_pricing", return_value=None):
            yield

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

    def test_a_server_in_grace_shows_when_it_stops_and_is_deleted(self, servers_file, capsys):
        owing = {**RUNNING, "unpaid_usd": 222.4, "period_start": "2026-12-12T09:00:00+00:00"}
        stopped = {**RUNNING, "name": "lab", "status": "suspended", "unpaid_usd": 30.0,
                   "period_start": None, "next_charge_at": None}
        with patch.object(sc, "_fetch_pricing", return_value={
                **MONTHLY, "unpaid": {"warn_days_before": 3, "stop_after_days": 3,
                                      "delete_after_days": 30}}):
            self._ls([owing, stopped], 500.0)
        out = _out(capsys)

        assert "prod owes $222.40: it stops on 2026-12-15 and is deleted on 2027-01-11" in out
        assert "lab owes $30.00 and is stopped; it is deleted 30 days after" in out

    def test_unpaid_since_from_the_backend_sets_the_dates(self, servers_file, capsys):
        owing = {**RUNNING, "unpaid_usd": 444.8, "unpaid_since": "2026-11-12T09:00:00+00:00",
                 "period_start": "2026-12-12T09:00:00+00:00"}
        stopped = {**RUNNING, "name": "lab", "status": "suspended", "unpaid_usd": 30.0,
                   "unpaid_since": "2026-11-01T00:00:00+00:00", "period_start": None}
        with patch.object(sc, "_fetch_pricing", return_value={
                **MONTHLY, "unpaid": {"warn_days_before": 3, "stop_after_days": 3,
                                      "delete_after_days": 30}}):
            self._ls([owing, stopped], 500.0)
        out = _out(capsys)

        assert "prod owes $444.80: it stops on 2026-11-15 and is deleted on 2026-12-12" in out
        assert "lab owes $30.00 and is stopped; it is deleted on 2026-12-01" in out

    def test_a_server_being_deleted_says_so(self):
        going = {**RUNNING, "status": "deleting", "unpaid_usd": 30.0,
                 "unpaid_since": "2026-11-01T00:00:00+00:00"}

        line = sc._grace_line(going, {"stop_after_days": 3, "delete_after_days": 30})

        assert line == "prod owes $30.00 and is being deleted."

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

    def test_the_warning_and_result_say_the_unused_part_is_refunded(self, servers_file, capsys):
        self._destroy(RUNNING, {"billing": "monthly_prepaid", "charged_usd": 74.13,
                                "refunded_usd": 148.27, "refunded": True, "unpaid_usd": 0.0,
                                "credit_note_number": "SRV-2026-11-000124"})
        out = _out(capsys)

        assert "unused part of this month (about $148.27) is refunded to your credits" in out
        assert "$148.27 refunded to your credits for the unused part of this month" in out
        assert "credit note SRV-2026-11-000124" in out
        assert "owe" not in out

    def test_the_days_used_of_a_month_never_paid_are_said_to_be_owed(self, servers_file, capsys):
        self._destroy(IN_GRACE, {"billing": "monthly_prepaid", "charged_usd": 0.0,
                                 "refunded_usd": 0.0, "unpaid_usd": 12.5})
        out = _out(capsys)

        # The open month ($222.40 owed) ended at the destroy: only its days are owed.
        assert "You still owe $12.50 for prod" in out
        assert "refunded" not in out

    def test_a_server_that_owes_is_told_what_stays_owed(self, servers_file, capsys):
        self._destroy(IN_GRACE, {"billing": "monthly_prepaid", "charged_usd": 0.0,
                                 "refunded_usd": 0.0, "unpaid_usd": 12.5})
        out = _out(capsys)

        assert "what is owed ($222.40, plus the days used of a month that was never paid)" in out
        assert "is refunded" not in out

    def test_a_stopped_server_refunds_nothing_and_its_debt_stays(self, servers_file, capsys):
        stopped = {**RUNNING, "status": "suspended", "period_start": None, "paid_until": None,
                   "refund_if_destroyed_usd": 0.0, "unpaid_usd": 30.0}
        self._destroy(stopped, {"billing": "monthly_prepaid", "charged_usd": 0.0,
                                "refunded_usd": 0.0, "unpaid_usd": 0.0})
        out = _out(capsys)

        assert "unused part" not in out
        assert "You still owe $30.00 for prod" in out
        assert "Nothing refunded" not in out

    def test_yes_still_reports_what_is_owed(self, servers_file, capsys):
        owing = {**RUNNING, "unpaid_usd": 30.0}
        with patch("connectonion.cli.commands.project_cmd_lib.load_api_key", return_value="k"), \
             patch.object(sc, "_fetch_billed_servers", return_value=[owing]), \
             patch("requests.delete", return_value=_response(200, {
                 "billing": "monthly_prepaid", "charged_usd": 0.0, "unpaid_usd": 5.0})):
            assert sc.handle_server_destroy("prod", yes=True) is True

        assert "You still owe $35.00 for prod" in _out(capsys)

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
        assert "co server invoice prod 1" in out

    def test_a_row_number_selects_that_invoice(self, capsys):
        ok, calls = self._invoice(name="prod", number="1")

        assert ok is True
        assert calls.call_args.args[0].endswith("/servers/prod/invoices/SRV-2026-12-000123")
        assert "Total USD $222.40" in _out(capsys)

    def test_a_row_past_the_end_is_refused(self, capsys):
        ok, _ = self._invoice(name="prod", number="2")

        assert ok is False
        assert "no invoice #2; it has 1" in _out(capsys)

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

    def test_a_number_selects_that_invoice(self, tmp_path):
        """The invoice email says `co server invoice <name> <number> --pdf <number>.pdf`."""
        from pypdf import PdfReader

        target = tmp_path / "SRV-2026-12-000123.pdf"
        ok, calls = self._invoice(name="prod", number="SRV-2026-12-000123", pdf=str(target))

        assert ok is True
        assert calls.call_args.args[0].endswith("/servers/prod/invoices/SRV-2026-12-000123")
        assert "SRV-2026-12-000123" in PdfReader(target).pages[0].extract_text()

    def test_pdf_alone_writes_the_only_invoice(self, tmp_path):
        target = tmp_path / "only.pdf"
        ok, _ = self._invoice(name="prod", pdf=str(target))

        assert ok is True
        assert target.exists()

    def test_pdf_alone_refuses_to_guess_between_several(self, tmp_path, capsys):
        newer = {**SUMMARY, "number": "SRV-2027-01-000200", "issued_at": "2027-01-12T09:10:00+00:00"}
        target = tmp_path / "which.pdf"
        with patch("connectonion.cli.commands.project_cmd_lib.load_api_key", return_value="k"), \
             patch.object(sc, "_fetch_pricing", return_value=MONTHLY), \
             patch("requests.get", return_value=_response(200, {"invoices": [SUMMARY, newer]})):
            ok = sc.handle_server_invoice(name="prod", pdf=str(target))
        out = _out(capsys)

        assert ok is False
        assert not target.exists()
        assert "co server invoice prod SRV-2027-01-000200 --pdf SRV-2027-01-000200.pdf" in out

    def test_a_backend_error_prints_its_text_not_markup(self, capsys):
        with patch("requests.get", return_value=_response(404, {"detail": "No such invoice"})):
            assert sc._get_json("k", "/api/v1/servers/prod/invoices/X") is None
        out = capsys.readouterr().out

        assert "No such invoice" in out
        assert "[dim]" not in out

    def test_the_old_backend_says_it_issues_none(self, capsys):
        ok, calls = self._invoice(pricing=PREPAID, name="prod")

        assert ok is False
        assert "does not issue server invoices yet" in _out(capsys)
        calls.assert_not_called()

    @pytest.mark.parametrize("args, says", [
        (dict(name="prod", month="2026-13"), "YYYY-MM"),
        (dict(name="prod", pdf="a.pdf", as_json=True), "--pdf or --json"),
        (dict(name="prod", every=True), "--all"),
        (dict(name="Not/A/Server"), "not a server name"),
        (dict(name="prod", number="../x"), "is not an invoice"),
        (dict(name="prod", number="SRV-2026-12-000123", month="2026-12"), "not both"),
        (dict(), "Name a server"),
    ])
    def test_arguments_that_cannot_go_together_are_refused(self, args, says):
        full = dict(name=None, number=None, month=None, every=False, pdf=None, as_json=False)
        assert says in sc.invoice_usage_error(**{**full, **args})

    def test_the_cli_exits_2_on_a_usage_error(self):
        from typer.testing import CliRunner

        from connectonion.cli.main import app

        result = CliRunner().invoke(app, ["server", "invoice", "prod", "--json", "--pdf", "x.pdf"])

        assert result.exit_code == 2
        assert "--pdf or --json" in result.output


class TestInvoicePdf:
    def test_long_lines_wrap_to_the_page(self):
        long = {**INVOICE, "bill_to": {**INVOICE["bill_to"], "address": "A" * 300}}

        lines = sc._pdf_lines(long)

        assert max(len(line) for line in lines) <= sc.PDF_LINE_CHARS
        assert sum(line.count("A") for line in lines) >= 300

    def test_a_name_the_font_cannot_draw_shows_the_account_and_says_so(self, tmp_path):
        from pypdf import PdfReader

        foreign = {**INVOICE, "bill_to": {**INVOICE["bill_to"], "name": "示例科技有限公司"}}
        target = tmp_path / "x.pdf"
        sc._write_invoice_pdf([foreign], target)
        text = PdfReader(target).pages[0].extract_text()

        assert "0xabc" in text
        assert "not shown" in text
        assert "???" not in text

    def test_a_western_name_with_accents_is_kept(self):
        accented = {**INVOICE, "bill_to": {**INVOICE["bill_to"], "name": "Café Ficticio S.A."}}

        assert any("Café Ficticio S.A." in line for line in sc._pdf_lines(accented))


class TestRefusalsOnCreate:
    def test_insufficient_credit_on_the_monthly_backend_says_what_the_balance_is(self, capsys):
        response = _response(402, {"detail": {
            "error": "insufficient_credits", "balance": 20.0, "required": 30.0,
            "shortfall": 10.0, "message": "Your balance must cover [this] server's month."}})

        sc._report_failure(response, monthly=True)
        out = _out(capsys)

        assert "left after your other servers' months $20.00" in out
        assert "this server's month $30.00" in out
        assert "[this]" in out


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

        assert body["billing"] == "monthly_prepaid"

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
