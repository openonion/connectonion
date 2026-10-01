"""co canny: read and triage Canny feedback over Canny's REST API (#2050).

LLM-Note:
  Dependencies: imports from [typer, httpx (lazy), cli/style.py, cli/typer_groups.py, command_tips.py, environment.py (setting)] | imported by [cli/main.py] | tested by [tests/unit/test_canny_commands.py, tests/e2e/real_api/test_real_co_canny.py]
  Data flow: handler → _call(endpoint, recover, **body) → POST https://canny.io/api/<endpoint> with {"apiKey", ...} → trimmed rows → text or --json on stdout, Next: tip after
  State/Effects: reads CANNY_API_KEY (process, then the selected env file, then the encrypted store) and CANNY_USER_ID | status, comment and changelog create change Canny only with --yes; without it they print a preview and the exact command
  Errors: missing key, API refusal or a second 429 → message on stderr, Next: <command> on stderr, exit 1

Every Canny endpoint is a POST of JSON carrying the secret apiKey, so the
client is one function. A 429 is waited out once when Retry-After is short;
a long one (an hourly window) is reported instead of blocking an agent.
"""

import json
import os
import re
import shlex
import sys
import time
from enum import Enum
from typing import Optional

import typer

from .. import style
from ..typer_groups import _OneSuggestion
from .command_tips import mark_next_step_named, print_tip, selected_tip

API = "https://canny.io/api"
KEY_HELP = "Find the secret API key in Canny under Settings → API"
SET_KEY = "co env set CANNY_API_KEY <key> --secret"
FIND_USER = "co canny check --email you@example.com"
MAX_WAIT = 60        # seconds of Retry-After we wait out; longer is reported
COMMENTS = 20        # newest comments shown by co canny post
BOARD_ID = re.compile(r"[0-9a-f]{24}")


# -- talking to Canny -------------------------------------------------------

def _http():
    import httpx
    return httpx.Client(timeout=30)


def _next(command: str, stderr: bool = False) -> None:
    """One Next: line. On stderr when stdout is --json or the command failed."""
    if not stderr:
        print_tip(f"Next: {command}")
        return
    style.console(stderr=True).print(style.markup(f"Next: {selected_tip(command)}"))
    mark_next_step_named()


def _fail(message: str, command: str) -> None:
    print(message, file=sys.stderr)
    _next(command, stderr=True)
    raise typer.Exit(1)


def _setting(name: str) -> Optional[str]:
    """A value from the shell, the selected env file, or `co env set --secret`'s store."""
    from ...environment import load_environment, setting
    load_environment()
    return setting(name)


def _find_key() -> tuple[Optional[str], str]:
    """CANNY_API_KEY and where it came from: the shell, the env file, or the encrypted store."""
    from ...environment import display_path, process_environment, selected_env_file
    key = _setting("CANNY_API_KEY")
    if "CANNY_API_KEY" in process_environment():
        return key, "your shell"
    if os.environ.get("CANNY_API_KEY") or not key:
        return key, display_path(selected_env_file())
    return key, "the encrypted store"


def _api_key() -> str:
    key, where = _find_key()
    if not key:
        _fail(f"CANNY_API_KEY is not set in {where}. {KEY_HELP}, then save it encrypted:", SET_KEY)
    return key


def _retry_after(response) -> int:
    return int(response.headers.get("Retry-After", "1"))


def _again() -> str:
    """The command being run, to repeat after a rate limit."""
    return shlex.join(["co", *sys.argv[1:]])


def _call(endpoint: str, recover: str, **body) -> dict:
    """POST one endpoint, e.g. "v1/posts/list". None values are left out of the body."""
    payload = {"apiKey": _api_key(), **{k: v for k, v in body.items() if v is not None}}
    with _http() as http:
        response = http.post(f"{API}/{endpoint}", json=payload)
        if response.status_code == 429 and _retry_after(response) <= MAX_WAIT:
            print(f"Canny rate limit: waiting {_retry_after(response)}s, then trying once more.", file=sys.stderr)
            time.sleep(_retry_after(response))
            response = http.post(f"{API}/{endpoint}", json=payload)
    if response.status_code == 429:
        _fail(f"Canny's rate limit is reached (HTTP 429): it asks for {_retry_after(response)}s before the "
              "next request and did not process this one. Wait that long, then run the same command:", _again())
    if response.status_code >= 400:
        _refused(endpoint, response, recover)
    return response.json()


