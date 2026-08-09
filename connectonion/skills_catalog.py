"""The small, customer-facing skill set bundled into every ``co ai`` session.

The skill bodies stay in ``useful_skills`` so ``co copy`` and the default loader
read one canonical file. This allowlist is the product decision: adding a
library skill does not silently put it in every user's prompt.

This module intentionally has no package-level dependencies. Both skill readers
import it during startup, including when ``useful_plugins`` is only partially
initialized.
"""

from pathlib import Path
from typing import Iterator, Optional


DEFAULT_LIBRARY_SKILLS = (
    "install-connectonion",
    "co-browser",
    "co-mail-and-drive",
)


def builtin_skills_dir() -> Path:
    return Path(__file__).parent / "cli" / "co_ai" / "skills" / "builtin"


def useful_skills_dir() -> Path:
    return Path(__file__).parent / "useful_skills"


def default_skill_files() -> Iterator[Path]:
    """Yield native builtins, then allowlisted library skills."""
    native = builtin_skills_dir()
    if native.exists():
        for skill_dir in sorted(native.iterdir()):
            skill_file = skill_dir / "SKILL.md"
            if skill_file.is_file():
                yield skill_file

    library = useful_skills_dir()
    for name in DEFAULT_LIBRARY_SKILLS:
        skill_file = library / name / "SKILL.md"
        if skill_file.is_file():
            yield skill_file


def default_skill_path(name: str) -> Optional[Path]:
    """Return the canonical default skill body for ``name``."""
    native = builtin_skills_dir() / name / "SKILL.md"
    if native.is_file():
        return native
    if name in DEFAULT_LIBRARY_SKILLS:
        library = useful_skills_dir() / name / "SKILL.md"
        if library.is_file():
            return library
    return None
