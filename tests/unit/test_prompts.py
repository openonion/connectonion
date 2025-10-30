"""Test system prompt loading functionality."""

import os
import tempfile
import pytest
from pathlib import Path
from connectonion.prompts import load_system_prompt, DEFAULT_PROMPT


class TestLoadSystemPrompt:
    """Test the load_system_prompt function."""
    
    def test_none_returns_default(self):
        """Test that None returns the default prompt."""
        result = load_system_prompt(None)
        assert result == DEFAULT_PROMPT
        assert "helpful assistant" in result
    
    def test_direct_string_prompt(self):
        """Test passing a direct string as prompt."""
        prompt = "You are a coding assistant"
        result = load_system_prompt(prompt)
        assert result == prompt
    
    def test_string_that_looks_like_path_but_isnt(self):
        """Test strings that might look like paths but aren't files."""
        prompts = [
            "config/setup",
            "prompts/assistant",
            "Be helpful with math/science topics"
        ]
        for prompt in prompts:
            result = load_system_prompt(prompt)
            assert result == prompt  # Treated as literal
    
    def test_load_from_file_path_string(self):
        """Test loading from a file path passed as string."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            content = "# Assistant\nYou are a helpful AI assistant."
            f.write(content)
            temp_path = f.name
        
        try:
            result = load_system_prompt(temp_path)
            assert result == content
        finally:
            os.unlink(temp_path)
    
    def test_load_from_path_object(self):
        """Test loading from a Path object."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            content = "You are an expert programmer."
            f.write(content)
            temp_path = Path(f.name)
        
        try:
            result = load_system_prompt(temp_path)
            assert result == content
        finally:
            temp_path.unlink()
    
    def test_file_without_extension(self):
        """Test loading from a file without extension."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='', delete=False) as f:
            content = "Custom prompt content"
            f.write(content)
            temp_path = f.name
        
        try:
            # As string
            result = load_system_prompt(temp_path)
            assert result == content
            
            # As Path
            result = load_system_prompt(Path(temp_path))
            assert result == content
        finally:
            os.unlink(temp_path)
    
    def test_various_file_extensions(self):
        """Test loading from files with different extensions."""
        extensions = ['.md', '.txt', '.prompt', '.yaml', '.json', '.custom']
        content = "Test prompt content"
        
        for ext in extensions:
            with tempfile.NamedTemporaryFile(mode='w', suffix=ext, delete=False) as f:
                f.write(content)
                temp_path = f.name
            
            try:
                result = load_system_prompt(temp_path)
                assert result == content
            finally:
                os.unlink(temp_path)
    
    def test_path_object_file_not_found(self):
        """Test Path object pointing to non-existent file."""
        path = Path("/nonexistent/file.md")
        with pytest.raises(FileNotFoundError) as exc_info:
            load_system_prompt(path)
        assert "not found" in str(exc_info.value)
    
    def test_path_object_is_directory(self):
        """Test Path object pointing to a directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            with pytest.raises(ValueError) as exc_info:
                load_system_prompt(path)
            assert "not a file" in str(exc_info.value)
    
    def test_empty_file_raises_error(self):
        """Test that empty files raise an error."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("")  # Empty file
            temp_path = f.name
        
        try:
            with pytest.raises(ValueError) as exc_info:
                load_system_prompt(temp_path)
            assert "empty" in str(exc_info.value).lower()
            
            # Also test with Path object
            with pytest.raises(ValueError):
                load_system_prompt(Path(temp_path))
        finally:
            os.unlink(temp_path)
    
    def test_whitespace_only_file_raises_error(self):
        """Test that files with only whitespace raise an error."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("   \n\t  \n  ")  # Only whitespace
            temp_path = f.name
        
        try:
            with pytest.raises(ValueError) as exc_info:
                load_system_prompt(temp_path)
            assert "empty" in str(exc_info.value).lower()
        finally:
            os.unlink(temp_path)
    
    def test_binary_file_with_invalid_utf8(self):
        """Test that files with invalid UTF-8 raise an appropriate error."""
        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
            # Write invalid UTF-8 bytes
            f.write(b'\xff\xfe\xfd\xfc')  
            temp_path = f.name
        
        try:
            with pytest.raises(ValueError) as exc_info:
                load_system_prompt(temp_path)
            assert "UTF-8" in str(exc_info.value) or "text file" in str(exc_info.value)
        finally:
            os.unlink(temp_path)
    
    def test_invalid_type_raises_error(self):
        """Test that invalid types raise an error."""
        with pytest.raises(TypeError):
            load_system_prompt(123)  # Integer
        
        with pytest.raises(TypeError):
            load_system_prompt([])  # List
        
        with pytest.raises(TypeError):
            load_system_prompt({"prompt": "test"})  # Dict
    
    def test_strips_whitespace_from_file(self):
        """Test that whitespace is stripped from file content."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("\n\n  Prompt content  \n\n")
            temp_path = f.name
        
        try:
            result = load_system_prompt(temp_path)
            assert result == "Prompt content"
        finally:
            os.unlink(temp_path)
    
    def test_hidden_file(self):
        """Test loading from a hidden file (starts with dot)."""
        with tempfile.NamedTemporaryFile(mode='w', prefix='.', delete=False) as f:
            content = "Hidden prompt"
            f.write(content)
            temp_path = f.name
        
        try:
            result = load_system_prompt(temp_path)
            assert result == content
        finally:
            os.unlink(temp_path)