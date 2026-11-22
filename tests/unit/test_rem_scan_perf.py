"""Two whole-notebook scans that grew with the people count (1,352 people on the owner's notebook made
`co rem status` take about three minutes): same_person compared every pair of people, and a page build re-ran the
tag scans once per tag page. Same answers, fewer reads. Invented pages only.
"""

import random

from connectonion.rem import same_person, tag_nodes, tags
from connectonion.rem.files import Notebook


def test_same_person_finds_the_same_pairs_without_comparing_every_pair():
    rng = random.Random(7)
    first = ["Mara", "Quinn", "Ines", "Theo", "Wren", "Dee", "Ody", "Lark"]
    last = ["Ostrowski", "Harbour", "Vale", "Kiln", "Pike", "Ash"]
    roster, mapped = [], {}
    for i in range(400):
        title = rng.choice([f"{rng.choice(first)} {rng.choice(last)}", rng.choice(first), f"{rng.choice(first)} (Q)"])
        aliases = rng.sample(first + last, rng.randint(0, 2))
        emails = [f"p{i}@example.org"] if i % 5 == 0 else []
        roster.append({"path": f"people/p{i:03d}.md", "title": title, "aliases": aliases, "emails": emails})
    for i in range(0, 400, 10):
        mapped[f"p{i}@example.org"] = f"people/p{(i + 3) % 400:03d}.md"

    def tie(one, other):
        shared = [e for e in one["emails"] if mapped.get(e) == other["path"]] + [
            e for e in other["emails"] if mapped.get(e) == one["path"]]
        return bool(shared) or bool(same_person._alike(one, other))

    brute = [(i, j) for i in range(len(roster)) for j in range(i + 1, len(roster)) if tie(roster[i], roster[j])]
    close = same_person._close(roster, mapped)
    assert [(i, j) for i, j in close if tie(roster[i], roster[j])] == brute
    assert len(close) < len(roster) * (len(roster) - 1) // 2


def test_same_person_candidates_still_pair_a_shared_name_and_a_name_inside_another(tmp_path):
    book = Notebook(tmp_path)
    book.stub_person("people/mara-a.md", "Mara Ostrowski", ["mara@a.example"])
    book.stub_person("people/mara-b.md", "Mara Ostrowski", ["mara@b.example"])
    book.stub_person("people/quinn.md", "Quinn", ["q@a.example"])
    book.stub_person("people/quinn-harbour.md", "Quinn Harbour", ["qh@a.example"])
    book.stub_person("people/ines.md", "Ines Vale", ["ines@a.example"])
    pairs = {tuple(pair["pages"]) for pair in same_person.candidates(tmp_path)}
    assert ("people/mara-a.md", "people/mara-b.md") in pairs
    assert ("people/quinn-harbour.md", "people/quinn.md") in pairs
    assert not any("people/ines.md" in pair for pair in pairs)


def _tagged(tmp_path, slug):
    book = Notebook(tmp_path)
    book.write("people/mara.md", f"# Mara\n\n## Facts\n- Tags: {slug}\n- Email: mara@a.example\n")
    return book


def test_inside_one_build_each_tag_scan_reads_the_notebook_once(tmp_path, monkeypatch):
    _tagged(tmp_path, "pilot")
    calls = {"vocabulary": 0, "members": 0}
    real_vocabulary, real_members = tags._vocabulary, tag_nodes._members
    monkeypatch.setattr(tags, "_vocabulary", lambda root, records: calls.__setitem__("vocabulary", calls["vocabulary"] + 1) or real_vocabulary(root, records))
    monkeypatch.setattr(tag_nodes, "_members", lambda root: calls.__setitem__("members", calls["members"] + 1) or real_members(root))
    with tags.held(tmp_path):
        for _ in range(5):
            tags.vocabulary(tmp_path)
            tag_nodes.members(tmp_path)
    assert calls == {"vocabulary": 1, "members": 1}


def test_outside_a_build_and_after_one_the_scans_see_every_write(tmp_path):
    book = _tagged(tmp_path, "pilot")
    assert "pilot" in tags.vocabulary(tmp_path)
    with tags.held(tmp_path):
        assert "pilot" in tags.vocabulary(tmp_path)
        assert tag_nodes.members(tmp_path).get("pilot") == ["people/mara.md"]
    # The long-running Host serves many builds: an answer must not outlive the build that made it.
    book.write("people/mara.md", "# Mara\n\n## Facts\n- Tags: renewal\n- Email: mara@a.example\n")
    assert "renewal" in tags.vocabulary(tmp_path) and "pilot" not in tags.vocabulary(tmp_path)
    assert "renewal" in tag_nodes.members(tmp_path) and "pilot" not in tag_nodes.members(tmp_path)
    with tags.held(tmp_path):
        assert "renewal" in tags.vocabulary(tmp_path)


def test_a_nested_hold_keeps_the_outer_builds_answers_until_the_outer_one_ends(tmp_path):
    _tagged(tmp_path, "pilot")
    with tags.held(tmp_path):
        first = tags.vocabulary(tmp_path)
        with tags.held(tmp_path):
            assert tags.vocabulary(tmp_path) is first
        assert tags.vocabulary(tmp_path) is first   # the inner exit did not drop the outer build's memo
    assert str(tmp_path) not in tags._HELD


def test_the_census_is_read_once_per_status_and_each_caller_gets_its_own_rows(tmp_path, monkeypatch):
    from connectonion.rem import census
    book = _tagged(tmp_path, "pilot")
    reads = {"n": 0}
    real = census._pages
    monkeypatch.setattr(census, "_pages", lambda root, records=None: reads.__setitem__("n", reads["n"] + 1) or real(root, records=records))
    with tags.held(tmp_path):
        first = census.pages(tmp_path)
        first["people/mara.md"]["category"] = "edited by one caller"
        second = census.pages(tmp_path)
    assert reads["n"] == 1 and second["people/mara.md"]["category"] == "people"
    book.write("people/quinn.md", "# Quinn\n\n## Facts\n- Email: quinn@a.example\n")
    assert "people/quinn.md" in census.pages(tmp_path)   # outside a hold, a new page is seen at once
