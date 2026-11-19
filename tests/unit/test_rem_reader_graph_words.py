"""The whole network is always the knowledge graph (owner, 2026-11-19, #3140): a reader string never says
图谱 without 知识, nor "graph" without "knowledge". A point in it is a 标签 / tag; its page a 标签页 / tag page."""
import re
from pathlib import Path

READER = Path(__file__).resolve().parents[2] / "connectonion" / "rem" / "reader.html"


def _pairs():
    """Every (English, Chinese) pair the reader translates: the UI dictionary, not identifiers or CSS."""
    text = READER.read_text(encoding="utf-8")
    return re.findall(r'"((?:[^"\\]|\\.)*)":\s*"((?:[^"\\]|\\.)*[一-鿿](?:[^"\\]|\\.)*)"', text)


def test_no_chinese_string_says_tupu_without_zhishi():
    bad = [zh for _, zh in _pairs() if "图谱" in zh and "知识图谱" not in zh]
    assert not bad, bad


def test_no_english_string_says_graph_without_knowledge():
    bad = [en for en, _ in _pairs() if re.search(r"\bgraph\b", en, re.I) and not re.search(r"knowledge graph", en, re.I)]
    assert not bad, bad


def test_the_renamed_strings_are_the_knowledge_graph_words():
    found = dict(_pairs())
    assert found["Knowledge graph"] == "知识图谱"
    assert found["In the knowledge graph"] == "知识图谱（相关部分）"
    assert found["Open in the knowledge graph →"] == "在知识图谱中打开 →"
