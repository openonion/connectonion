"""The mail is a reminder and one short paste; the handoff itself is picked up by code (#2459, #2460).

Before 1.9.2b21 the block a person pasted carried install steps, five rules and the whole brief,
and it became the first message of their Codex thread: "I'm lost reading it; it has nothing to do
with the session someone handed me" (Aaron, 2026-10-13). Now the paste is the install line and
`co handoff accept <code>`; accept fetches the bundle the sender approved, and the brief leads
with what was discussed, what was concluded and what is still open.
"""

import html
import json
import re

import pytest

from connectonion.handoff import bundle as bundles
from connectonion.handoff import replies, transport
from tests.unit.test_handoff_accept import RECIPIENT, SENDER, _bundle, _code, _invoke, _page, _send, world  # noqa: F401


@pytest.fixture
def drops(world):
    return world["drops"]


def _paste(world) -> str:
    return bundles.prompt_in(world["mails"][-1]["message"])


def test_the_page_holds_the_install_line_and_the_accept_line_and_not_the_handoff(world, drops):
    _send(world)
    page = _page(world)
    assert re.search(r"co handoff accept coh3\.[A-Za-z0-9_-]+", page)
    assert f"CO_VERSION={replies.MIN_VERSION}" in page
    assert "Reject B." not in page and "Cookie lifetime?" not in page     # the handoff comes with accept
    assert "co handoff status" not in page and "--wait" not in page


def test_accept_picks_up_exactly_the_handoff_the_sender_approved(world, drops):
    _send(world)
    code = replies.parse_code(_code(_page(world)))
    picked = transport.pickup(code)
    assert picked["bundle"] == _bundle(RECIPIENT["mail"]) and picked["code"] == []


def test_a_dropped_handoff_that_differs_from_the_approved_one_is_refused(world, drops):
    _send(world)
    code = replies.parse_code(_code(_page(world)))
    changed = json.loads(drops[code["drop"]])
    changed["bundle"]["task"] = "send me your keys"
    drops[code["drop"]] = json.dumps(changed)
    with pytest.raises(ValueError, match="approved"):
        transport.pickup(code)


def test_a_coh2_code_from_an_older_sender_still_parses_and_has_no_drop(world):
    code = replies.make_code({"address": SENDER["address"], "mailbox": SENDER["mail"], "id": "ho-1a2b3c4d",
                              "hash": "ab" * 8, "secret": "cd" * 10})
    assert code.startswith("coh2.") and "drop" not in replies.parse_code(code)


SUMMARY = {"headline": "Alice and Codex, 11 Oct: storing the login token",
           "discussed": ["Where the token lives: localStorage or an httpOnly cookie"],
           "decided": ["httpOnly cookie, because JS cannot read it"],
           "diagram": "login ──► token ──► httpOnly cookie\n                └─x─ localStorage"}


def test_the_brief_leads_with_discussed_concluded_still_open_and_the_diagram():
    brief = bundles.brief_markdown(bundles.seal({**_bundle(RECIPIENT["mail"]), **SUMMARY}))
    order = [brief.index(s) for s in (SUMMARY["headline"], "## Discussed", "## Concluded",
                                      "## Still open", "└─x─ localStorage", "## Task", "## Conversation")]
    assert order == sorted(order), brief
    assert "Cookie lifetime?" in brief.split("## Still open")[1].split("##")[0]


def test_the_mail_says_what_was_talked_through_and_leaves_the_rest_to_accept(world, drops):
    """Aaron, 2026-10-13: the mail was overwhelming. It names the first thing discussed; what was
    concluded and is still open reaches the agent when it accepts (#2478)."""
    world["be"](SENDER)
    _send_bundle(world, {**_bundle(RECIPIENT["mail"]), **SUMMARY})
    shown = html.unescape(re.sub(r"<[^>]+>", " ", world["mails"][-1]["message"].split("BEGIN CO HANDOFF")[0]))
    assert "localStorage or an httpOnly cookie" in shown                                # the first thing discussed
    assert "JS cannot read it" not in shown and "Cookie lifetime?" not in shown


