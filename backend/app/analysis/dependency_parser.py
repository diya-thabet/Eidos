"""
Dependency file parsers.

Parses package manifest files (requirements.txt, package.json, pom.xml, etc.)
and extracts declared dependencies. Uses ONLY Python stdlib: json, tomllib,
xml.etree, configparser, re.

Each parser returns a list of DependencyInfo dataclasses.
"""

from __future__ import annotations

import configparser
import json
import logging
import re
import tomllib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class DependencyInfo:
    """A single declared dependency from a manifest file."""

    name: str
    version: str  # raw version string (">=2.0", "^4.17", "1.0.0")
    ecosystem: str  # pypi, npm, maven, crates, go, nuget, cmake
    file_path: str  # relative path to the manifest
    is_dev: bool = False
    is_pinned: bool = False  # exact version (no range)


# -----------------------------------------------------------------------
# Version pinning detection
# -----------------------------------------------------------------------

_RANGE_CHARS = re.compile(r"[><=^~*|]")


def _is_pinned(version: str) -> bool:
    """True if version is an exact pin (no range operators)."""
    v = version.strip()
    if not v or v == "*" or v == "latest":
        return False
    return not _RANGE_CHARS.search(v)


# -----------------------------------------------------------------------
# Python: requirements.txt
# -----------------------------------------------------------------------

_REQ_LINE = re.compile(
    r"^([A-Za-z0-9_][A-Za-z0-9._-]*)\s*(?:\[.*?\])?\s*(.*?)$"
)


def parse_requirements_txt(content: str, file_path: str) -> list[DependencyInfo]:
    """Parse requirements.txt or constraints.txt."""
    deps: list[DependencyInfo] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        m = _REQ_LINE.match(line)
        if m:
            name = m.group(1)
            raw_ver = m.group(2).strip()
            version = raw_ver.lstrip("=!<>~") or "*"
            # Pinned = exactly "==X.Y.Z" (no range)
            pinned = raw_ver.startswith("==") and "," not in raw_ver
            deps.append(DependencyInfo(
                name=name,
                version=version,
                ecosystem="pypi",
                file_path=file_path,
                is_pinned=pinned,
            ))
    return deps


# -----------------------------------------------------------------------
# Python: pyproject.toml
# -----------------------------------------------------------------------

_PEP508 = re.compile(
    r"^([A-Za-z0-9_][A-Za-z0-9._-]*)\s*(?:\[.*?\])?\s*(.*?)$"
)


def parse_pyproject_toml(content: str, file_path: str) -> list[DependencyInfo]:
    """Parse pyproject.toml [project.dependencies] and [project.optional-dependencies]."""
    deps: list[DependencyInfo] = []
    try:
        data = tomllib.loads(content)
    except Exception:
        logger.warning("Failed to parse %s", file_path)
        return deps

    # [project.dependencies]
    for spec in data.get("project", {}).get("dependencies", []):
        d = _parse_pep508(spec, file_path, is_dev=False)
        if d:
            deps.append(d)

    # [project.optional-dependencies]
    for group, specs in data.get("project", {}).get(
        "optional-dependencies", {}
    ).items():
        for spec in specs:
            d = _parse_pep508(spec, file_path, is_dev=True)
            if d:
                deps.append(d)

    return deps


def _parse_pep508(
    spec: str, file_path: str, is_dev: bool
) -> DependencyInfo | None:
    m = _PEP508.match(spec.strip())
    if not m:
        return None
    name = m.group(1)
    version_part = m.group(2).strip().rstrip(";").strip()
    return DependencyInfo(
        name=name,
        version=version_part or "*",
        ecosystem="pypi",
        file_path=file_path,
        is_dev=is_dev,
        is_pinned=_is_pinned(version_part),
    )


# -----------------------------------------------------------------------
# Python: setup.cfg
# -----------------------------------------------------------------------


def parse_setup_cfg(content: str, file_path: str) -> list[DependencyInfo]:
    """Parse setup.cfg [options] install_requires."""
    deps: list[DependencyInfo] = []
    cfg = configparser.ConfigParser()
    try:
        cfg.read_string(content)
    except Exception:
        return deps

    raw = cfg.get("options", "install_requires", fallback="")
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        d = _parse_pep508(line, file_path, is_dev=False)
        if d:
            deps.append(d)
    return deps


# -----------------------------------------------------------------------
# JavaScript / TypeScript: package.json
# -----------------------------------------------------------------------


def parse_package_json(content: str, file_path: str) -> list[DependencyInfo]:
    """Parse package.json dependencies and devDependencies."""
    deps: list[DependencyInfo] = []
    try:
        data = json.loads(content)
    except Exception:
        return deps

    for name, version in data.get("dependencies", {}).items():
        deps.append(DependencyInfo(
            name=name,
            version=version,
            ecosystem="npm",
            file_path=file_path,
            is_pinned=_is_pinned(version),
        ))
    for name, version in data.get("devDependencies", {}).items():
        deps.append(DependencyInfo(
            name=name,
            version=version,
            ecosystem="npm",
            file_path=file_path,
            is_dev=True,
            is_pinned=_is_pinned(version),
        ))
    return deps


