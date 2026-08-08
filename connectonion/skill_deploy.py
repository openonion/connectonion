"""Collect the skill dependency state that must travel with a deployment."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .skill_requirements import parse_skill_requirements
from .useful_plugins.skills import _parse_skill_content


@dataclass(frozen=True)
class DeploySkillRequirements:
    python: tuple[str, ...] = ()
    unsupported: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()

    @property
    def requested_state(self) -> dict:
        return {
            "schema": 1,
            "skills": list(self.skills),
            "python": list(self.python),
            "unsupported": list(self.unsupported),
        }

    @property
    def digest(self) -> str:
        encoded = json.dumps(
            self.requested_state, sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(encoded).hexdigest()


def collect_deploy_skill_requirements(
    project_dir: Path, extra_skill_paths: Iterable[Path] = ()
) -> DeploySkillRequirements:
    """Collect required runtime dependencies from skills that will deploy."""
    files = []
    for root in (project_dir / ".co" / "skills", project_dir / ".claude" / "skills"):
        if root.is_dir():
            files.extend(root.glob("*/SKILL.md"))
    for path in extra_skill_paths:
        if (path / "SKILL.md").is_file():
            files.append(path / "SKILL.md")
        elif path.is_dir():
            files.extend(path.glob("*/SKILL.md"))

    python = set()
    unsupported = set()
    skills = set()
    for skill_file in sorted(set(path.resolve() for path in files)):
        frontmatter, _ = _parse_skill_content(skill_file.read_text(encoding="utf-8"))
        name = str(frontmatter.get("name") or skill_file.parent.name)
        manifest = parse_skill_requirements(frontmatter, name)
        if manifest is None:
            continue
        skills.add(name)
        for requirement in manifest.required:
            if requirement.category == "python":
                python.add(requirement.name + (requirement.version or ""))
            elif requirement.category in {"executables", "capabilities"}:
                constraint = f" {requirement.version}" if requirement.version else ""
                hint = f" — {requirement.setup}" if requirement.setup else ""
                unsupported.add(
                    f"{name}: {requirement.category}/{requirement.name}{constraint}{hint}"
                )

    return DeploySkillRequirements(
        python=tuple(sorted(python)),
        unsupported=tuple(sorted(unsupported)),
        skills=tuple(sorted(skills)),
    )


__all__ = ["DeploySkillRequirements", "collect_deploy_skill_requirements"]