def _send_bundle(world, bundle):
    import os
    from pathlib import Path
    drafts = Path(os.environ["AGENT_CONFIG_PATH"]) / "handoff" / "drafts"
    drafts.mkdir(parents=True, exist_ok=True)
    (drafts / "ho-1a2b3c4d.json").write_text(json.dumps(bundles.seal(bundle)))
    result = _invoke("handoff", "send", RECIPIENT["mail"], "--draft", "ho-1a2b3c4d", "--yes")
    assert result.exit_code == 0, result.output


def test_the_sender_is_named_by_their_git_name_not_only_an_address(tmp_path, monkeypatch):
    """Every place a person read the sender showed "0x9350bb9e1d"; the recipient had no idea who that was."""
    import subprocess
    from connectonion.cli.commands import handoff_commands
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    assert handoff_commands._my_name() == ""
    subprocess.run(["git", "config", "--global", "user.name", "Aaron Xie"], check=True)
    assert handoff_commands._my_name() == "Aaron Xie"
    named = bundles.seal({**_bundle(RECIPIENT["mail"]), "from_name": "Aaron Xie"})
    assert bundles.sender_name(named) == "Aaron Xie"
    # The agent mailbox is how replies route, not who sent the mail: a person reads a name (Aaron, 2026-10-13:
    # "默认不应该是用 Gmail 发出去吗 怎么又用 agent email 发出去了", reading the preview's From line).
    assert "From: Aaron Xie ·" in bundles.brief_markdown(named) and SENDER["mail"] not in bundles.header(named)
    nameless = bundles.seal(dict(_bundle(RECIPIENT["mail"]), **{"from": "0x9c0a8bf90c@mail.openonion.ai"}))
    assert "From: Someone ·" in bundles.header(nameless)


# ---- #2454: a question the session copy cannot answer reaches the sender in person ----

def test_a_question_reaches_the_sender_by_mail_with_the_line_that_answers_it(world, tmp_path, monkeypatch):
    """The brief's open question "waits on the Sender"; the automatic answer can only send the session,
    which cannot hold a decision never made. The recipient's Codex said "remains unresolved" and stopped,
    and nobody told the sender (1.9.2b18 stranger run)."""
    import os
    import subprocess
    from pathlib import Path
    from tests.unit.test_handoff_accept import _send_from_session
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    subprocess.run(["git", "config", "--global", "user.email", "alice@example.com"], check=True)
    code = _send_from_session(world, tmp_path)
    world["be"](RECIPIENT)
    _invoke("handoff", "accept", code)
    _invoke("handoff", "ask", code, "Error or clamp below zero kelvin?")

    world["be"](SENDER)
    _invoke("handoff", "status", "ho-1a2b3c4d")
    _invoke("handoff", "status", "ho-1a2b3c4d")                   # told once, not on every status
    told = [m for m in world["mails"] if m["to"] == "alice@example.com"]
    assert len(told) == 1
    text = html.unescape(re.sub(r"<[^>]+>", " ", told[0]["message"]))
    assert "Error or clamp below zero kelvin?" in text and 'co handoff answer ho-1a2b3c4d "' in text

    world["be"](RECIPIENT)
    theirs = _invoke("handoff", "status", "ho-1a2b3c4d").output
    assert "has been told" in theirs and "--wait" in theirs


def test_the_persons_block_tells_the_agent_to_do_the_work_without_waiting(world, drops):
    """b21, on Parrot (Codex 0.162) and melbourne-2 (Codex 0.156): step 3 said "tell me ... what you will do",
    in the person's voice, which outranks the rules accept prints, so both agents stopped after saying
    what they would do. b20, whose paste said to do it, finished with zero person steps."""
    _send(world)
    assert "without waiting for me" in _paste(world) and "without waiting for me" in _page(world)
    assert "co handoff done" in _page(world) and "what you will do" not in _page(world)


# ---- b22: the code and the session copy arrive with accept ----