# -----------------------------------------------------------------------
# Java: pom.xml
# -----------------------------------------------------------------------

_MVN_NS = "{http://maven.apache.org/POM/4.0.0}"


def parse_pom_xml(content: str, file_path: str) -> list[DependencyInfo]:
    """Parse Maven pom.xml <dependency> elements."""
    deps: list[DependencyInfo] = []
    try:
        root = ET.fromstring(content)  # noqa: S314
    except Exception:
        return deps

    for dep in root.iter(f"{_MVN_NS}dependency"):
        gid = dep.findtext(f"{_MVN_NS}groupId", "")
        aid = dep.findtext(f"{_MVN_NS}artifactId", "")
        ver = dep.findtext(f"{_MVN_NS}version", "*")
        scope = dep.findtext(f"{_MVN_NS}scope", "compile")
        if not aid:
            continue
        name = f"{gid}:{aid}" if gid else aid
        deps.append(DependencyInfo(
            name=name,
            version=ver or "*",
            ecosystem="maven",
            file_path=file_path,
            is_dev=scope in ("test", "provided"),
            is_pinned=_is_pinned(ver or ""),
        ))

    # Fallback: try without namespace
    if not deps:
        for dep in root.iter("dependency"):
            gid = dep.findtext("groupId", "")
            aid = dep.findtext("artifactId", "")
            ver = dep.findtext("version", "*")
            scope = dep.findtext("scope", "compile")
            if not aid:
                continue
            name = f"{gid}:{aid}" if gid else aid
            deps.append(DependencyInfo(
                name=name,
                version=ver or "*",
                ecosystem="maven",
                file_path=file_path,
                is_dev=scope in ("test", "provided"),
                is_pinned=_is_pinned(ver or ""),
            ))
    return deps


# -----------------------------------------------------------------------
# Java: build.gradle (regex-based, best-effort)
# -----------------------------------------------------------------------

_GRADLE_DEP = re.compile(
    r"""(?:implementation|api|compile|testImplementation|testCompile"""
    r"""|runtimeOnly|compileOnly)\s*[\('"]\s*"""
    r"""([^:'"]+):([^:'"]+):([^'")\s]*)""",
)

_GRADLE_TEST = re.compile(r"test(?:Implementation|Compile)")


def parse_build_gradle(content: str, file_path: str) -> list[DependencyInfo]:
    """Parse build.gradle dependency declarations (best-effort regex)."""
    deps: list[DependencyInfo] = []
    for m in _GRADLE_DEP.finditer(content):
        group, artifact, version = m.group(1), m.group(2), m.group(3)
        name = f"{group}:{artifact}"
        ver: str = version or "*"
        # Check if the original line was a test dependency
        line_start = content.rfind("\n", 0, m.start()) + 1
        line = content[line_start : m.end()]
        is_dev = bool(_GRADLE_TEST.search(line))
        deps.append(DependencyInfo(
            name=name,
            version=ver,
            ecosystem="maven",
            file_path=file_path,
            is_dev=is_dev,
            is_pinned=_is_pinned(ver),
        ))
    return deps


# -----------------------------------------------------------------------
# Go: go.mod
# -----------------------------------------------------------------------

_GO_REQUIRE = re.compile(r"^\s*(\S+)\s+(v[\d.]+\S*)", re.MULTILINE)


def parse_go_mod(content: str, file_path: str) -> list[DependencyInfo]:
    """Parse go.mod require directives."""
    deps: list[DependencyInfo] = []
    for m in _GO_REQUIRE.finditer(content):
        name, version = m.group(1), m.group(2)
        # Skip indirect marker
        if name in ("require", "go", "module", "toolchain"):
            continue
        deps.append(DependencyInfo(
            name=name,
            version=version,
            ecosystem="go",
            file_path=file_path,
            is_pinned=True,  # Go modules are always pinned
        ))
    return deps


# -----------------------------------------------------------------------
# Rust: Cargo.toml
# -----------------------------------------------------------------------


def parse_cargo_toml(content: str, file_path: str) -> list[DependencyInfo]:
    """Parse Cargo.toml [dependencies] and [dev-dependencies]."""
    deps: list[DependencyInfo] = []
    try:
        data = tomllib.loads(content)
    except Exception:
        return deps

    for section, is_dev in [
        ("dependencies", False),
        ("dev-dependencies", True),
        ("build-dependencies", True),
    ]:
        for name, val in data.get(section, {}).items():
            if isinstance(val, str):
                version = val
            elif isinstance(val, dict):
                version = val.get("version", "*")
            else:
                version = "*"
            deps.append(DependencyInfo(
                name=name,
                version=str(version),
                ecosystem="crates",
                file_path=file_path,
                is_dev=is_dev,
                is_pinned=_is_pinned(str(version)),
            ))
    return deps


