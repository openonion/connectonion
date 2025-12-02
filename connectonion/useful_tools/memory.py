"""
Purpose: Persistent key-value memory storage for agents using markdown files with automatic scaling
LLM-Note:
  Dependencies: imports from [os, re] | imported by [useful_tools/__init__.py] | tested by [tests/test_memory.py]
  Data flow: Agent calls Memory methods → write_memory(key, content) stores in memory.md (or directory) → read_memory(key) retrieves by parsing markdown sections → list_memories() shows all keys → search_memory(pattern) uses regex across all content → auto-splits to directory when file exceeds split_threshold lines
  State/Effects: creates/modifies memory.md file or memory/ directory | single file uses ## headings as keys | auto-migrates to directory structure at threshold | does NOT delete old file on migration (removes it) | no network I/O
  Integration: exposes Memory class with write_memory(), read_memory(), list_memories(), search_memory() | used as agent tool by passing to Agent(tools=[memory]) | storage format: markdown with ## key headings | directory format: one .md file per key
  Performance: file I/O per operation (no caching) | parsing is O(n) file lines | search is O(n*m) files * lines | auto-scaling avoids single file bloat
  Errors: returns error string for missing keys | invalid key names sanitized (alphanumeric, hyphen, underscore only) | no exceptions raised (returns error messages)

**Simple by default**: Stores all memories in a single `memory.md` file.
**Scales automatically**: Splits into directory when file exceeds 3000 lines.

Usage:
    from connectonion import Agent, Memory

    memory = Memory()  # Creates memory.md
    agent = Agent("assistant", tools=[memory])

    # Agent can now use:
    # - write_memory(key, content)
    # - read_memory(key)
    # - list_memories()
    # - search_memory(pattern)  # Regex pattern

Example:
    from connectonion import Agent, Memory

    memory = Memory()
    agent = Agent(
        name="assistant",
        system_prompt="You are a helpful assistant with persistent memory.",
        tools=[memory]
    )

    agent.input("Remember that Alice prefers email over phone calls")
    agent.input("What do I know about Alice?")
"""

import os
import re