def _refused(endpoint: str, response, recover) -> None:
    """recover is the next command, or a function of Canny's error text returning (note, command)."""
    is_json = "json" in response.headers.get("content-type", "")
    error = str(response.json().get("error", "") if is_json else response.text[:200])
    if response.status_code in (401, 403) or "api key" in error.lower():
        _fail(f"Canny rejected the API key (HTTP {response.status_code}: {error}). {KEY_HELP}, then:", SET_KEY)
    note, command = recover(error) if callable(recover) else ("", recover)
    _fail(f"Canny refused {endpoint} (HTTP {response.status_code}): {error}{note}", command)


def _acting_user() -> str:
    """The Canny user id recorded as changing a status or writing a comment."""
    user = _setting("CANNY_USER_ID")
    if not user:
        _fail("Canny records which admin changed a status or wrote a comment, and an API key does not say "
              "who you are. Set CANNY_USER_ID once to your own Canny user id. Find it by your login email:",
              FIND_USER)
    return user


def _board_id(board: Optional[str]) -> Optional[str]:
    """A board id as given, or the id of the board with this name."""
    if board is None or BOARD_ID.fullmatch(board):
        return board
    boards = _call("v1/boards/list", "co canny boards")["boards"]
    match = [b["id"] for b in boards if b["name"].lower() == board.lower()]
    if not match:
        names = ", ".join(b["name"] for b in boards) or "none"
        _fail(f'No Canny board is named "{board}". Boards: {names}', "co canny boards")
    return match[0]


# -- shaping and printing ---------------------------------------------------

def _name(user) -> str:
    return (user or {}).get("name") or "-"


def _post_row(post: dict) -> dict:
    return {"id": post["id"], "title": post["title"], "status": post["status"], "votes": post["score"],
            "board": post["board"]["name"], "created": post["created"]}


def _post_line(row: dict) -> str:
    return (f"{row['id']}  {row['votes']:>4} {_plural(row['votes'], 'vote'):<5}  {row['status']:<12}  {row['board']}  "
            f"{row['created'][:10]}  {row['title']}")


def _print_json(value) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def _say(text: str) -> None:
    """Provider text, printed as it is: a [bracket] in a title is not markup."""
    style.console().print(text, markup=False)


def _plural(n: int, word: str, words: str = "") -> str:
    """"1 board", "2 boards"; pass the plural when it is not word + s."""
    return word if n == 1 else (words or word + "s")


# -- read commands ------------------------------------------------------------

def handle_boards(json_output: bool) -> None:
    boards = _call("v1/boards/list", "co canny check")["boards"]
    rows = [{"id": b["id"], "name": b["name"], "posts": b["postCount"], "private": b.get("isPrivate", False),
             "created": b["created"], "url": b.get("url")} for b in boards]
    if json_output:
        _print_json({"boards": rows})
    else:
        style.console().print(f"{style.count(len(rows))} {_plural(len(rows), 'board')}")
        for row in rows:
            _say(f"{row['id']}  {row['posts']:>5} {_plural(row['posts'], 'post'):<5}  "
                 f"{'private' if row['private'] else 'public ':<7}  {row['name']}  {row['url']}")
    _next_after_boards(rows, json_output)


def _next_after_boards(rows: list, json_output: bool) -> None:
    """The busiest board's posts; with no posts anywhere, where to add one, not an empty listing."""
    busy = sorted((r for r in rows if r["posts"]), key=lambda r: -r["posts"])
    if busy:
        _next(f"co canny posts --board {busy[0]['id']} --sort score", json_output)
        return
    if rows:
        print(f"No board has posts yet. Add one on the board's page, {rows[0]['url']}, then list again.",
              file=sys.stderr if json_output else sys.stdout)
    _next("co canny boards" if rows else "co canny check", json_output)


