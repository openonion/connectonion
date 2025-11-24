"""Test the Memory system functionality."""

import os
import shutil
import pytest
from connectonion import Memory


@pytest.fixture
def test_memory():
    """Create a Memory instance with a test directory."""
    test_dir = "test_memories_temp"
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)

    memory = Memory(memory_dir=test_dir)
    yield memory

    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)


def test_write_memory(test_memory):
    """Test writing a memory."""
    result = test_memory.write_memory("test-note", "This is a test note")
    assert "saved" in result.lower()
    assert "test-note" in result


def test_read_memory(test_memory):
    """Test reading a memory."""
    test_memory.write_memory("test-note", "This is a test note")
    result = test_memory.read_memory("test-note")
    assert "This is a test note" in result
    assert "test-note" in result


def test_read_nonexistent_memory(test_memory):
    """Test reading a memory that doesn't exist."""
    result = test_memory.read_memory("does-not-exist")
    assert "not found" in result.lower()


def test_list_memories_empty(test_memory):
    """Test listing memories when none exist."""
    result = test_memory.list_memories()
    assert "no memories" in result.lower() or "0" in result


def test_list_memories_with_content(test_memory):
    """Test listing memories with content."""
    test_memory.write_memory("note-1", "First note")
    test_memory.write_memory("note-2", "Second note")

    result = test_memory.list_memories()
    assert "note-1" in result
    assert "note-2" in result


def test_memory_persistence(test_memory):
    """Test that memories persist across instances."""
    test_memory.write_memory("persistent", "This should persist")

    new_memory = Memory(memory_dir=test_memory.memory_dir)
    result = new_memory.read_memory("persistent")
    assert "This should persist" in result


def test_invalid_key_sanitization(test_memory):
    """Test that invalid characters in keys are sanitized."""
    result = test_memory.write_memory("test@#$%note", "Content")
    assert "saved" in result.lower() or "invalid" in result.lower()

    # If saved (after sanitization)
    if "saved" in result.lower():
        result = test_memory.read_memory("testnote")
        assert "Content" in result


def test_markdown_content(test_memory):
    """Test that markdown content is preserved."""
    markdown = "# Header\n\n- Item 1\n- Item 2\n\n**Bold text**"
    test_memory.write_memory("markdown-test", markdown)

    result = test_memory.read_memory("markdown-test")
    assert "# Header" in result
    assert "**Bold text**" in result


def test_memory_directory_creation():
    """Test that memory directory is created if it doesn't exist."""
    test_dir = "test_auto_created_dir"
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)

    memory = Memory(memory_dir=test_dir)
    assert os.path.exists(test_dir)

    # Cleanup
    shutil.rmtree(test_dir)


def test_memory_with_custom_directory():
    """Test memory with custom directory path."""
    custom_dir = "custom_memories"
    if os.path.exists(custom_dir):
        shutil.rmtree(custom_dir)

    memory = Memory(memory_dir=custom_dir)
    memory.write_memory("custom-test", "Custom content")

    assert os.path.exists(os.path.join(custom_dir, "custom-test.md"))

    result = memory.read_memory("custom-test")
    assert "Custom content" in result

    # Cleanup
    shutil.rmtree(custom_dir)


def test_search_memory(test_memory):
    """Test searching across memories with regex."""
    test_memory.write_memory("alice-notes", "Alice prefers email communication\nAlice works at TechCorp")
    test_memory.write_memory("bob-notes", "Bob prefers phone calls\nBob is from Marketing")
    test_memory.write_memory("project-x", "Project X requires Alice and Bob collaboration")

    # Search for Alice
    result = test_memory.search_memory("Alice")
    assert "alice-notes" in result
    assert "project-x" in result
    assert "email communication" in result or "Alice" in result

    # Search for "prefers" - should match both alice and bob
    result = test_memory.search_memory("prefers")
    assert "alice-notes" in result
    assert "bob-notes" in result


def test_search_memory_case_sensitive(test_memory):
    """Test case-sensitive search using regex flags."""
    test_memory.write_memory("test", "This has UPPERCASE and lowercase")

    # Case-insensitive with (?i) flag
    result = test_memory.search_memory("(?i)uppercase")
    assert "matches" in result.lower() or "UPPERCASE" in result

    # Case-sensitive (default without flag)
    result = test_memory.search_memory("uppercase")
    assert "no matches" in result.lower()


def test_search_memory_regex_pattern(test_memory):
    """Test regex patterns in search."""
    test_memory.write_memory("contacts", "Email: alice@example.com\nEmail: bob@test.org")

    # Regex pattern for email addresses
    result = test_memory.search_memory(r"\w+@\w+\.\w+")
    assert "contacts" in result
    assert "alice@example.com" in result or "bob@test.org" in result


def test_search_memory_empty(test_memory):
    """Test search with no memories."""
    result = test_memory.search_memory("anything")
    assert "no memories" in result.lower()
