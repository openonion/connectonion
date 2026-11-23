"""An address-titled person's display name (#3397, art director on #3429).

A local part that reads as a name becomes that name; anything else keeps the whole address, because half an
address is neither a name nor a way to reach the person. Every address below is invented.
"""
import json

import pytest
from test_rem_org_ui_integration import run_js


def name_of(address):
    return run_js(['addressName'], f"console.log(JSON.stringify(addressName({json.dumps(address)})));")


@pytest.mark.parametrize("address, name", [
    ("dana@quillmoor.example", "Dana"),
    ("john.smith@quillmoor.example", "John Smith"),
    ("john_smith@quillmoor.example", "John Smith"),
    ("mary-jane.watson@quillmoor.example", "Mary Jane Watson"),
])
def test_a_name_like_local_part_becomes_the_name(address, name):
    assert name_of(address) == name


@pytest.mark.parametrize("address", [
    "j23x@quillmoor.example", "u1234567@student.example", "xkcd@quillmoor.example", "a@quillmoor.example",
    "info@quillmoor.example", "admin@quillmoor.example", "noreply@quillmoor.example", "no-reply@quillmoor.example",
    "support@quillmoor.example",
])
def test_digits_random_strings_and_role_mailboxes_are_not_names(address):
    assert name_of(address) == ""
