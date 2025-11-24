"""Interactive test for DiffWriter, pick, and yes_no.

Run this file directly to test:
    python tests/test_diff_writer.py
"""

import tempfile
import os
from pathlib import Path

from connectonion import pick, yes_no, DiffWriter


def test_pick_list():
    """Test pick with list options."""
    print("\n=== Testing pick() with list ===")
    choice = pick("Pick a fruit", ["Apple", "Banana", "Cherry"])
    print(f"You picked: {choice}")


def test_pick_dict():
    """Test pick with dict options."""
    print("\n=== Testing pick() with dict ===")
    choice = pick("What to do?", {
        "c": "Continue",
        "r": "Retry",
        "q": "Quit",
    })
    print(f"You chose: {choice}")


def test_yes_no():
    """Test yes_no dialog."""
    print("\n=== Testing yes_no() ===")
    ok = yes_no("Are you sure?")
    print(f"Confirmed: {ok}")


def test_new_file_approval():
    """Test approval UI for new file."""
    print("\n=== Testing New File Approval ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        writer = DiffWriter(auto_approve=False)
        test_file = os.path.join(tmpdir, "hello.py")

        content = '''def hello():
    print("Hello, World!")

if __name__ == "__main__":
    hello()
'''

        print(f"Creating new file: {test_file}")
        result = writer.write(test_file, content)
        print(f"\nResult: {result}")

        if Path(test_file).exists():
            print(f"File created!")
        else:
            print("File was not created (rejected)")


def test_modify_file_approval():
    """Test approval UI for modifying existing file."""
    print("\n=== Testing File Modification Approval ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "hello.py")

        original = '''def hello():
    pass
'''
        Path(test_file).write_text(original)
        print(f"Created initial file: {test_file}")

        writer = DiffWriter(auto_approve=False)

        new_content = '''def hello():
    print("Hello, World!")

def goodbye():
    print("Goodbye!")
'''

        print("Proposing changes...")
        result = writer.write(test_file, new_content)
        print(f"\nResult: {result}")


if __name__ == "__main__":
    print("=" * 50)
    print("pick / yes_no / DiffWriter Test")
    print("=" * 50)

    tests = {
        "1": ("Test pick() with list", test_pick_list),
        "2": ("Test pick() with dict", test_pick_dict),
        "3": ("Test yes_no()", test_yes_no),
        "4": ("Test new file approval", test_new_file_approval),
        "5": ("Test file modification approval", test_modify_file_approval),
        "q": ("Quit", None),
    }

    while True:
        choice = pick("Select a test", {k: v[0] for k, v in tests.items()})

        if choice == "q":
            print("Bye!")
            break

        func = tests[choice][1]
        if func:
            func()