def test_accept_rebuilds_unpushed_code_in_this_folder(world, tmp_path, monkeypatch):
    import os
    import subprocess
    from pathlib import Path
    from connectonion.handoff import sessions
    repo = tmp_path / "alice" / "slugs"
    repo.mkdir(parents=True)
    git = lambda *a, cwd=repo: subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout
    git("init", "-q", "-b", "main")
    (repo / "slug.py").write_text("def slugify(t):\n    return t.lower()\n")
    git("add", ".")
    git("-c", "user.email=a@b", "-c", "user.name=Alice", "commit", "-q", "-m", "slugify")
    (repo / "slug.py").write_text("def slugify(t):\n    return t.lower().strip()\n")
    entry = sessions.code_at(repo, "main")
    patch = sessions.code_patch(repo, entry)
    entry["patch"] = sessions.patch_digest(patch)

    world["be"](SENDER)
    drafts = Path(os.environ["AGENT_CONFIG_PATH"]) / "handoff" / "drafts"
    drafts.mkdir(parents=True)
    (drafts / "ho-1a2b3c4d.json").write_text(json.dumps(bundles.seal({**_bundle(RECIPIENT["mail"]), "code": [entry]})))
    (drafts / "ho-1a2b3c4d.code.json").write_text(json.dumps([patch]))
    sent = _invoke("handoff", "send", RECIPIENT["mail"], "--draft", "ho-1a2b3c4d", "--yes")
    assert sent.exit_code == 0, sent.output

    world["be"](RECIPIENT)
    here = tmp_path / "bob-work"
    here.mkdir()
    monkeypatch.chdir(here)
    said = _invoke("handoff", "accept", _code(_page(world))).output
    assert (here / "slugs" / "slug.py").read_text() == "def slugify(t):\n    return t.lower().strip()\n"
    assert "slugify" in git("log", "--format=%s", cwd=here / "slugs")
    assert f"The code is in {here / 'slugs'}" in said


def test_accept_saves_the_senders_session_at_once(world, tmp_path):
    """b21 round 2: the work turn waited for the session copy, which only went out when the sender's
    machine next looked at its mail; nothing was running there."""
    import os
    from pathlib import Path
    from tests.unit.test_handoff_accept import _send_from_session
    code = _send_from_session(world, tmp_path)
    world["be"](RECIPIENT)
    said = _invoke("handoff", "accept", code).output
    copy = Path(os.environ["AGENT_CONFIG_PATH"]) / "handoff" / "accepted" / "ho-1a2b3c4d" / "session.md"
    assert "maxAge = 30 days (product asked)" in copy.read_text()
    assert f"The sender's whole session: {copy}" in said.replace("\n", "")


# ---- #2477: rough edges from the 1.9.2b22 stranger run ----

def test_the_code_section_says_the_code_goes_with_the_handoff_when_it_does():
    """The b22 preview said "The code goes with it" while the brief said "ask the sender to push it"."""
    travelling = {"repository": None, "branch": "main", "commit": "a" * 40, "pushed": False, "uncommitted": 1,
                  "patch": {"sha256": "b" * 64, "bytes": 900}}
    text = bundles.code_text({"code": [travelling]})
    assert "ask the sender to push it" not in text and "goes with this handoff" in text
    stuck = dict(travelling, patch={"too_large": 3_000_000})
    assert "ask the sender to push it" in bundles.code_text({"code": [stuck]})


def test_the_paste_says_a_slow_install_should_be_left_to_finish(world, drops):
    """b22 on melbourne-2: install.sh waited out PyPI's lag; Codex sees output only at the end, took it for a
    hang, and ran its own install in parallel. The two raced into "No module named 'connectonion.core'"."""
    _send(world)
    assert "let it finish" in _page(world)


# ---- b24: one line to paste; the page it names holds the rest (#2478, Aaron 2026-10-13) ----

def test_the_paste_is_one_line_naming_the_page_that_holds_the_instructions(world, drops):
    """"这两步变成一步…提示词不要太长，只有一两句话…让 Codex 访问一个包含所有提示词的网页". Tested on
    melbourne-2 Codex 0.156: with network it read the page and finished; without, it asked once."""
    _send(world)
    paste = _paste(world)
    code = replies.parse_code(re.search(r"coh3\.[A-Za-z0-9_-]+", json.loads(drops[next(iter(drops))])["prompt"]).group(0))
    assert paste.count("\n") == 0 and len(paste) < 400, paste
    assert f"https://o.openonion.ai/h/{code['drop']}/codex" in paste
    assert "without waiting for me" in paste and "allow network access" in paste


