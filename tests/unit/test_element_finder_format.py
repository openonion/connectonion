"""Unit tests for connectonion/useful_tools/browser_tools/element_finder.py format_elements_for_llm.

This is the format consumed by a vision LLM for element matching — format stability
is load-bearing for the model's ability to pick correct elements.
"""

from connectonion.useful_tools.browser_tools.element_finder import (
    InteractiveElement,
    format_elements_for_llm,
)


def _el(**overrides):
    """Build an InteractiveElement with sensible defaults, override specific fields."""
    defaults = dict(index=0, tag='div', x=0, y=0)
    defaults.update(overrides)
    return InteractiveElement(**defaults)


# ---------- empty / minimal ----------

def test_empty_list_returns_empty_string():
    assert format_elements_for_llm([]) == ""


def test_minimal_element_shows_index_tag_and_position():
    line = format_elements_for_llm([_el(index=3, tag='button', x=10, y=20)])
    assert line == "[3] button pos=(10,20)"


def test_multiple_elements_one_per_line():
    out = format_elements_for_llm([
        _el(index=0, tag='a', x=1, y=2),
        _el(index=1, tag='button', x=3, y=4),
    ])
    assert out.split('\n') == [
        "[0] a pos=(1,2)",
        "[1] button pos=(3,4)",
    ]


# ---------- optional attributes ----------

def test_text_appears_quoted_after_tag():
    line = format_elements_for_llm([_el(index=0, tag='button', text='Submit', x=5, y=5)])
    assert '"Submit"' in line
    # text comes before placeholder/aria/pos
    assert line.index('"Submit"') < line.index('pos=')


def test_placeholder_always_shown_when_present():
    line = format_elements_for_llm([_el(index=0, tag='input', placeholder='Email')])
    assert 'placeholder="Email"' in line


def test_aria_label_always_shown_when_present():
    line = format_elements_for_llm([_el(index=0, tag='button', aria_label='Close dialog')])
    assert 'aria="Close dialog"' in line


def test_input_type_appears_as_type_kv():
    line = format_elements_for_llm([_el(index=0, tag='input', input_type='password')])
    assert 'type=password' in line


def test_role_appears_when_present():
    line = format_elements_for_llm([_el(index=0, tag='div', role='checkbox')])
    assert 'role=checkbox' in line


def test_icon_metadata_appears_when_present():
    line = format_elements_for_llm([_el(
        index=2,
        tag='div',
        title='QR code',
        alt='scan login',
        element_id='qr-switch',
        class_name='qr-login-switch icon-qrcode',
        data_attrs='data-testid=qr-login',
        x=1618,
        y=430,
        width=42,
        height=42,
    )])
    assert 'title="QR code"' in line
    assert 'alt="scan login"' in line
    assert 'id="qr-switch"' in line
    assert 'class="qr-login-switch icon-qrcode"' in line
    assert 'data="data-testid=qr-login"' in line
    assert 'size=42x42' in line


def test_size_only_shown_for_elements_without_text():
    with_text = _el(index=0, tag='button', text='Login', width=100, height=40)
    without_text = _el(index=1, tag='div', class_name='icon-menu', width=24, height=24)

    lines = format_elements_for_llm([with_text, without_text]).split('\n')

    assert 'size=' not in lines[0]
    assert 'size=24x24' in lines[1]


# ---------- href truncation ----------

def test_href_strips_query_string():
    line = format_elements_for_llm([_el(
        index=0, tag='a', href='https://example.com/path?q=1&r=2'
    )])
    # query string dropped
    assert '?' not in line
    assert 'q=1' not in line


def test_href_truncated_to_last_30_chars():
    long = 'https://example.com/very/long/path/that/exceeds/thirty/chars'
    line = format_elements_for_llm([_el(index=0, tag='a', href=long)])
    # Extract the href=... segment
    href_part = [p for p in line.split() if p.startswith('href=')][0]
    payload = href_part[len('href=...'):]
    assert len(payload) <= 30
    assert payload == long[-30:]


# ---------- frame context ----------

def test_main_frame_is_implicit_not_shown():
    line = format_elements_for_llm([_el(index=0, tag='div', frame='main')])
    assert 'frame=' not in line


def test_iframe_frame_shown_as_kv():
    line = format_elements_for_llm([_el(index=0, tag='div', frame='scormContent')])
    assert 'frame=scormContent' in line


# ---------- combination ----------

def test_full_element_renders_all_fields():
    line = format_elements_for_llm([_el(
        index=7,
        tag='input',
        text='',
        placeholder='Search',
        aria_label='Site search',
        input_type='search',
        role='searchbox',
        x=100, y=50,
        frame='topbar',
    )])
    assert '[7]' in line
    assert 'input' in line
    assert 'placeholder="Search"' in line
    assert 'aria="Site search"' in line
    assert 'pos=(100,50)' in line
    assert 'type=search' in line
    assert 'role=searchbox' in line
    assert 'frame=topbar' in line