def handle_posts(board: Optional[str], status: Optional[str], sort: str, limit: int,
                 json_output: bool, search: Optional[str] = None) -> None:
    data = _call("v1/posts/list", "co canny boards", boardID=_board_id(board), status=status,
                 sort=sort, limit=limit, search=search)
    rows = [_post_row(p) for p in data["posts"]]
    if json_output:
        _print_json({"posts": rows, "hasMore": data.get("hasMore", False)})
    else:
        more = "; more match, raise -n to see them" if data.get("hasMore") else ""
        style.console().print(f"{style.count(len(rows))} {_plural(len(rows), 'post')}{more}")
        for row in rows:
            _say(_post_line(row))
    _next(f"co canny post {rows[0]['id']}" if rows else _next_after_nothing(search), json_output)


def _next_after_nothing(search: Optional[str]) -> str:
    """No rows: browse instead of searching; with nothing to browse, the boards and their post counts."""
    return "co canny posts --sort score" if search else "co canny boards"


def _comment_row(comment: dict) -> dict:
    return {"id": comment["id"], "author": _name(comment.get("author")), "created": comment["created"],
            "internal": comment.get("internal", False), "value": comment.get("value", "")}


def _post_detail(post: dict, comments: list) -> dict:
    return {**_post_row(post), "url": post.get("url"), "author": _name(post.get("author")),
            "owner": _name(post.get("owner")), "eta": post.get("eta"), "details": post.get("details", ""),
            "commentCount": post.get("commentCount", 0), "comments": [_comment_row(c) for c in comments]}


def _print_post(detail: dict) -> None:
    _say(detail["title"])
    _say(_post_line(detail))
    _say(f"by {detail['author']}  owner {detail['owner']}  eta {detail['eta'] or '-'}  {detail['url']}")
    if detail["details"]:
        _say("\n" + detail["details"])
    shown = len(detail["comments"])
    style.console().print(f"\n{style.count(shown)} {_plural(shown, 'comment')}, newest first, "
                          f"of {detail['commentCount']}")
    for c in detail["comments"]:
        internal = " (internal)" if c["internal"] else ""
        _say(f"  {c['created'][:10]}  {c['author']}{internal}: {c['value']}")


def handle_post(post_id: str, json_output: bool) -> None:
    post = _call("v1/posts/retrieve", "co canny posts", id=post_id)
    comments = _call("v2/comments/list", "co canny posts", postID=post_id, limit=COMMENTS)["items"]
    detail = _post_detail(post, comments)
    if json_output:
        _print_json(detail)
    else:
        _print_post(detail)
    _next(f'co canny comment {post_id} "<your reply>"', json_output)


def handle_changelog(limit: int, json_output: bool) -> None:
    entries = _call("v1/entries/list", "co canny check", limit=limit)["entries"]
    rows = [{"id": e["id"], "title": e["title"], "status": e["status"], "types": e.get("types", []),
             "created": e["created"], "publishedAt": e.get("publishedAt"), "url": e.get("url")} for e in entries]
    if json_output:
        _print_json({"entries": rows})
    else:
        style.console().print(f"{style.count(len(rows))} {_plural(len(rows), 'changelog entry', 'changelog entries')}, "
                              "unpublished first")
        for row in rows:
            date = (row["publishedAt"] or row["created"])[:10]
            _say(f"{row['id']}  {row['status']:<9}  {date}  {row['title']}")
    _next('co canny changelog create "<title>" --details -', json_output)


# -- checking the connection ----------------------------------------------------

def _workspace(boards: list) -> str:
    """The Canny host, read from a board's URL; the API has no company endpoint."""
    url = boards[0].get("url", "") if boards else ""
    return url.split("/")[2] if url.count("/") >= 2 else "unknown (no boards)"


def _lookup(email: str) -> None:
    user = _call("v1/users/retrieve", FIND_USER, email=email)
    role = "a Canny admin" if user.get("isAdmin") else "NOT a Canny admin: Canny takes status changes only from admins"
    _say(f"{user['id']}  {_name(user)}  {email}  {role}")
    if not user.get("isAdmin"):
        _next("co canny check --email <an admin's login email>")
        return
    _next(f"co env set CANNY_USER_ID {user['id']}")


