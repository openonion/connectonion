"""
Purpose: File tools module - Claude Code-style file operations with state tracking
LLM-Note:
  Dependencies: exports FileTools class and individual tool functions
  Integration: imported by useful_tools/__init__.py

Exports:
  - FileTools: Class with read-before-edit tracking and permission control
  - Individual functions: read_file, edit, multi_edit, write, glob, grep (standalone)
"""

from .edit import edit
from .file_tools import FileTools
from .glob import glob
from .grep import grep
from .multi_edit import EditOperation, multi_edit
from .read import read_file
from .write import write

__all__ = [
    # Main class (recommended)
    "FileTools",
    # Individual functions (for backward compatibility or custom usage)
    "read_file",
    "edit",
    "multi_edit",
    "write",
    "glob",
    "grep",
    # Types
    "EditOperation",
]