# -----------------------------------------------------------------------
# C#: .csproj
# -----------------------------------------------------------------------


def parse_csproj(content: str, file_path: str) -> list[DependencyInfo]:
    """Parse .csproj <PackageReference> elements."""
    deps: list[DependencyInfo] = []
    try:
        root = ET.fromstring(content)  # noqa: S314
    except Exception:
        return deps

    for ref in root.iter("PackageReference"):
        name = ref.get("Include", "") or ref.get("include", "")
        version = (
            ref.get("Version", "")
            or ref.get("version", "")
            or ref.findtext("Version", "*")
        )
        if not name:
            continue
        deps.append(DependencyInfo(
            name=name,
            version=version or "*",
            ecosystem="nuget",
            file_path=file_path,
            is_pinned=_is_pinned(version or ""),
        ))
    return deps


# -----------------------------------------------------------------------
# C/C++: vcpkg.json
# -----------------------------------------------------------------------


def parse_vcpkg_json(content: str, file_path: str) -> list[DependencyInfo]:
    """Parse vcpkg.json dependencies array."""
    deps: list[DependencyInfo] = []
    try:
        data = json.loads(content)
    except Exception:
        return deps

    for item in data.get("dependencies", []):
        if isinstance(item, str):
            name = item
            version = "*"
        elif isinstance(item, dict):
            name = item.get("name", "")
            version = str(item.get("version>=", item.get("version", "*")))
        else:
            continue
        if name:
            deps.append(DependencyInfo(
                name=name,
                version=str(version),
                ecosystem="vcpkg",
                file_path=file_path,
                is_pinned=_is_pinned(str(version)),
            ))
    return deps


# -----------------------------------------------------------------------
# C/C++: CMakeLists.txt (best-effort regex)
# -----------------------------------------------------------------------

_CMAKE_PKG = re.compile(
    r"find_package\s*\(\s*(\w+)(?:\s+([\d.]+))?\s*", re.IGNORECASE
)


def parse_cmakelists(content: str, file_path: str) -> list[DependencyInfo]:
    """Parse CMakeLists.txt find_package() calls."""
    deps: list[DependencyInfo] = []
    for m in _CMAKE_PKG.finditer(content):
        name = m.group(1)
        version = m.group(2) or "*"
        deps.append(DependencyInfo(
            name=name,
            version=version,
            ecosystem="cmake",
            file_path=file_path,
            is_pinned=_is_pinned(version),
        ))
    return deps


# -----------------------------------------------------------------------
# Master dispatcher
# -----------------------------------------------------------------------

# Map filename (or pattern) to parser
_PARSERS: dict[str, object] = {
    "requirements.txt": parse_requirements_txt,
    "requirements-dev.txt": parse_requirements_txt,
    "requirements_dev.txt": parse_requirements_txt,
    "constraints.txt": parse_requirements_txt,
    "pyproject.toml": parse_pyproject_toml,
    "setup.cfg": parse_setup_cfg,
    "package.json": parse_package_json,
    "pom.xml": parse_pom_xml,
    "build.gradle": parse_build_gradle,
    "go.mod": parse_go_mod,
    "Cargo.toml": parse_cargo_toml,
    "vcpkg.json": parse_vcpkg_json,
    "CMakeLists.txt": parse_cmakelists,
}


def is_manifest_file(filename: str) -> bool:
    """Check if a filename is a recognized dependency manifest."""
    base = Path(filename).name
    if base in _PARSERS:
        return True
    if base.endswith(".csproj"):
        return True
    if base.startswith("requirements") and base.endswith(".txt"):
        return True
    return False


def parse_manifest(
    content: str, file_path: str
) -> list[DependencyInfo]:
    """Parse a manifest file and return its dependencies."""
    base = Path(file_path).name

    # .csproj files
    if base.endswith(".csproj"):
        return parse_csproj(content, file_path)

    # requirements*.txt variants
    if base.startswith("requirements") and base.endswith(".txt"):
        return parse_requirements_txt(content, file_path)

    parser_func = _PARSERS.get(base)
    if parser_func is None:
        return []
    return parser_func(content, file_path)  # type: ignore[no-any-return, operator]


def scan_dependencies(repo_dir: Path) -> list[DependencyInfo]:
    """Scan a repo directory for all manifest files and parse them."""
    all_deps: list[DependencyInfo] = []
    skip_dirs = {
        ".git", "node_modules", "__pycache__", ".venv", "venv",
        "vendor", "target", "bin", "obj", "dist", "build",
    }

    for path in repo_dir.rglob("*"):
        if path.is_dir():
            continue
        # Skip ignored directories
        parts = path.relative_to(repo_dir).parts
        if any(p in skip_dirs for p in parts):
            continue
        if is_manifest_file(path.name):
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                rel = str(path.relative_to(repo_dir)).replace("\\", "/")
                deps = parse_manifest(content, rel)
                all_deps.extend(deps)
            except Exception:
                logger.warning("Failed to parse manifest: %s", path)
    return all_deps
