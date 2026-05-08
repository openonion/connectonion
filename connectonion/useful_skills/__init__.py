"""
Purpose: Marker package whose only role is to ship a directory of copyable skill bundles (.md / .sh files) that `co copy <skill-name>` drops into a user's .co/skills/.
LLM-Note:
  Dependencies: none (no Python imports — skills are static assets, not Python modules) | imported by [cli/commands/copy_commands.py uses pkg_resources / importlib.resources to enumerate this package's data files] | not unit-tested directly; covered by tests/cli/test_copy.py
  Data flow: copy_commands resolves the path to this package via importlib.resources → walks the directory for skill bundles → copies selected bundle into the user project's .co/skills/<name>/
  State/Effects: none at import time — this file exists purely so Python treats useful_skills/ as an importable package and so MANIFEST.in/setup.py package_data can ship its sibling files
  Integration: no public API; the surface lives in cli/commands/copy_commands.py
"""

# Copyable skills — use `co copy <skill-name>` to add to your project's .co/skills/