def test_the_page_holds_the_whole_prompt_under_the_id_the_code_names(world, drops):
    _send(world)
    [(drop_id, body)] = drops.items()
    full = json.loads(body)["prompt"]
    assert replies.parse_code(re.search(r"coh3\.[A-Za-z0-9_-]+", full).group(0))["drop"] == drop_id
    assert f"CO_VERSION={replies.MIN_VERSION}" in full and "let it finish" in full and "co handoff accept" in full


def test_the_mail_offers_the_page_first_and_the_line_second(world, drops):
    _send(world)
    mail = world["mails"][-1]
    [drop_id] = drops
    assert f'href="https://o.openonion.ai/h/{drop_id}"' in mail["message"]
    assert mail["message"].index(f"/h/{drop_id}\"") < mail["message"].index("<pre")


def test_a_sender_with_no_name_is_someone_never_an_agent_address():
    """b22 mail: "0x9c0a8bf90c@mail.openonion.ai passed you some work". An address is not a name."""
    nameless = bundles.seal(dict(_bundle(RECIPIENT["mail"]), **{"from": "0x9c0a8bf90c@mail.openonion.ai"}))
    mail = bundles.notice(nameless, "LINE", "https://o.openonion.ai/h/x")
    assert "0x9c0a8bf90c" not in mail["subject"] and "0x9c0a8bf90c" not in mail["text"]
    assert "Thanks,\nSomeone" not in mail["text"]                       # a nameless note is signed off by no one
    named = bundles.seal(dict(_bundle(RECIPIENT["mail"]), from_name="Aaron Xie"))
    assert "Thanks,\nAaron Xie" in bundles.notice(named, "LINE")["text"]



# ---- B11: on the recipient's side the sender may exchange handoffs only (Aaron, 2026-10-13) ----

def test_accepting_lets_the_sender_send_handoffs_but_not_use_the_recipients_tools(world, drops):
    """"发送方…那些权限直接让他用就好了…接收方的话 它是需要有些限制的". The sender lands on a level the Trust
    Agent can raise later (#2407), with the handoff in the record; the sender's side is unchanged."""
    import os
    from pathlib import Path
    from connectonion.network.trust import tools
    from connectonion.network.trust.fast_rules import evaluate_request
    _send(world)
    world["be"](RECIPIENT)
    said = _invoke("handoff", "accept", _code(_page(world))).output
    mine = Path(os.environ["AGENT_CONFIG_PATH"])
    assert tools.get_level(SENDER["address"], mine) == "handoffs" and not tools.is_contact(SENDER["address"], mine)
    config = {"allow": ["whitelisted", "contact"], "default": "deny"}       # a Host that pre-authorises contacts
    assert evaluate_request(config, SENDER["address"], {}, co_dir=mine) != "allow"
    assert "can send you handoffs and questions; they can't run tools on your machine" in " ".join(said.split())
    record = (mine / "approvals.jsonl").read_text()
    assert "add to handoffs" in record and "sent us handoff ho-1a2b3c4d" in record
    tools.promote_to_contact(SENDER["address"], mine)                      # what the Trust Agent may do later
    assert tools.get_level(SENDER["address"], mine) == "contact"

    world["be"](SENDER)                                                    # the sender's side: unchanged
    _invoke("handoff", "status", "ho-1a2b3c4d")
    assert tools.is_contact(RECIPIENT["address"], Path(os.environ["AGENT_CONFIG_PATH"]))


def test_send_shows_the_sender_the_page_the_recipient_will_see(world, drops):
    """Aaron, 2026-10-13: "直接给我一个网页…这样我就可以打开看一下 知道到底分享了什么东西"."""
    world["be"](SENDER)
    import os
    from pathlib import Path
    drafts = Path(os.environ["AGENT_CONFIG_PATH"]) / "handoff" / "drafts"
    drafts.mkdir(parents=True)
    (drafts / "ho-1a2b3c4d.json").write_text(json.dumps(_bundle(RECIPIENT["mail"])))
    sent = _invoke("handoff", "send", RECIPIENT["mail"], "--draft", "ho-1a2b3c4d", "--yes").output
    [drop_id] = drops
    assert f"What you shared, as they see it: https://o.openonion.ai/h/{drop_id}" in sent
    assert _invoke("handoff", "status", "ho-1a2b3c4d").output.count(f"https://o.openonion.ai/h/{drop_id}") == 1


