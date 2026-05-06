"""
SBOM (Software Bill of Materials) generation.

Supports:
- CycloneDX 1.5 (JSON)
- SPDX 2.3 (JSON)

Pure formatting � no external API calls.
"""

from __future__ import annotationsimport uuidfrom datetime import UTC, datetimefrom typing import Any# Ecosystem -> PURL scheme mapping
_PURL_MAP: dict[str, str] = {
    "pypi": "pkg:pypi/{name}@{version}",
    "npm": "pkg:npm/{name}@{version}",
    "maven": "pkg:maven/{group}/{name}@{version}",
    "crates": "pkg:cargo/{name}@{version}",
    "nuget": "pkg:nuget/{name}@{version}",
    "go": "pkg:golang/{name}@{version}",
    "gem": "pkg:gem/{name}@{version}",
    "composer": "pkg:composer/{name}@{version}",
}


def _to_purl(name: str, version: str, ecosystem: str) -> str:
    """Convert a dependency to Package URL (purl) format."""
    template = _PURL_MAP.get(ecosystem, "pkg:{ecosystem}/{name}@{version}")
    # Handle Maven group/artifact
    if ecosystem == "maven" and ":" in name:
        parts = name.split(":", 1)
        return template.format(group=parts[0], name=parts[1], version=version)
    return template.format(
        name=name, version=version, ecosystem=ecosystem,
    )


def generate_cyclonedx(
    repo_name: str,
    snapshot_id: str,
    dependencies: list[dict[str, Any]],
) -> dict[str, Any]:
    """Generate a CycloneDX 1.5 SBOM.

    Args:
        repo_name: The repository name.
        snapshot_id: The snapshot ID (used as version).
        dependencies: List of dicts with keys: name, version, ecosystem, is_dev, file_path.

    Returns:
        CycloneDX 1.5 JSON dict.
    """
    components: list[dict[str, Any]] = []
    for dep in dependencies:
        name = dep.get("name", "")
        version = dep.get("version", "*")
        ecosystem = dep.get("ecosystem", "unknown")
        is_dev = dep.get("is_dev", False)

        component: dict[str, Any] = {
            "type": "library",
            "name": name,
            "version": version,
            "purl": _to_purl(name, version, ecosystem),
            "scope": "optional" if is_dev else "required",
        }

        # Add properties for ecosystem
        component["properties"] = [
            {"name": "ecosystem", "value": ecosystem},
        ]
        if dep.get("file_path"):
            component["properties"].append(
                {"name": "manifest", "value": dep["file_path"]},
            )

        components.append(component)

    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(UTC).isoformat(),
            "tools": {
                "components": [
                    {"type": "application", "name": "Eidos", "version": "1.0.0"},
                ],
            },
            "component": {
                "type": "application",
                "name": repo_name,
                "version": snapshot_id[:8],
            },
        },
        "components": components,
    }


def generate_spdx(
    repo_name: str,
    snapshot_id: str,
    dependencies: list[dict[str, Any]],
) -> dict[str, Any]:
    """Generate an SPDX 2.3 SBOM.

    Args:
        repo_name: The repository name.
        snapshot_id: The snapshot ID.
        dependencies: List of dicts with keys: name, version, ecosystem, is_dev.

    Returns:
        SPDX 2.3 JSON dict.
    """
    doc_id = f"SPDXRef-DOCUMENT-{uuid.uuid4().hex[:12]}"
    packages: list[dict[str, Any]] = []

    for i, dep in enumerate(dependencies):
        name = dep.get("name", "")
        version = dep.get("version", "*")
        ecosystem = dep.get("ecosystem", "unknown")

        pkg: dict[str, Any] = {
            "SPDXID": f"SPDXRef-Package-{i + 1}",
            "name": name,
            "versionInfo": version,
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": False,
            "supplier": "NOASSERTION",
            "externalRefs": [
                {
                    "referenceCategory": "PACKAGE-MANAGER",
                    "referenceType": "purl",
                    "referenceLocator": _to_purl(name, version, ecosystem),
                },
            ],
        }
        packages.append(pkg)

    relationships: list[dict[str, str]] = [
        {
            "spdxElementId": doc_id,
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": f"SPDXRef-Package-{i + 1}",
        }
        for i in range(len(packages))
    ]

    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": doc_id,
        "name": f"{repo_name}-{snapshot_id[:8]}",
        "documentNamespace": f"https://eidos.dev/spdx/{repo_name}/{snapshot_id}",
        "creationInfo": {
            "created": datetime.now(UTC).isoformat(),
            "creators": ["Tool: Eidos-1.0.0"],
            "licenseListVersion": "3.22",
        },
        "packages": packages,
        "relationships": relationships,
    }
