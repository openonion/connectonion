from pathlib import Path

ROOT = Path(__file__).parents[2]
PLUGIN_DOC = ROOT / "docs" / "claude-code-plugin.md"
VIBE_DOC = ROOT / "docs" / "vibe-coding-guide.md"
TEMPLATE_DOC = ROOT / "docs" / "templates" / "README.md"
HISTORICAL_TEMPLATE_DECISIONS = (
    ROOT / "docs" / "design-decisions" / "004-cli-create-flow.md",
    ROOT / "docs" / "design-decisions" / "010-cli-ux-progressive-disclosure.md",
)


def test_plugin_docs_use_the_published_marketplace_identity():
    pages = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (PLUGIN_DOC, VIBE_DOC)
    )

    assert "/plugin marketplace add openonion/connectonion-claude-plugin" in pages
    assert "/plugin install connectonion@connectonion-marketplace" in pages
    assert "https://github.com/openonion/connectonion-claude-plugin" in pages


def test_first_installation_reloads_the_plugin():
    plugin = PLUGIN_DOC.read_text(encoding="utf-8")
    install = plugin.split("The single-template", 1)[0]

    assert "/plugin install connectonion@connectonion-marketplace" in install
    assert "/reload-plugins" in install


def test_existing_installations_are_updated_to_the_single_template_contract():
    plugin = PLUGIN_DOC.read_text(encoding="utf-8")

    assert "1.2.0 or" in plugin
    assert "/plugin marketplace update connectonion-marketplace" in plugin
    assert "/plugin update connectonion@connectonion-marketplace" in plugin
    assert "/reload-plugins" in plugin


def test_every_build_entry_point_requires_the_corrected_plugin():
    for path in (PLUGIN_DOC, VIBE_DOC, TEMPLATE_DOC):
        text = path.read_text(encoding="utf-8")
        if "/connectonion:aaron-build-my-agent" not in text:
            continue
        assert "1.2.0" in text, path
        if path != PLUGIN_DOC:
            assert "claude-code-plugin.md#install-or-update" in text, path


def test_plugin_commands_are_namespaced_and_linked_from_the_template():
    plugin = PLUGIN_DOC.read_text(encoding="utf-8")
    template = TEMPLATE_DOC.read_text(encoding="utf-8")

    assert "/connectonion:aaron-build-my-agent" in plugin
    assert "/connectonion:aaron-review-my-code" in plugin
    assert "/connectonion:linus-review-my-code" in plugin
    assert "../claude-code-plugin.md" in template


def test_plugin_guide_follows_the_single_template_design():
    plugin = PLUGIN_DOC.read_text(encoding="utf-8")

    assert "one small, deployable `co-ai` agent" in plugin
    assert "per-template prompts" not in plugin


def test_historical_template_decisions_point_to_the_current_contract():
    for path in HISTORICAL_TEMPLATE_DECISIONS:
        decision = path.read_text(encoding="utf-8")
        prose = " ".join(decision.split())
        assert "superseded" in decision.lower(), path
        assert "[Templates](../templates/README.md)" in decision, path
        assert "one deployable `co-ai` template" in prose, path