def _report_user() -> bool:
    """Print who writes as you. True when CANNY_USER_ID is set and an admin."""
    user_id = _setting("CANNY_USER_ID")
    if not user_id:
        style.console().print(style.warn("Acting user: CANNY_USER_ID is not set; status and comment need it"))
        return False
    user = _call("v1/users/retrieve", FIND_USER, id=user_id)
    admin = bool(user.get("isAdmin"))
    _say(f"Acting user: {user_id} {_name(user)} ({'admin' if admin else 'NOT an admin'})")
    return admin


def handle_check(email: Optional[str]) -> None:
    if email:
        _lookup(email)
        return
    _, where = _find_key()
    boards = _call("v1/boards/list", "co canny check")["boards"]
    out = style.console()
    out.print(f"API key: {style.ok('accepted')} (CANNY_API_KEY from {style.path(where)})")
    _say(f"Workspace: {_workspace(boards)}")
    _say(f"Boards: {len(boards)} visible: "
         + ", ".join(f"{b['name']} ({b['postCount']} {_plural(b['postCount'], 'post')})" for b in boards))
    _next("co canny posts --status open --sort score" if _report_user() else FIND_USER)


# -- write commands: preview unless --yes -------------------------------------

def _preview(lines: list, command: list) -> None:
    for line in lines:
        _say(line)
    style.console().print(style.warn("Nothing changed: this was a preview."))
    _next(shlex.join(command))


def handle_status(post_id: str, status: str, comment: Optional[str], notify: bool, yes: bool) -> None:
    _api_key()                 # the key is the first thing to fix, so it is named first
    changer = _acting_user()
    post = _call("v1/posts/retrieve", "co canny posts", id=post_id)
    if not yes:
        same = "  It already has this status: Canny will record nothing and email no one." if post["status"] == status else ""
        emails = "emails its non-admin voters" if notify else "emails no one (add --notify to email voters)"
        _preview([f'Change "{post["title"]}" ({post_id}): {post["status"]} -> {status}.{same}',
                  f"Comment: {comment or '(none)'}",
                  f"Votes: {post['score']}; this {emails}",
                  f"Recorded as Canny user {changer} (CANNY_USER_ID)"],
                 ["co", "canny", "status", post_id, status, *(["--comment", comment] if comment else []),
                  *(["--notify"] if notify else []), "--yes"])
        return
    _call("v1/posts/change_status", f"co canny post {post_id}", postID=post_id, changerID=changer,
          status=status, shouldNotifyVoters=notify, commentValue=comment)
    told = "voters emailed" if notify else "no one emailed"
    style.console().print(style.ok(f"Changed {post_id} from {post['status']} to {status}; {told}."))
    _next(f"co canny post {post_id}")


def handle_comment(post_id: str, text: str, internal: bool, yes: bool) -> None:
    _api_key()                 # the key is the first thing to fix, so it is named first
    author = _acting_user()
    post = _call("v1/posts/retrieve", "co canny posts", id=post_id)
    if not yes:
        seen = "your team only (internal)" if internal else "everyone who can see the post"
        _preview([f'Comment on "{post["title"]}" ({post_id}) as Canny user {author}:', text,
                  f"Visible to {seen}; voters are not emailed."],
                 ["co", "canny", "comment", post_id, text, *(["--internal"] if internal else []), "--yes"])
        return
    created = _call("v1/comments/create", _after_comment_refused(post_id, text), postID=post_id,
                    authorID=author, value=text, internal=internal or None)
    style.console().print(style.ok(f"Commented on {post_id} (comment {created['id']})."))
    _next(f"co canny post {post_id}")


def _after_comment_refused(post_id: str, text: str):
    """Canny's Free plan has no internal comments: offer the same comment, said plainly to be public."""
    def recover(error: str):
        if "internal" not in error.lower():
            return "", f"co canny post {post_id}"
        return ("\nYour Canny plan has no internal comments. Without --internal the comment is public: "
                "everyone who can see the post reads it.", shlex.join(["co", "canny", "comment", post_id, text]))
    return recover


