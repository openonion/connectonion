"""The credential check looks at what a command reads, not the words it carries (#1494).

An unattended LinkedIn round had a comment refused as credential access: the
sentence typed into the page said "Idempotency keys catch replays". The check
matched `keys`, `secret` and `credential` anywhere in the command, so text
that was data being typed somewhere was treated as a path being opened.
"""
import pytest

from connectonion.useful_plugins.tool_approval.policy import _classify_single_command


@pytest.mark.parametrize("word", ["keys", "secret", "secrets", "credential", "credentials"])
@pytest.mark.parametrize("shape", ["{w}", '"{w} matters"'])
def test_an_ordinary_word_typed_as_data_is_not_credential_access(word, shape):
    text = shape.format(w=word)
    result = _classify_single_command(f"co browser -t t type_text_by_selector div.x {text}")
    assert result["effect_class"] != "credentials", result


@pytest.mark.parametrize(
    "command",
    [
        "co browser -t lidaily type_text_by_selector div.tiptap Idempotency keys catch replays",
        "git commit -m 'rotate credentials on deploy'",
        "echo the secret is good tests",
    ],
)
def test_a_sentence_with_credential_words_is_not_credential_access(command):
    result = _classify_single_command(command)
    assert result["effect_class"] != "credentials", result


@pytest.mark.parametrize(
    "command",
    [
        "cat .env",
        "cat config/.env.production",
        "cat ~/.aws/credentials",
        "cat secrets.yaml",
        "cat client_secret.json",
        "head deploy/credentials.json",
        "ls keys",                         # inside .co: a path-reading command names a dir
        "cat credentials",                 # inside ~/.aws
        "kubectl get secret db-password -o yaml",
        "gh secret list",
        "vault kv get secret/prod",
        "printenv",
        "security find-generic-password -s x -w",
    ],
)
def test_a_credential_shaped_value_is_still_credential_access(command):
    result = _classify_single_command(command)
    assert result["decision"] == "deny", result
    assert result["effect_class"] == "credentials", result
