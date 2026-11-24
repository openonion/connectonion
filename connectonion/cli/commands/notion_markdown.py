"""
Purpose: one Notion page as a Markdown document — `co notion page <ref> --md`
LLM-Note:
  Dependencies: imports from [json, re, notion_api.py (plain, media, block_text)] | imported by [notion_commands.py page --md] | tested by [tests/unit/test_notion_commands.py]
  Data flow: read_page() detail (row fields, typed properties, flat (depth, block) list, coverage) → YAML front matter (title, id, link, edited, properties) → `# Title` → the blocks as CommonMark/GFM → coverage, visible when the read stopped short
  State/Effects: pure; reads nothing and writes nothing
  Integration: --md prints document(); the terminal view of `page` renders body(terminal=True) with Rich, as co obsidian renders a note: the same Markdown, with child pages and files named instead of linked (they are numbered and listed after it)
  Errors: none raised; a block type with no Markdown form is kept as an *[unsupported block: …]* line, never dropped silently
"""

import json
import re

from . import notion_api as api

LIST_KINDS = {"bulleted_list_item": "- ", "numbered_list_item": "1. ", "to_do": "- ", "toggle": "- "}
HEADINGS = {"heading_1": "## ", "heading_2": "### ", "heading_3": "#### ", "heading_4": "##### "}
LAYOUT = {"column_list", "column", "synced_block", "table_of_contents", "breadcrumb", "table"}


def _edges(text: str) -> tuple[str, str, str]:
    """Leading space, core, trailing space: Markdown markers must touch the text they wrap."""
    core = text.strip()
    if not core:
        return text, "", ""
    start = text.index(core)
    return text[:start], core, text[start + len(core):]


def inline(rich_text: list | None) -> str:
    """Rich text with bold, italic, strikethrough, inline code and http(s) links kept."""
    out = []
    for part in rich_text or []:
        text = part.get("plain_text") or (part.get("text") or {}).get("content", "")
        if not text:
            continue
        notes = part.get("annotations") or {}
        lead, core, trail = _edges(text)
        if core:
            if notes.get("code"):
                core = f"`{core}`"
            if notes.get("bold"):
                core = f"**{core}**"
            if notes.get("italic"):
                core = f"*{core}*"
            if notes.get("strikethrough"):
                core = f"~~{core}~~"
        href = part.get("href") or ((part.get("text") or {}).get("link") or {}).get("url") or ""
        if core and re.match(r"https?://", href):
            core = f"[{core}]({href})"
        out.append(lead + core + trail)
    return "".join(out)


def notion_link(object_id: str) -> str:
    return f"https://www.notion.so/{object_id.replace('-', '')}"


def _media(block: dict) -> str:
    found = api.media(block)
    if not found["url"]:
        return f"*[{found['kind']}: {found['name']}]*"
    if found["kind"] == "image":
        return f"![{found['name']}]({found['url']})"
    return f"[{found['name']}]({found['url']})"


def block_markdown(block: dict, terminal: bool = False) -> str:
    """One block's own text; its children are placed by `body`.

    terminal: for the `page` view, child pages and files are named, not linked:
    the view numbers them after the content, and a long URL in the text helps no one.
    """
    kind = block.get("type", "")
    data = block.get(kind) or {}
    if terminal and kind == "child_page":
        return f"**{api.one_line(data.get('title')) or 'Untitled'}** *(child page)*"
    if terminal and kind == "child_database":
        return f"**{api.one_line(data.get('title')) or 'Untitled database'}** *(child database)*"
    if terminal and kind == "link_to_page":
        return "*(link to another page)*"
    if terminal and kind in api.MEDIA:
        found = api.media(block)
        return f"*[{found['kind']}: {found['name']}]*"
    if kind in HEADINGS:              # a Markdown heading is one line
        return HEADINGS[kind] + api.one_line(inline(data.get("rich_text")))
    if kind == "to_do":
        return f"- [{'x' if data.get('checked') else ' '}] {inline(data.get('rich_text'))}"
    if kind in LIST_KINDS:
        return LIST_KINDS[kind] + inline(data.get("rich_text"))
    if kind in ("quote", "callout"):
        return "> " + inline(data.get("rich_text"))
    if kind == "paragraph" or kind == "template":
        return inline(data.get("rich_text"))
    if kind == "code":
        return f"```{data.get('language', '')}\n{api.plain(data.get('rich_text'))}\n```"
    if kind == "divider":
        return "---"
    if kind == "equation":
        return f"$$\n{data.get('expression', '')}\n$$"
    if kind == "child_page":
        return f"[{api.one_line(data.get('title')) or 'Untitled'}]({notion_link(block['id'])})"
    if kind == "child_database":
        return f"[{api.one_line(data.get('title')) or 'Untitled database'}]({notion_link(block['id'])}) (database)"
    if kind == "link_to_page":
        target = data.get(data.get("type", "")) or ""
        return f"[Linked page]({notion_link(target)})" if target else ""
    if kind in ("bookmark", "embed", "link_preview"):
        url = data.get("url", "")
        caption = inline(data.get("caption")) or url
        return f"[{caption}]({url})" if url else ""
    if kind in api.MEDIA:
        return _media(block)
    if kind == "table_row":
        cells = [inline(cell).replace("|", "\\|").replace("\n", " ") for cell in data.get("cells", [])]
        return "| " + " | ".join(cells) + " |"
    if kind in LAYOUT:
        return ""
    if "rich_text" in data:
        return inline(data.get("rich_text"))
    return f"*[unsupported block: {kind}]*"


