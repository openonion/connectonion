# co rem README screenshots

Real Chrome captures of the reader in this repository, populated with the
invented notebook in `tests/fixtures/rem_reader_notebook.py` (with its cached
Chinese translations for the 中文 shots). Names, roles and sources are
examples, not private account data or a claim about the quality of an
unattended run.

Regenerate them all with:

    python scripts/capture_rem_reader.py --readme docs/assets/rem-readme

- `reader-desktop.png`, `reader-phone.png`: the morning brief, English, light;
  desktop 1440 × 1000 at scale 1, phone 390 × 844 at scale 2.
- `tour-*.png`: a person's page (dark, desktop), the morning brief in 中文,
  the People table, Open threads on a phone (dark) and a person's page on a
  phone in 中文.
- Network requests are blocked during capture; no UI text or layout is
  altered for the screenshots.

The README uses a native HTML picture element so phones get legible mobile UI.
