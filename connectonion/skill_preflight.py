"""Purely local preflight checks for versioned skill requirements."""

import importlib.metadata
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Optional

from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

from .skill_requirements import SkillRequirement, SkillRequirements


@dataclass(frozen=True)
class RequirementCheck:
    skill_name: str
    required: bool
    requirement: SkillRequirement
    available: bool
    detail: str


@dataclass(frozen=True)
class SkillPreflightReport:
    checks: tuple[RequirementCheck, ...] = ()

    @property
    def missing_required(self) -> tuple[RequirementCheck, ...]:
        return tuple(check for check in self.checks if check.required and not check.available)

    @property
    def missing_optional(self) -> tuple[RequirementCheck, ...]:
        return tuple(check for check in self.checks if not check.required and not check.available)

    @property
    def ready(self) -> bool:
        return not self.missing_required


def preflight_skills(
    skills: Iterable[tuple[str, Optional[SkillRequirements]]],
    *,
    environ: Optional[Mapping[str, str]] = None,
    which: Callable[[str], Optional[str]] = shutil.which,
    package_version: Callable[[str], str] = importlib.metadata.version,
    executable_version: Optional[Callable[[str], Optional[str]]] = None,
) -> SkillPreflightReport:
    """Resolve manifests against this machine without making network calls."""
    env = os.environ if environ is None else environ
    executable_version = executable_version or _executable_version
    checks = []
    for skill_name, manifest in skills:
        if manifest is None:
            continue
        for required, requirements in ((True, manifest.required), (False, manifest.optional)):
            for requirement in requirements:
                available, detail = _check_requirement(
                    requirement, env, which, package_version, executable_version
                )
                checks.append(RequirementCheck(
                    skill_name, required, requirement, available, detail
                ))
    return SkillPreflightReport(tuple(checks))


def format_preflight_report(report: SkillPreflightReport) -> str:
    """One actionable report containing required and optional findings."""
    findings = report.missing_required + report.missing_optional
    if not findings:
        return ""
    lines = ["Skill runtime preflight:"]
    for check in findings:
        level = "required" if check.required else "optional"
        req = check.requirement
        constraint = f" {req.version}" if req.version else ""
        lines.append(
            f"- {check.skill_name} [{level}/{req.category}] "
            f"{req.name}{constraint}: {check.detail}"
        )
        if req.setup:
            lines.append(f"  Setup: {req.setup}")
    return "\n".join(lines)


def _check_requirement(requirement, env, which, package_version, executable_version):
    category = requirement.category
    if category == "python":
        try:
            installed = package_version(requirement.name)
        except importlib.metadata.PackageNotFoundError:
            return False, "package is not installed"
        return _version_result(installed, requirement.version)

    if category == "executables":
        path = which(requirement.name)
        if not path:
            return False, "executable is not on PATH"
        if not requirement.version:
            return True, f"found at {path}"
        installed = executable_version(path)
        if not installed:
            return False, "found, but its version could not be determined"
        return _version_result(installed, requirement.version)

    if category == "environment":
        return ((True, "set") if env.get(requirement.name)
                else (False, "environment variable is not set"))

    if category == "oauth":
        prefix = re.sub(r"[^A-Za-z0-9]", "_", requirement.name).upper()
        connected = bool(env.get(f"{prefix}_ACCESS_TOKEN") or env.get(f"{prefix}_REFRESH_TOKEN"))
        if not connected:
            return False, f"{requirement.name} OAuth is not connected"
        available_scopes = set(filter(None, re.split(r"[\s,]+", env.get(f"{prefix}_SCOPES", ""))))
        missing = sorted(scope for scope in requirement.scopes
                         if not _has_scope(scope, available_scopes))
        if missing:
            return False, "missing OAuth scopes: " + ", ".join(missing)
        return True, "connected"

    if category == "capabilities":
        available = set(filter(None, re.split(
            r"[\s,]+", env.get("CONNECTONION_CAPABILITIES", "")
        )))
        if requirement.name not in available:
            return False, "platform capability is not available"
        versions = _capability_versions(env.get("CONNECTONION_CAPABILITY_VERSIONS", ""))
        if not requirement.version:
            return True, "available"
        installed = versions.get(requirement.name)
        if not installed:
            return False, "available, but its version is not declared"
        return _version_result(installed, requirement.version)

    return False, "unsupported requirement category"


def _version_result(installed: str, constraint: Optional[str]) -> tuple[bool, str]:
    if not constraint:
        return True, f"installed {installed}"
    try:
        matches = Version(installed) in SpecifierSet(constraint)
    except InvalidVersion:
        return False, f"installed version {installed!r} is not PEP 440 compatible"
    if matches:
        return True, f"installed {installed}"
    return False, f"installed {installed} does not satisfy {constraint}"


def _executable_version(path: str) -> Optional[str]:
    try:
        result = subprocess.run(
            [path, "--version"], capture_output=True, text=True, timeout=2, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(r"(?<!\w)(\d+(?:\.\d+)+(?:[-+._][A-Za-z0-9.]+)?)", result.stdout + result.stderr)
    return match.group(1) if match else None


def _capability_versions(value: str) -> dict[str, str]:
    versions = {}
    for item in filter(None, re.split(r"[\s,]+", value)):
        if "=" in item:
            name, version = item.split("=", 1)
            if name and version:
                versions[name] = version
    return versions


def _has_scope(required: str, available: set[str]) -> bool:
    return required in available or any(
        scope.endswith("/" + required) for scope in available
    )


__all__ = [
    "RequirementCheck",
    "SkillPreflightReport",
    "format_preflight_report",
    "preflight_skills",
]