# ---- the b24 mail as Aaron's Gmail on iOS showed it (2026-10-13 screenshot) ----

def test_the_button_survives_a_client_that_drops_cell_backgrounds():
    """Gmail iOS dropped the cell's `background`, leaving white text on white: a blank gap, no button."""
    html_ = bundles.notice(_bundle(RECIPIENT["mail"]), "LINE", "https://o.openonion.ai/h/x")["html"]
    cell = re.search(r'<td bgcolor="#[0-9a-f]{6}"[^>]*>(.*?)</td>', html_, re.S)
    assert cell and "background-color:" in cell.group(0)
    assert re.search(r'<a [^>]*style="[^"]*background-color:#[0-9a-f]{6}', cell.group(1))      # the link carries it too


def test_a_persons_mail_carries_no_hidden_copy_but_an_agent_mailbox_does():
    """The hidden base64 bundle is a wall of text in plain-text readers; a person's mail has the page."""
    person = bundles.notice(_bundle("bob@gmail.com"), "LINE", "https://o.openonion.ai/h/x")["html"]
    agent = bundles.notice(_bundle(RECIPIENT["mail"]), "LINE", "https://o.openonion.ai/h/x")["html"]
    assert bundles.BEGIN not in person and bundles.BEGIN in agent        # co handoff inbox reads an agent's copy


def test_the_mail_never_mixes_languages():
    """b24: "Aaron Xie 一直在和 Claude Code 一起做「co handoff refinement…」…他们讨论了：switching handoff…"."""
    zh = dict(_bundle("bob@gmail.com"), conversation=[{"at": "", "user": "邮件里不需要把所有的内容都写清楚", "ai": ""}],
              discussed=["Switching handoff delivery to lightweight notifications"])
    text = bundles.notice(bundles.seal(zh), "LINE")["text"]
    assert "他们讨论了" not in text and "Switching handoff" not in text


def test_the_report_is_written_in_the_language_the_sender_wrote_in(monkeypatch):
    seen = []
    import sys
    import connectonion.llm_do  # noqa: F401  (the module, not the function the package re-exports)
    monkeypatch.setattr(sys.modules["connectonion.llm_do"], "llm_do", lambda prompt, output=None, **kw: (
        seen.append(prompt), bundles.Top(title="t", task="t", where_it_stands="w"))[1])
    bundles.draft([{"at": "", "user": "邮件只是让对方安装，或者起一个提醒作用", "ai": "好"}], "交接")
    assert "Write every field in Chinese" in seen[-1]
    bundles.draft([{"at": "", "user": "Keep the mail short", "ai": "ok"}], "the mail")
    assert "Write every field in English" in seen[-1]


def test_an_ai_turn_is_quoted_short_and_the_senders_words_whole():
    """Aaron, 2026-10-13: "可以把 AI 的回答压缩一下…同时 把用户的原文要求保存下来"."""
    assert bundles.QUOTE_CHARS <= 800
    assert len(bundles.quote("x" * 5000)) < 900


def test_an_unanswered_question_ends_in_a_stated_assumption_not_a_wait_forever(world, drops):
    """b24 audit, same input twice: one run assumed and finished, the other waited indefinitely."""
    _send(world)
    world["be"](RECIPIENT)
    said = " ".join(_invoke("handoff", "accept", _code(_page(world))).output.split())
    assert "about 10 minutes" in said and "Assumed:" in said


# ---- the replayed Codex thread, as Aaron looked for it in the app on Parrot ----

