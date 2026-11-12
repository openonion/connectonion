"""D-103: REM's languages are the ones the owner writes, detected. Fictional people only."""
from connectonion.rem import translate
from connectonion.rem.config import default_config, prepare, read_config, set_config
from connectonion.rem.files import Notebook, state_path, write_json
from connectonion.rem.languages import owner_languages


def _detected(root, languages):
    write_json(state_path(root, 'map.json'), {'owner': {'record': 'people/me.md', 'addresses': ['me@example.test'],
               'languages': {'languages': languages, 'shares': {}, 'messages': 40, 'english_terms': []}}})


def test_an_empty_languages_setting_translates_into_every_detected_language(tmp_path):
    prepare(tmp_path)
    assert default_config()['languages'] == [] and read_config(tmp_path)['languages'] == []
    Notebook(tmp_path).write('people/fern.md', '# Fern Vale\n\nFern runs the pilot.\n')
    _detected(tmp_path, ['zh', 'en'])
    assert translate.languages(tmp_path) == ['zh', 'en']
    assert owner_languages(tmp_path)['languages'] == ['zh', 'en']  # the reader offers the same two
    assert translate.backlog(tmp_path, 'zh') == ['people/fern.md']
    assert translate.coverage(tmp_path)['zh']['requested'] is True


def test_a_configured_list_still_wins(tmp_path):
    prepare(tmp_path)
    _detected(tmp_path, ['zh', 'en'])
    set_config(tmp_path, ['languages', 'ja,en'])
    assert translate.languages(tmp_path) == ['ja', 'en']


def test_nothing_detected_yet_means_nothing_to_translate(tmp_path):
    prepare(tmp_path)
    assert translate.languages(tmp_path) == []