class Memory:
    """Simple memory system - single file by default, auto-scales to directory."""

    def __init__(self, memory_file: str = None, memory_dir: str = None, split_threshold: int = 3000):
        """Initialize memory system.

        Args:
            memory_file: Path to memory file (default: "memory.md")
            memory_dir: Directory for memories (backward compatibility, creates dir immediately)
            split_threshold: Line count that triggers directory split (default: 3000)
        """
        self.split_threshold = split_threshold
        self.using_directory = False

        # Handle backward compatibility with memory_dir parameter
        if memory_dir is not None:
            self.memory_dir = memory_dir
            self.memory_file = f"{memory_dir}.md"
            os.makedirs(memory_dir, exist_ok=True)
            self.using_directory = True
        elif memory_file is None:
            self.memory_file = "memory.md"
            # Check if already using directory structure
            dir_path = self.memory_file.replace('.md', '')
            if os.path.isdir(dir_path):
                self.using_directory = True
                self.memory_dir = dir_path
        else:
            self.memory_file = memory_file
            # Check if already using directory structure
            dir_path = memory_file.replace('.md', '')
            if os.path.isdir(dir_path):
                self.using_directory = True
                self.memory_dir = dir_path

    def write_memory(self, key: str, content: str) -> str:
        """Write content to memory.

        Args:
            key: Memory key/name
            content: Content to write (supports markdown)

        Returns:
            Confirmation message
        """
        safe_key = "".join(c for c in key if c.isalnum() or c in ('-', '_')).lower()
        if not safe_key:
            return "Invalid key name. Use alphanumeric characters, hyphens, or underscores."

        if self.using_directory:
            return self._write_directory(safe_key, content)

        return self._write_single_file(safe_key, content)

    def read_memory(self, key: str) -> str:
        """Read content from memory.

        Args:
            key: Memory key/name to read

        Returns:
            Memory content or error message
        """
        safe_key = "".join(c for c in key if c.isalnum() or c in ('-', '_')).lower()

        if self.using_directory:
            return self._read_directory(safe_key)

        return self._read_single_file(safe_key)

    def list_memories(self) -> str:
        """List all stored memories.

        Returns:
            Formatted list of available memory keys
        """
        if self.using_directory:
            return self._list_directory()

        return self._list_single_file()

    def search_memory(self, pattern: str) -> str:
        """Search across all memories using regex pattern.

        Use regex flags in pattern: (?i) for case-insensitive

        Args:
            pattern: Regex pattern to search for

        Returns:
            Formatted search results showing matching memories and lines
        """
        if self.using_directory:
            return self._search_directory(pattern)

        return self._search_single_file(pattern)


    # Single file implementation
    def _write_single_file(self, key: str, content: str) -> str:
        """Write to single memory file."""
        if not os.path.exists(self.memory_file):
            # Create new file
            with open(self.memory_file, 'w') as f:
                f.write(f"## {key}\n\n{content}\n\n")
            return f"Memory saved: {key}"

        # Read and parse existing file
        with open(self.memory_file, 'r') as f:
            file_content = f.read()

        sections = self._parse_sections(file_content)
        sections[key] = content

        # Write back
        new_content = self._serialize_sections(sections)
        with open(self.memory_file, 'w') as f:
            f.write(new_content)

        # Check if we need to split
        line_count = new_content.count('\n')
        if line_count > self.split_threshold:
            self._split_to_directory(sections)
            return f"Memory saved: {key} (migrated to directory)"

        return f"Memory saved: {key}"

    def _read_single_file(self, key: str) -> str:
        """Read from single memory file."""
        if not os.path.exists(self.memory_file):
            return f"Memory not found: {key}\nNo memories stored yet"

        with open(self.memory_file, 'r') as f:
            file_content = f.read()

        sections = self._parse_sections(file_content)

        if key not in sections:
            available = ", ".join(sorted(sections.keys())) if sections else "none"
            return f"Memory not found: {key}\nAvailable memories: {available}"

        return f"Memory: {key}\n\n{sections[key]}"

    def _list_single_file(self) -> str:
        """List memories from single file."""
        if not os.path.exists(self.memory_file):
            return "No memories stored yet"

        with open(self.memory_file, 'r') as f:
            file_content = f.read()

        sections = self._parse_sections(file_content)

        if not sections:
            return "No memories stored yet"

        output = [f"Stored Memories ({len(sections)}):"]
        for i, key in enumerate(sorted(sections.keys()), 1):
            size = len(sections[key])
            output.append(f"{i}. {key} ({size} bytes)")

        return "\n".join(output)

    def _search_single_file(self, pattern: str) -> str:
        """Search in single memory file."""
        if not os.path.exists(self.memory_file):
            return "No memories to search"

        with open(self.memory_file, 'r') as f:
            file_content = f.read()

        sections = self._parse_sections(file_content)

        if not sections:
            return "No memories to search"

        regex = re.compile(pattern)
        results = []
        total_matches = 0

        for key in sorted(sections.keys()):
            content = sections[key]
            lines = content.split('\n')

            matches = []
            for line_num, line in enumerate(lines, 1):
                if regex.search(line):
                    matches.append((line_num, line.strip()))

            if matches:
                total_matches += len(matches)
                results.append(f"\n{key}:")
                for line_num, line in matches:
                    results.append(f"  Line {line_num}: {line}")

        if not results:
            return f"No matches found for pattern: {pattern}"

        output = [f"Search Results ({total_matches} matches):"]
        output.extend(results)
        return "\n".join(output)


    def _parse_sections(self, content: str) -> dict:
        """Parse memory.md into sections."""
        sections = {}
        current_key = None
        current_content = []

        for line in content.split('\n'):
            if line.startswith('## '):
                # Save previous section
                if current_key:
                    sections[current_key] = '\n'.join(current_content).strip()
                # Start new section
                current_key = line[3:].strip()
                current_content = []
            elif current_key:
                current_content.append(line)

        # Save last section
        if current_key:
            sections[current_key] = '\n'.join(current_content).strip()

        return sections

    def _serialize_sections(self, sections: dict) -> str:
        """Serialize sections back to memory.md format."""
        output = []
        for key in sorted(sections.keys()):
            output.append(f"## {key}\n")
            output.append(f"{sections[key]}\n")
        return '\n'.join(output)

    def _split_to_directory(self, sections: dict):
        """Split single file into directory structure."""
        self.memory_dir = self.memory_file.replace('.md', '')
        os.makedirs(self.memory_dir, exist_ok=True)

        # Write each section to its own file
        for key, content in sections.items():
            filepath = os.path.join(self.memory_dir, f"{key}.md")
            with open(filepath, 'w') as f:
                f.write(content)

        # Remove single file
        if os.path.exists(self.memory_file):
            os.remove(self.memory_file)

        self.using_directory = True

    # Directory implementation
    def _write_directory(self, key: str, content: str) -> str:
        """Write to directory structure."""
        os.makedirs(self.memory_dir, exist_ok=True)
        filepath = os.path.join(self.memory_dir, f"{key}.md")
        with open(filepath, 'w') as f:
            f.write(content)
        return f"Memory saved: {key}"

    def _read_directory(self, key: str) -> str:
        """Read from directory structure."""
        if not os.path.exists(self.memory_dir):
            return f"Memory not found: {key}\nNo memories stored yet"

        filepath = os.path.join(self.memory_dir, f"{key}.md")

        if not os.path.exists(filepath):
            files = [f.replace('.md', '') for f in os.listdir(self.memory_dir) if f.endswith('.md')]
            available = ", ".join(sorted(files)) if files else "none"
            return f"Memory not found: {key}\nAvailable memories: {available}"

        with open(filepath, 'r') as f:
            content = f.read()

        return f"Memory: {key}\n\n{content}"

    def _list_directory(self) -> str:
        """List memories from directory."""
        if not os.path.exists(self.memory_dir):
            return "No memories stored yet"

        files = [f for f in os.listdir(self.memory_dir) if f.endswith('.md')]

        if not files:
            return "No memories stored yet"

        keys = [f.replace('.md', '') for f in files]
        output = [f"Stored Memories ({len(keys)}):"]

        for i, key in enumerate(sorted(keys), 1):
            filepath = os.path.join(self.memory_dir, f"{key}.md")
            size = os.path.getsize(filepath)
            output.append(f"{i}. {key} ({size} bytes)")

        return "\n".join(output)

    def _search_directory(self, pattern: str) -> str:
        """Search in directory structure."""
        if not os.path.exists(self.memory_dir):
            return "No memories to search"

        files = [f for f in os.listdir(self.memory_dir) if f.endswith('.md')]

        if not files:
            return "No memories to search"

        regex = re.compile(pattern)
        results = []
        total_matches = 0

        for filename in sorted(files):
            key = filename.replace('.md', '')
            filepath = os.path.join(self.memory_dir, filename)

            with open(filepath, 'r') as f:
                content = f.read()
                lines = content.split('\n')

            matches = []
            for line_num, line in enumerate(lines, 1):
                if regex.search(line):
                    matches.append((line_num, line.strip()))

            if matches:
                total_matches += len(matches)
                results.append(f"\n{key}:")
                for line_num, line in matches:
                    results.append(f"  Line {line_num}: {line}")

        if not results:
            return f"No matches found for pattern: {pattern}"

        output = [f"Search Results ({total_matches} matches):"]
        output.extend(results)
        return "\n".join(output)

