"""A page read in another language: a cached co ai translation, never the page.

The Markdown page stays the one canonical record. A translation lives at
`.state/translations/<language>/<record>` and starts with a line naming the
record and the hash of the text it was made from; once the page changes, the
hash no longer matches and the translation is stale, so it is made again on the
next request instead of being shown.
"""

import hashlib
import re
import shutil
import tempfile
from pathlib import Path

from .config import LANGUAGE
from .files import Notebook, RemError, atomic_write, state_path

HEADER = re.compile(r"<!-- co rem translation of (\S+) sha256:([0-9a-f]{64}) -->\n")
CITATION = re.compile(r"\[(W?\d{1,3})\]")
# English phrases the reader parses inside prose; translated, a closed thread reads as open.
MARKERS = ("Unknown", "None as of", "Nothing open as of", "Now:", "Changed:", "At stake:", "Pattern:")
# The page's last line, which the reader reads for its status. Not prose: it is
# never sent to the model (Codex translated its label) and is put back as written.
STAMP = re.compile(r"^Investigation:[^\n]*$", re.M)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def checked_language(language: str) -> str:
    if not isinstance(language, str) or not LANGUAGE.fullmatch(language):
        raise RemError("language must be a language tag such as en, zh, zh-TW or ja")
    return language


def translation_path(root: Path, record: str, language: str) -> Path:
    return state_path(root, f"translations/{checked_language(language)}/{record}")


def cached(root: Path, record: str, language: str) -> str | None:
    """The translation of the page as it is now, or None when missing or stale."""
    path = translation_path(root, record, language)
    if not path.is_file():
        return None
    saved = path.read_text(encoding="utf-8")
    match = HEADER.match(saved)
    if not match or match.group(2) != digest(Notebook(root).read(record)):
        return None
    return saved[match.end():]


def cached_languages(root: Path, record: str) -> dict[str, str]:
    """{language: text} for every translation of this record that is still current."""
    directory = state_path(root, "translations")
    if not directory.is_dir():
        return {}
    found = {}
    for language in sorted(path.name for path in directory.iterdir() if LANGUAGE.fullmatch(path.name)):
        text = cached(root, record, language)
        if text is not None:
            found[language] = text
    return found


def prompt(language: str) -> str:
    from .runner import language_rules
    return ("Translate page.md, a Markdown notebook page, into the language tagged "
            f"`{language}` and write the result to translation.md in this folder. Do not edit "
            "page.md and do not read anything else. Translate the prose only: add nothing, drop "
            "nothing, keep every line's Markdown, every link target and every source id like [3] "
            "where it is." + language_rules() + "These stay in English even mid-sentence: "
            "`Nothing open as of 2026-09-29; Jordan canceled` becomes `Nothing open as of 2026-09-29；"
            "Jordan 取消了` in Chinese. Then reply DONE.")


def checked(original: str, translation: str) -> str:
    """What the reader parses must survive: headings, cited sources and markers."""
    headings = [line for line in original.splitlines() if line.startswith("#")]
    if [line for line in translation.splitlines() if line.startswith("#")] != headings:
        raise RemError("The translation changed the page's headings; nothing was cached. Translate again")
    if sorted(CITATION.findall(translation)) != sorted(CITATION.findall(original)):
        raise RemError("The translation changed the page's source ids; nothing was cached. Translate again")
    for marker in MARKERS:
        if translation.count(marker) < original.count(marker):
            raise RemError(f"The translation dropped `{marker}`, which the reader reads; nothing was cached. "
                           "Translate again")
    return translation


def translate(root: Path, record: str, language: str) -> str:
    """The cached translation when current, else one co ai turn on the notebook's runner."""
    from .config import read_config
    from .runner import ready, run_task
    text = Notebook(root).read(record)
    if (hit := cached(root, record, language)) is not None:
        return hit
    config = read_config(root)
    problem, fix = ready(config)
    if problem:
        raise RemError(f"{problem}; run `{fix}` and translate again")
    tasks = state_path(root, "tasks")
    tasks.mkdir(parents=True, exist_ok=True, mode=0o700)
    workspace = Path(tempfile.mkdtemp(prefix="translate-", dir=tasks))
    prose, stamp = STAMP.sub("", text).rstrip() + "\n", STAMP.search(text)
    (workspace / "page.md").write_text(prose, encoding="utf-8")
    run_task(workspace, prompt(language), config, "abstract")
    output = workspace / "translation.md"
    answer = output.read_text(encoding="utf-8").strip() if output.is_file() else ""
    shutil.rmtree(workspace)
    if not answer:
        raise RemError("co ai finished without writing a translation; nothing was cached. Translate again")
    translation = checked(prose, answer + "\n") + (f"\n{stamp.group(0)}\n" if stamp else "")
    atomic_write(translation_path(root, record, language),
                 f"<!-- co rem translation of {record} sha256:{digest(text)} -->\n" + translation)
    return translation