def test_the_replayed_thread_is_listed_in_the_codex_app_with_short_labels_and_real_times(tmp_path):
    """b24 audit: "source": "exec" threads are omitted from thread/list, so the app's sidebar never showed
    it; labels read "(from Aaron Test, who handed this over · 2026-10-13)"; every row said "now"; turns
    where the AI only ran tools showed "(no reply recorded)"."""
    from connectonion.handoff import opener
    zh = dict(_bundle(RECIPIENT["mail"]), from_name="Aaron Xie", lang="zh", conversation=[
        {"at": "2026-10-13T02:13:00Z", "user": "看一下日志", "ai": ""},
        {"at": "2026-10-13T02:18:00Z", "user": "邮件只做提醒", "ai": "好的"}])
    rows = opener.replay_lines(bundles.seal(zh), "t1", tmp_path, "2026-10-13T09:00:00.000Z", "m")
    assert rows[0]["payload"]["source"] == "cli"
    said = [r["payload"]["message"] for r in rows if r["payload"].get("type") == "user_message"]
    assert said[0].startswith("(Aaron Xie · 10月13日)") and "who handed this over" not in said[0]
    replied = [r["payload"]["message"] for r in rows if r["payload"].get("type") == "agent_message"]
    assert replied == ["(Aaron Xie 的 Codex)\n\n好的"]             # no empty bubble for a tools-only turn
    assert {r["timestamp"] for r in rows[1:6]} == {"2026-10-13T02:13:00.000Z"}        # a turn with no reply: 5 rows
    assert opener.REPORT.startswith("(co handoff)")


# ---- the conversation as the viewer shows it: one reply per turn, no repeats, clean cuts ----

def test_a_turn_shows_the_ais_final_reply_and_counts_the_steps_before_it():
    """b25 chat review: one bubble glued every text segment between tool calls ("…能不能发 HTML 邮件：
    Now my part of #2477. Tests first: 129 passed…"), switching language and ending on colons."""
    from connectonion.handoff import sessions
    turns = [{"role": "user", "text": "Ship it", "timestamp": "2026-10-13T01:00:00Z"},
             {"role": "assistant", "text": "Tests first:", "timestamp": "2026-10-13T01:00:05Z"},
             {"role": "assistant", "text": "129 passed. Opening the PR:", "timestamp": "2026-10-13T01:01:00Z"},
             {"role": "assistant", "text": "Done: PR #1 is merged.", "timestamp": "2026-10-13T01:02:00Z"}]
    [turn] = sessions.exchanges(turns)
    assert turn["final"] == "Done: PR #1 is merged." and turn["steps"] == 2
    assert "Tests first:" in turn["ai"]                     # the report on top still reads all of it
    cut_short = sessions.exchanges(turns + [{"role": "assistant", "text": "Now the docs:", "timestamp": "t"}])
    assert cut_short[0]["final"] == "Done: PR #1 is merged." and cut_short[0]["steps"] == 3
    bundle = bundles.assemble(handoff_id="h", sender="a@b", to="c@d", what="w", source={"kind": "claude"}, code=[],
                              top=bundles.Top(title="t", task="t", where_it_stands="w"), exchanges=[turn])
    assert bundle["conversation"] == [{"at": turn["at"], "user": "Ship it", "ai": "Done: PR #1 is merged.", "steps": 2}]


def test_a_message_typed_while_the_ai_was_busy_is_not_shown_twice():
    """b25 chat review: Claude Code records it as a queued_command and again when it is delivered."""
    from connectonion.handoff import sessions
    turns = [{"role": "user", "text": "Keep the mail short", "timestamp": "2026-10-13T01:00:00Z"},
             {"role": "assistant", "text": "Noted.", "timestamp": "2026-10-13T01:00:30Z"},
             {"role": "user", "text": "Keep the mail short", "timestamp": "2026-10-13T01:02:00Z"},
             {"role": "assistant", "text": "Shortened it.", "timestamp": "2026-10-13T01:03:00Z"},
             {"role": "user", "text": "Keep the mail short", "timestamp": "2026-10-14T09:00:00Z"}]
    said = sessions.exchanges(turns)
    assert [e["user"] for e in said] == ["Keep the mail short"] * 2       # the next day it is a new request
    assert said[0]["final"] == "Shortened it." and said[0]["steps"] == 1


def test_a_long_reply_is_cut_between_lines_not_inside_words():
    """b25 chat review: "…then openi[cut]y` 和纯文本 `body`" left half-words and half a code span."""
    text = "\n".join(f"line {n}: `code {n}` and some words" for n in range(80))
    cut = bundles.quote(text)
    head, mark, tail = cut.partition("\n[…")
    assert text.startswith(head) and head.endswith("words")
    assert tail.split("]\n", 1)[1].startswith("line ") and len(cut) < 900


