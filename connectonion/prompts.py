"""
Purpose: Load and validate system prompts from files or strings with intelligent path detection
LLM-Note:
  Dependencies: imports from [os, warnings, pathlib, typing] | imported by [agent.py] | no dedicated tests found
  Data flow: receives system_prompt: Union[str, Path, None] from Agent.__init__ → checks if None (returns DEFAULT_PROMPT) → checks if Path object (reads file) → checks if str exists as file (reads) → warns if looks like file but doesn't exist → returns literal string
  State/Effects: reads text files if path provided | emits UserWarning if path looks like file but doesn't exist | no writes or global state
  Integration: exposes load_system_prompt(prompt), DEFAULT_PROMPT constant | used by Agent to load system prompts from various sources | supports .md, .txt, .prompt file extensions | Path objects enforce file must exist
  Performance: file I/O only when path provided | heuristic checks (file extension, path separators) are fast string operations
  Errors: raises FileNotFoundError if Path doesn't exist | raises ValueError if Path is not a file or file is empty | raises ValueError if file not UTF-8 | warns (doesn't fail) for str that looks like missing file
"""

import os
import warnings
from pathlib import Path
from typing import Union


DEFAULT_PROMPT = "You are a helpful assistant that can use tools to complete tasks."


def _looks_like_file_path(text: str) -> bool:
    """Check if a string looks like a file path rather than prompt text."""
    # Check for file extensions
    has_file_extension = '.' in text and text.split('.')[-1] in ['md', 'txt', 'prompt']
    # Check for path separators
    has_path_separator = '/' in text or '\\' in text

    return has_file_extension or has_path_separator


def _warn_if_missing_file(prompt: str) -> None:
    """Warn user if prompt looks like a file path but doesn't exist."""
    if _looks_like_file_path(prompt) and not os.path.exists(prompt):
        abs_path = os.path.abspath(prompt)
        cwd = os.getcwd()

        # Suggest better approach
        suggestion = ""
        if '/' in prompt or '\\' in prompt:
            # Has path separators, suggest Path object
            suggestion = f"\n  Tip: Use Path object for explicit file loading: Path('{prompt}')"
        else:
            # Just filename, suggest correct directory or Path
            suggestion = (f"\n  Tip: Either run from the correct directory, or use absolute path:\n"
                         f"       Path(__file__).parent / '{prompt}'")

        warnings.warn(
            f"'{prompt}' looks like a file path but doesn't exist.\n"
            f"  Looked in: {abs_path}\n"
            f"  Current directory: {cwd}\n"
            f"  Treating as literal prompt text."
            f"{suggestion}",
            UserWarning,
            stacklevel=3
        )


def load_system_prompt(prompt: Union[str, Path, None]) -> str:
    """
    Load system prompt from various sources.
    
    Args:
        prompt: Can be:
            - None: Returns default prompt
            - str: Either a file path (if file exists) or literal prompt text
            - Path: Path object to a text file
            
    Returns:
        str: The loaded system prompt
        
    Examples:
        >>> load_system_prompt(None)
        'You are a helpful assistant that can use tools to complete tasks.'
        
        >>> load_system_prompt("You are a helpful assistant")
        'You are a helpful assistant'
        
        >>> load_system_prompt("prompts/assistant.md")  # If file exists
        # Returns content from the file
        
        >>> load_system_prompt(Path("prompts/assistant"))  # Any text file
        # Returns content from the file
        
    Raises:
        FileNotFoundError: If a Path object points to non-existent file
        ValueError: If file is empty or not valid UTF-8 text
    """
    if prompt is None:
        return DEFAULT_PROMPT
    
    if isinstance(prompt, Path):
        # Explicit Path object - must exist
        if not prompt.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt}")
        if not prompt.is_file():
            raise ValueError(f"Path is not a file: {prompt}")
        return _read_text_file(prompt)
    
    if isinstance(prompt, str):
        # Check if it's an existing file
        if os.path.exists(prompt) and os.path.isfile(prompt):
            return _read_text_file(Path(prompt))

        # Warn if it looks like a missing file
        _warn_if_missing_file(prompt)

        # Treat as literal prompt text
        return prompt
    
    raise TypeError(f"Invalid prompt type: {type(prompt).__name__}. Expected str, Path, or None.")


def _read_text_file(path: Path) -> str:
    """
    Read content from a text file.
    
    Args:
        path: Path to the text file
        
    Returns:
        str: File content
        
    Raises:
        ValueError: If file is empty or not valid UTF-8
    """
    try:
        content = path.read_text(encoding='utf-8').strip()
        if not content:
            raise ValueError(f"Prompt file '{path}' is empty. Please add content or use a different file.")
        return content
    except UnicodeDecodeError:
        raise ValueError(
            f"File '{path}' is not a valid UTF-8 text file. "
            f"System prompts must be text files."
        )
    except ValueError:
        # Re-raise ValueError (empty file)
        raise
    except PermissionError:
        # Re-raise PermissionError
        raise
    except Exception as e:
        # Catch any other unexpected errors
        raise RuntimeError(f"Error reading prompt file '{path}': {e}")