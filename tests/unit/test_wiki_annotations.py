"""Resolve annotations even on Python versions that defer them at import."""

from typing import get_type_hints

from connectonion.wiki.files import Notebook


def test_notebook_search_annotation_uses_builtin_list_not_the_list_method():
    assert get_type_hints(Notebook.search)["return"] == list[dict]