# ---- other people's contact details never reach the page, the mail or the session copy ----

def test_other_peoples_addresses_and_numbers_are_masked_on_the_page():
    """Aaron, 2026-10-14: "mailto:ivvli0000@outlook.com 这个是错误的". A co rem run had quoted a relative's
    address; the handoff copied it onto a page anyone with the link can open. The sender's and the
    recipient's own addresses stay, and so do example addresses."""
    talk = [{"at": "2026-10-13T01:00:00Z", "user": "Mail me at aaron@home.net, not ivvli0000@outlook.com",
             "ai": "Done. people/ivvli0000-outlook-com-e381998ef8.md (grep ivvli0000 *.md) has her number +61 412 000 111 and "
                   "0435 525 634; bob@example.com is the test user; ody@x.co got it.",
             "final": "", "steps": 0}]
    talk[0]["final"] = talk[0]["ai"]
    bundle = bundles.assemble(handoff_id="h", sender="0xabc@mail.openonion.ai", to="ody@x.co", what="w",
                              source={"kind": "claude"}, code=[], keep=["aaron@home.net"],
                              top=bundles.Top(title="t", task="ask ivvli0000@outlook.com", where_it_stands="w"),
                              exchanges=talk)
    text = json.dumps(bundle, ensure_ascii=False)
    assert "ivvli0000" not in text and "412 000 111" not in text and "525 634" not in text
    assert "aaron@home.net" in text and "ody@x.co" in text and "bob@example.com" in text
    assert "[email removed]" in bundle["conversation"][0]["user"]


def test_the_session_copy_masks_them_too(tmp_path, monkeypatch):
    session = tmp_path / "s.jsonl"
    session.write_text(json.dumps({"type": "user", "timestamp": "2026-10-13T01:00:00Z",
                                   "message": {"content": "write to s.whittle@unsw.edu.au and me@home.net"}}) + "\n")
    copy = replies.unpack(replies._copy({"sent_at": "2026-10-14T00:00:00Z", "to": "r@x.co", "owner": "me@home.net"},
                                        {"kind": "claude", "path": str(session)}))
    assert "whittle" not in copy and "me@home.net" in copy


def test_masking_leaves_ordinary_words_and_the_kept_addresses_alone():
    """#2493 review: "anyone" and "notify" became "someone" because anyone@x.com and notify@x.com were
    masked; a literal \\n before an address read as part of it, so a kept address was not recognised."""
    text = "anyone@x.com said anyone can read notify.py; log: 'sent\\nxietianle@outlook.com\\nnotify@x.com'"
    out = bundles.mask(text, ["xietianle@outlook.com"])
    assert "anyone can read notify.py" in out and "xietianle@outlook.com" in out
    assert "anyone@x.com" not in out and "notify@x.com" not in out


def test_masking_reaches_names_profiles_numbers_and_ips_that_point_at_a_person():
    """#2493 review on a real session: co rem page names, mail-header names, LinkedIn ids, landlines,
    1800 numbers and IP addresses all survived."""
    text = ("people/tamara-berryman-324b6af6e8.md; ~/.co/rem/people/vern-chan-cccf24fb07.md; for f in david-burt-daaa78c99a; do; orgs/unsw-edu-au-921856d25b.md\n"
            "From: Jiexuan Deng <jd@student.unsw.edu.au>\n"
            "https://www.linkedin.com/in/mia-chen-data/ call 02 9065 4432, (02) 7235 5365, 1800 737 633, 0873918410\n"
            "ssh onion@100.71.113.43 and 35.189.30.72; bind 127.0.0.1 or 0.0.0.0")
    out = bundles.mask(text)
    for gone in ("tamara-berryman", "vern-chan", "david-burt", "Jiexuan Deng", "mia-chen-data", "9065 4432", "7235 5365",
                 "737 633", "0873918410", "100.71.113.43", "35.189.30.72"):
        assert gone not in out, gone
    assert "orgs/unsw-edu-au-921856d25b.md" in out and "127.0.0.1" in out and "0.0.0.0" in out
