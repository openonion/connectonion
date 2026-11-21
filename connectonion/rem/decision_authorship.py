"""Check captured decision speakers against local originals, and that the page does not admit
it has no alternative or reason, without a model or fetch."""

import re
import sqlite3

from .files import is_address, state_path
from .languages import own_words
from .mail import _address
from .page_review import _quote_bindings, _quoted_in
from .project_material import retained_session
from .reader_model import _cited_row
from .source import parse_session_source
from .store_messages import archived_message, owner_addresses

UNVERIFIED = '- Speaker unverified.'

# A short list on purpose: the page's own sentence saying its alternative or reason is
# unknown or inferred. Within one clause, so an unknown about something else does not match.
_BASIS = r'(?:alternatives?|reasons?|rationale)'
ADMITS = re.compile(
    rf'(?i)\b{_BASIS}\b[^.;\n]{{0,40}}\b(?:unknown|unclear|inferred|not (?:stated|recorded|captured|known|given))\b'
    rf'|\b(?:unknown|unstated|inferred|no (?:stated|recorded))\b[^.;\n]{{0,20}}\b{_BASIS}\b')


def admitted_gaps(text):
    """Refuse a decision page whose own body says the alternative or the reason is unknown or inferred.

    2026-11-16: 15 of 66 new decision pages said so and passed, because review only asked
    who spoke the quote. A choice with no known alternative or reason is not a decision."""
    found = ADMITS.search(text.partition('\n## Sources\n')[0])
    if not found:
        return []
    return [f'Decision page says its alternative or reason is unknown or inferred ("{found[0]}"); that is not a '
            'decision: delete this page and give its captured line `VERDICT <line id> not-a-decision`, '
            'or state the rejected alternative and the reason from the supplied pages']


def _original(root, db, source, owner):
    row = _cited_row(db, source) if db is not None else None
    saved = archived_message(root, dict(row)) if row is not None else None
    if parse_session_source(source):
        if saved is None:
            saved = retained_session(root, source)
        if saved is not None and isinstance(saved.get('text'), str):
            role = saved.get('role', 'user')  # Both session stores file owner input only.
            author = {'user': 'owner', 'assistant': 'other'}.get(role, 'unverified')
            return saved['text'], author, saved
    if saved is not None and row['source'] in ('gmail', 'outlook') and isinstance(saved.get('body'), str):
        body = saved['body']
        if '--- Email Body ---' in body:
            body = body.partition('--- Email Body ---')[2]
        header = saved.get('from') or row['sender'] or ''
        sender = _address(header) if isinstance(header, str) else ''
        author = ('owner' if sender in owner else 'other') if is_address(sender) and owner else 'unverified'
        return body, author, saved
    return None


def _speaker(words, original):
    if original is None:
        return 'unverified'
    body, author, saved = original
    # An email's sender did not author the thread quoted below the new reply.
    authored = own_words(body) if 'body' in saved else body
    if _quoted_in(words, authored):
        return author
    if _quoted_in(words, body) or saved.get('truncated') or '[truncated by co rem:' in body:
        return 'unverified'
    return 'absent'


def _uncertainty(text, unverified):
    """Use the notebook's existing Uncertainties section, keeping one short line."""
    text = re.sub(r'(?m)^' + re.escape(UNVERIFIED) + r'\n?', '', text)
    section = re.search(r'(?ms)^## Uncertainties\n(.*?)(?=^## |\Z)', text)
    if unverified:
        if section:
            body = section[1].rstrip()
            return text[:section.start(1)] + (body + '\n' if body else '') + UNVERIFIED + '\n\n' + text[section.end():]
        head, separator, tail = text.partition('\n## Sources\n')
        return head.rstrip() + '\n\n## Uncertainties\n' + UNVERIFIED + '\n' + separator + tail
    if section and not section[1].strip():
        return text[:section.start()] + text[section.end():]
    return text


def review(root, text):
    """Refuse known other speakers and contradicted quotes; label unresolved speakers."""
    path = state_path(root, 'rem.db')
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) if path.is_file() else None
    if db is not None:
        db.row_factory = sqlite3.Row
    errors, unverified = [], False
    owner, originals = owner_addresses(root), {}
    try:
        for words, binding in _quote_bindings(text):
            speakers = set()
            for source in binding or ():
                if source not in originals:
                    originals[source] = _original(root, db, source, owner)
                speakers.add(_speaker(words, originals[source]))
            if 'other' in speakers:
                errors.append('Decision quote was not authored by the owner; the cited original identifies another speaker')
            elif 'owner' not in speakers:
                if speakers and speakers == {'absent'}:
                    errors.append("Decision quote is not in the owner's cited original; captured wording does not establish authorship")
                else:
                    unverified = True
    finally:
        if db is not None:
            db.close()
    return _uncertainty(text, unverified), list(dict.fromkeys(errors))