def handle_changelog_create(title: str, details: str, publish: bool, yes: bool) -> None:
    text = sys.stdin.read() if details == "-" else details
    if not yes:
        state = "published now, publicly visible" if publish else "saved as a draft"
        _preview([f'Changelog entry "{title}", {state}; subscribers are not emailed.',
                  f"Details ({len(text)} characters):", text[:500]],
                 ["co", "canny", "changelog", "create", title, "--details", details,
                  *(["--publish"] if publish else []), "--yes"])
        if details == "-":
            print("Pipe the same details into it again.", file=sys.stderr)
        return
    created = _call("v1/entries/create", "co canny changelog", title=title, details=text, published=publish)
    style.console().print(style.ok(f"Created changelog entry {created['id']} ({'published' if publish else 'draft'})."))
    _next("co canny changelog")


# -- the command surface --------------------------------------------------------

class Sort(str, Enum):
    newest = "newest"
    oldest = "oldest"
    score = "score"
    statusChanged = "statusChanged"
    trending = "trending"


JSON_HELP = "Print the same fields as one JSON object; the Next: line goes to stderr"
BOARD_HELP = 'Board id, or its exact name ("Feature Requests"), from co canny boards'
STATUS_HELP = ('open, "under review", planned, "in progress", complete, closed, or a custom status '
               "from your Canny settings; comma-separate several")
POST_HELP = "Post id, from co canny posts or co canny search"
USER_NOTE = ("Canny records who did it: CANNY_USER_ID, your Canny admin user id. "
             f"Find yours once with {FIND_USER}, then co env set CANNY_USER_ID <id>.")

canny_app = typer.Typer(
    cls=_OneSuggestion,
    help="Your Canny feedback boards: posts, votes and comments; change a post's status, reply, write the "
         "changelog. Reads are Read-only; status, comment and changelog create only preview until --yes. "
         "Needs CANNY_API_KEY, the secret API key in Canny under Settings → API.",
    epilog="Example:  co canny posts --status open --sort score -n 5  |  "
           "Workflow:  co canny check  →  co canny posts  →  co canny post <post-id>  →  "
           "co canny status <post-id> planned --notify",
    invoke_without_command=True)


