"""Versioned runtime requirement manifests for SKILL.md files.

This module only parses the declaration.  Checking the current machine and
installing supported dependencies are deliberately separate concerns.
"""

import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from packaging.specifiers import InvalidSpecifier, SpecifierSet

SCHEMA_VERSION = 1
_SECTIONS = ("required", "optional")
_CATEGORIES = ("python", "executables", "environment", "oauth", "capabilities")
_IDENTIFIERS = {
    "python": re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$"),
    "executables": re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$"),
    "environment": re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$"),
    "oauth": re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$"),
    "capabilities": re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$"),
}


class SkillManifestError(ValueError):
    """A requirement manifest is invalid and identifies its exact location."""

    def __init__(self, skill_name: str, field: str, problem: str):
        self.skill_name = skill_name
        self.field = field
        self.problem = problem
        super().__init__(f"Skill {skill_name!r}: {field}: {problem}")


@dataclass(frozen=True)
class SkillRequirement:
    """One normalized runtime requirement."""

    category: str
    name: str
    version: Optional[str] = None
    setup: Optional[str] = None
    scopes: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillRequirements:
    """A validated version of a skill's runtime requirement manifest."""

    version: int
    required: tuple[SkillRequirement, ...] = ()
    optional: tuple[SkillRequirement, ...] = ()


def parse_skill_requirements(
    frontmatter: Mapping[str, Any], skill_name: str
) -> Optional[SkillRequirements]:
    """Validate and normalize ``frontmatter.requirements``.

    Skills which do not declare requirements remain fully compatible and
    return ``None``. Invalid declarations raise :class:`SkillManifestError`.
    """
    if "requirements" not in frontmatter:
        return None

    root = frontmatter["requirements"]
    _mapping(root, skill_name, "requirements")
    _known_fields(root, {"version", *_SECTIONS}, skill_name, "requirements")

    if "version" not in root:
        _fail(skill_name, "requirements.version", "is required")
    version = root["version"]
    if isinstance(version, bool) or not isinstance(version, int):
        _fail(skill_name, "requirements.version", "must be the integer 1")
    if version != SCHEMA_VERSION:
        _fail(
            skill_name,
            "requirements.version",
            f"unsupported schema version {version}; supported version is {SCHEMA_VERSION}",
        )

    parsed = {
        section: _parse_section(root.get(section, {}), skill_name, section)
        for section in _SECTIONS
    }
    return SkillRequirements(version=version, **parsed)


def _parse_section(value: Any, skill_name: str, section: str) -> tuple[SkillRequirement, ...]:
    path = f"requirements.{section}"
    _mapping(value, skill_name, path)
    _known_fields(value, set(_CATEGORIES), skill_name, path)

    requirements = []
    for category in _CATEGORIES:
        entries = value.get(category, [])
        category_path = f"{path}.{category}"
        if not isinstance(entries, list):
            _fail(skill_name, category_path, "must be a list")
        for index, entry in enumerate(entries):
            requirements.append(
                _parse_entry(entry, skill_name, category, f"{category_path}[{index}]")
            )
    return tuple(requirements)


def _parse_entry(value: Any, skill_name: str, category: str, path: str) -> SkillRequirement:
    _mapping(value, skill_name, path)
    name_field = "provider" if category == "oauth" else "name"
    allowed = {name_field, "setup"}
    if category in {"python", "executables", "capabilities"}:
        allowed.add("version")
    if category == "oauth":
        allowed.add("scopes")
    _known_fields(value, allowed, skill_name, path)

    if name_field not in value:
        _fail(skill_name, f"{path}.{name_field}", "is required")
    name = _nonempty_string(value[name_field], skill_name, f"{path}.{name_field}")
    if not _IDENTIFIERS[category].fullmatch(name):
        _fail(skill_name, f"{path}.{name_field}", f"is not a valid {category} identifier")

    version = None
    if "version" in value:
        version = _nonempty_string(value["version"], skill_name, f"{path}.version")
        try:
            SpecifierSet(version)
        except InvalidSpecifier:
            _fail(skill_name, f"{path}.version", "must be a valid PEP 440 constraint")

    setup = None
    if "setup" in value:
        setup = _nonempty_string(value["setup"], skill_name, f"{path}.setup")

    scopes: tuple[str, ...] = ()
    if "scopes" in value:
        raw_scopes = value["scopes"]
        if not isinstance(raw_scopes, list):
            _fail(skill_name, f"{path}.scopes", "must be a list")
        parsed_scopes = []
        for index, scope in enumerate(raw_scopes):
            parsed_scopes.append(
                _nonempty_string(scope, skill_name, f"{path}.scopes[{index}]")
            )
        scopes = tuple(parsed_scopes)

    return SkillRequirement(
        category=category, name=name, version=version, setup=setup, scopes=scopes
    )


def _mapping(value: Any, skill_name: str, path: str) -> None:
    if not isinstance(value, Mapping):
        _fail(skill_name, path, "must be a mapping")


def _known_fields(value: Mapping[str, Any], allowed: set[str], skill_name: str, path: str) -> None:
    for field in value:
        if not isinstance(field, str) or field not in allowed:
            _fail(skill_name, f"{path}.{field}", "is not a supported field")


def _nonempty_string(value: Any, skill_name: str, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(skill_name, path, "must be a non-empty string")
    return value.strip()


def _fail(skill_name: str, field: str, problem: str) -> None:
    raise SkillManifestError(skill_name, field, problem)


__all__ = [
    "SCHEMA_VERSION",
    "SkillManifestError",
    "SkillRequirement",
    "SkillRequirements",
    "parse_skill_requirements",
]
