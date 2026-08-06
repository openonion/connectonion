"""Every non-Latin prompt writes to the same eval file.

`_slugify` keeps `[a-zA-Z0-9]` and turns everything else into an underscore, so
a prompt written in Chinese, Japanese, Korean, Russian, Greek or Arabic reduces
to nothing and falls back to the literal name `default`:

    '写一个爬虫'        -> 'default'
    '分析销售数据'       -> 'default'
    '日本語のテスト'      -> 'default'
    'Привет мир'      -> 'default'
    '帮我看一下这个 bug'  -> 'bug'

logger.py promises the opposite, one line above where the slug is used:

    writes to .co/evals/{input_slug}.yaml (one file per unique first input)

For anyone not writing prompts in English that is one file for *every* input:
`.co/evals/default.yaml` and `.co/evals/default/run_N.yaml`, with unrelated runs
accumulating in each other. The last example is worse in a quieter way — two
unrelated Chinese prompts that both happen to mention "bug" land in `bug.yaml`
together, and the name describes neither.

The user this was found on writes prompts in Chinese.

## Not a traversal

Dots and slashes are not word characters either way:

    '../../etc/passwd' -> 'etc_passwd'

so widening to Unicode word characters keeps that property — checked below,
because the reason a character class is narrow is often that someone was
guarding something with it.
"""

import pytest

from connectonion.logger import _slugify


class TestANonLatinPromptKeepsItsOwnName:

    @pytest.mark.parametrize(
        "prompt",
        ["写一个爬虫", "分析销售数据", "日本語のテスト", "Привет мир", "간단한 테스트"],
    )
    def test_it_is_not_called_default(self, prompt):
        assert _slugify(prompt) != "default", (
            f"{prompt!r} shares one eval file with every other non-Latin prompt"
        )

    @pytest.mark.parametrize(
        "one,two",
        [
            ("写一个爬虫", "分析销售数据"),
            ("日本語のテスト", "Привет мир"),
            ("帮我看一下这个 bug", "修复这个 bug"),
        ],
    )
    def test_two_different_prompts_do_not_collide(self, one, two):
        assert _slugify(one) != _slugify(two)

    def test_a_mixed_prompt_keeps_both_halves(self):
        slug = _slugify("帮我看一下这个 bug")

        assert "bug" in slug
        assert "帮" in slug


class TestTheEnglishBehaviourIsUnchanged:

    @pytest.mark.parametrize(
        "prompt,expected",
        [
            ("Reply with exactly ok", "reply_with_exactly_ok"),
            ("Fix the CI failure", "fix_the_ci_failure"),
            ("Hello, world!", "hello_world"),
        ],
    )
    def test_it_slugs_as_before(self, prompt, expected):
        assert _slugify(prompt) == expected

    def test_empty_input_is_still_default(self):
        assert _slugify("   ") == "default"

    def test_punctuation_only_is_still_default(self):
        assert _slugify("!!! ???") == "default"

    def test_emoji_only_is_still_default(self):
        """Not word characters in any script."""
        assert _slugify("🎉🎉") == "default"


class TestItIsStillAFilename:

    @pytest.mark.parametrize(
        "hostile",
        ["../../etc/passwd", "..\\..\\windows\\system32", "/absolute/path",
         "with/slash", "with\\backslash", "nul", "a:b"],
    )
    def test_no_separator_survives(self, hostile):
        slug = _slugify(hostile)

        for character in ("/", "\\", ":", ".."):
            assert character not in slug

    def test_it_is_bounded(self):
        assert len(_slugify("字" * 500)) <= 50

    def test_a_long_latin_prompt_is_bounded(self):
        assert len(_slugify("word " * 200)) <= 50

    def test_it_never_returns_empty(self):
        for text in ("", " ", "///", "...", "\n\t"):
            assert _slugify(text)