@canny_app.callback()
def canny(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        print(ctx.get_help())
        print_tip("Next: co canny check")


@canny_app.command("check", epilog="Example:  co canny check  |  co canny check --email you@example.com")
def check(email: Optional[str] = typer.Option(None, "--email", help="Look up a Canny user's id by login email, for CANNY_USER_ID")):
    """Check the Canny connection: the API key, the boards it sees, and the admin user that writes as you. Read-only.

    Run it first. Without CANNY_API_KEY it names the co env set command. With
    --email it prints that user's id and whether they are an admin; only an
    admin can change a status, so set CANNY_USER_ID to an admin's id.
    """
    handle_check(email)


@canny_app.command("boards", epilog="Example:  co canny boards  |  co canny boards --json")
def boards(json_output: bool = typer.Option(False, "--json", help=JSON_HELP)):
    """List your Canny boards with ids and post counts. Read-only."""
    handle_boards(json_output)


@canny_app.command("posts", epilog='Example:  co canny posts --status open --sort score -n 5  |  '
                                   'co canny posts --board "Feature Requests" --status planned --json')
def posts(board: Optional[str] = typer.Option(None, "--board", help=BOARD_HELP),
          status: Optional[str] = typer.Option(None, "--status", help=STATUS_HELP),
          sort: Sort = typer.Option(Sort.newest, "--sort", help="score is most votes first"),
          limit: int = typer.Option(20, "--limit", "-n", min=1, max=100, help="How many posts to show"),
          json_output: bool = typer.Option(False, "--json", help=JSON_HELP)):
    """List feedback posts: id, votes, status, board, created, title. Read-only.

    The five most-voted open requests: co canny posts --status open --sort score -n 5.
    Each row starts with the post id that co canny post, status and comment take.
    """
    handle_posts(board, status, sort.value, limit, json_output)


@canny_app.command("search", epilog='Example:  co canny search "dark mode"  |  '
                                    'co canny search "export" --board "Feature Requests" --json')
def search(text: str = typer.Argument(..., help="Words to find in post titles and details"),
           board: Optional[str] = typer.Option(None, "--board", help=BOARD_HELP),
           limit: int = typer.Option(20, "--limit", "-n", min=1, max=100, help="How many posts to show"),
           json_output: bool = typer.Option(False, "--json", help=JSON_HELP)):
    """Find posts that match words, best match first, before filing a duplicate. Read-only."""
    handle_posts(board, None, "relevance", limit, json_output, search=text)


@canny_app.command("post", epilog="Example:  co canny post <post-id>  |  co canny post <post-id> --json")
def post(post_id: str = typer.Argument(..., help=POST_HELP),
         json_output: bool = typer.Option(False, "--json", help=JSON_HELP)):
    """Show one post: details, vote count, status, owner, ETA and its newest comments. Read-only."""
    handle_post(post_id, json_output)


STATUS_DOC = (
    "Change a post's status (planned, complete…), with an optional comment and email to its voters. "
    "Previews unless --yes; Changes the post with --yes.\n\n"
    "The preview shows the current status, the vote count and who would be emailed, and prints the "
    "exact command with --yes. Setting the status a post already has records nothing and emails no one. "
    + USER_NOTE)


@canny_app.command("status", help=STATUS_DOC, epilog='Example:  co canny status <post-id> planned --comment "On the roadmap for October" --notify  |  '
                                    "co canny status <post-id> planned --notify --yes")
def set_status(post_id: str = typer.Argument(..., help=POST_HELP),
               status: str = typer.Argument(..., help=STATUS_HELP.removesuffix("; comma-separate several")),
               comment: Optional[str] = typer.Option(None, "--comment", help="Public comment posted with the change"),
               notify: bool = typer.Option(False, "--notify", help="Have Canny email the post's non-admin voters"),
               yes: bool = typer.Option(False, "--yes", help="Make the change; without it you get a preview")):
    handle_status(post_id, status, comment, notify, yes)


COMMENT_DOC = (
    "Reply on a post as your Canny admin user; --internal keeps it to your team. "
    "Previews unless --yes; Sends it with --yes.\n\n"
    "Voters are not emailed for a comment; to tell them, change the status with "
    'co canny status <post-id> <status> --comment "..." --notify. ' + USER_NOTE)


@canny_app.command("comment", help=COMMENT_DOC, epilog='Example:  co canny comment <post-id> "Thanks, this is planned"  |  '
                                     'co canny comment <post-id> "Needs design review" --internal --yes')
def comment(post_id: str = typer.Argument(..., help=POST_HELP),
            text: str = typer.Argument(..., help="Comment text, under 2,500 characters"),
            internal: bool = typer.Option(False, "--internal", help="Visible to your team only"),
            yes: bool = typer.Option(False, "--yes", help="Post it; without it you get a preview")):
    handle_comment(post_id, text, internal, yes)


changelog_app = typer.Typer(
    cls=_OneSuggestion,
    help="Your Canny changelog. Bare co canny changelog lists entries, unpublished first (Read-only); "
         "create writes one (Creates; previews unless --yes).",
    epilog="Example:  co canny changelog -n 5  |  co canny changelog --json",
    invoke_without_command=True)
canny_app.add_typer(changelog_app, name="changelog")


@changelog_app.callback()
def changelog(ctx: typer.Context,
              limit: int = typer.Option(10, "--limit", "-n", min=1, max=100, help="How many entries to show"),
              json_output: bool = typer.Option(False, "--json", help=JSON_HELP)):
    """List changelog entries, unpublished first: id, status, date, title. Read-only."""
    if ctx.invoked_subcommand is None:
        handle_changelog(limit, json_output)


@changelog_app.command("create", epilog='Example:  co canny changelog create "Dark mode" --details "Dark mode is here."  |  '
                                        'cat notes.md | co canny changelog create "Dark mode" --details - --publish --yes')
def changelog_create(title: str = typer.Argument(..., help="Entry title"),
                     details: str = typer.Option(..., "--details", help="Entry text in Markdown; - reads it from stdin"),
                     publish: bool = typer.Option(False, "--publish", help="Publish now, publicly; default saves a draft"),
                     yes: bool = typer.Option(False, "--yes", help="Create it; without it you get a preview")):
    """Write a changelog entry, a draft unless --publish. Previews unless --yes; Creates the entry with --yes.

    Canny does not email subscribers for entries made here. Link the entry to
    posts and send it from Canny's changelog editor if you want that.
    """
    handle_changelog_create(title, details, publish, yes)
