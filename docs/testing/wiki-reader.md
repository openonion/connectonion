# Offline Wiki reader acceptance

The reader remains a self-contained HTML snapshot opened through `file://`.
It uses system fonts, inline CSS/JavaScript, and no remote assets or new dependencies.
Notebook Markdown and reader.py storage/serialization behavior are unchanged.

## Behavior

- Below 821px, **Browse notebook** expands the category list. Enter/Space toggles
  it; Escape closes it and returns keyboard focus from navigation to the button.
  Choosing a category closes the menu. Desktop navigation remains visible.
- ASCII diagrams and code keep their whitespace and scroll inside their block.
  Tables, including maintenance history, scroll within their own region. Long
  inline identifiers, paths and source labels wrap without widening the page.
- Backtick and tilde fences preserve literal Sources:/Related: lines and blank
  lines, including fences nested in lists. Nested ordered/unordered lists retain
  their hierarchy. Code is escaped rather than executed.
- Same-page and cross-page Markdown heading links scroll to their targets.
  Repeated heading IDs receive numeric suffixes. Opening a search result clears
  the query field; browser Back restores the search query and results.

## Reproduce

```bash
python -m pytest tests/unit/test_wiki_reader.py -q
CO_WIKI_BROWSER_TEST=1 CO_WIKI_SHOTS=/tmp/wiki-reader-shots python -m pytest tests/e2e/cli/test_wiki_reader_browser.py -q
```

The opt-in browser test needs installed Chrome and the existing patchright
package. All inputs are synthetic. It checks 375×812, 768×1024 and 1440×1000
viewports; keyboard/ARIA menu behavior and resizing; local overflow boundaries;
heading target positions; search/history; code whitespace; nested lists; inert
markup; and zero HTTP(S) page requests. Screenshots are optional local artifacts.

This is a small Markdown subset, not a complete CommonMark implementation.
Tab-indented list markers fall back to text rather than crashing. Real mobile
hardware, Safari and Firefox are not covered by this Chrome acceptance suite.