def body(flat: list, terminal: bool = False) -> str:
    """The blocks as Markdown: lists nest under their item, a table gets its header rule, blocks are separated."""
    lines: list[str] = []
    indents: dict[int, str] = {0: ""}       # depth → indent its children use
    previous = ""                           # kind of the last block written
    table_rows = 0
    for depth, block in flat:
        kind = block.get("type", "")
        indent = indents.get(depth, indents.get(max(d for d in indents if d <= depth), ""))
        text = block_markdown(block, terminal)
        # A child of a list item sits inside the item; under anything else it cannot nest in Markdown.
        marker = LIST_KINDS.get(kind)
        indents[depth + 1] = indent + (" " * len(marker) if marker else "")
        for deeper in [d for d in indents if d > depth + 1]:
            del indents[deeper]
        if kind == "table":
            table_rows = 0
        if not text:
            continue
        tight = (kind in LIST_KINDS and previous in LIST_KINDS) or (kind == "table_row" and previous == "table_row")
        if lines and not tight:
            lines.append("")
        lines.extend(indent + line if line else "" for line in text.split("\n"))
        if kind == "table_row":
            table_rows += 1
            if table_rows == 1:   # GFM needs a header rule after the first row
                width = len(block.get("table_row", {}).get("cells", []))
                lines.append(indent + "|" + " --- |" * max(width, 1))
        previous = kind
    return "\n".join(lines)


def _yaml(value) -> str:
    """A scalar or list in YAML that any reader parses: JSON strings are valid YAML."""
    if isinstance(value, list):
        return "[" + ", ".join(json.dumps(str(v), ensure_ascii=False) for v in value) + "]"
    if isinstance(value, bool) or isinstance(value, (int, float)):
        return json.dumps(value)
    return json.dumps(str(value), ensure_ascii=False)


def document(detail: dict, value_text) -> str:
    """The whole page: front matter, title, a visible note when the read is partial, the content."""
    front = ["---", f"title: {_yaml(detail['title'])}", f"notion_id: {_yaml(detail['id'])}",
             f"url: {_yaml(detail['url'])}", f"edited: {_yaml(detail['edited'])}"]
    shown = {name: value_text(prop) for name, prop in detail["properties"].items() if prop["type"] != "title"}
    shown = {name: text for name, text in shown.items() if text}
    if shown:
        front.append("properties:")
        front += [f"  {_yaml(name)}: {_yaml(text)}" for name, text in shown.items()]
    if detail.get("in_trash"):
        front.append("in_trash: true")
    front.append("---")
    coverage = detail["coverage"]
    parts = ["\n".join(front), f"# {api.one_line(detail['title']) or 'Untitled'}"]
    if not coverage["complete"]:
        parts.append("> **Incomplete:** " + "; ".join(coverage["stopped"])
                     + f". Read {coverage['blocks']} blocks; the rest of the page is not below.")
    content = body(detail["blocks"])
    parts.append(content or "*(no content)*")
    if any(item["hosted"] for item in coverage["media"]):
        parts.append("<!-- Files hosted by Notion are temporary links: they expire about an hour after this "
                     "was read. -->")
    return "\n\n".join(parts) + "\n"
