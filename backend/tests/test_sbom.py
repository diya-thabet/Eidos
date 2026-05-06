"""
Tests for Phase 9 (Phase 10.9): SBOM Generation (CycloneDX & SPDX).

Tests the SBOM generators and 1 API endpoint with format param.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.exports.sbom import _to_purl, generate_cyclonedx, generate_spdx
from app.main import app
from app.storage.database import get_db
from app.storage.models import Dependency, Repo, RepoSnapshot, SnapshotStatus
from tests.conftest import create_tables, drop_tables, override_get_db

app.dependency_overrides[get_db] = override_get_db

SAMPLE_DEPS = [
    {
        "name": "fastapi", "version": "0.115.0",
        "ecosystem": "pypi", "is_dev": False, "file_path": "requirements.txt",
    },
    {
        "name": "pytest", "version": "8.0.0",
        "ecosystem": "pypi", "is_dev": True, "file_path": "requirements-dev.txt",
    },
    {
        "name": "react", "version": "18.2.0",
        "ecosystem": "npm", "is_dev": False, "file_path": "package.json",
    },
]


# =======================================================================
# Unit tests: PURL
# =======================================================================


class TestPurl:

    def test_pypi(self):
        assert _to_purl("fastapi", "0.115", "pypi") == "pkg:pypi/fastapi@0.115"

    def test_npm(self):
        assert _to_purl("react", "18.2.0", "npm") == "pkg:npm/react@18.2.0"

    def test_maven(self):
        result = _to_purl("org.junit:junit", "5.0", "maven")
        assert result == "pkg:maven/org.junit/junit@5.0"

    def test_cargo(self):
        assert _to_purl("serde", "1.0", "crates") == "pkg:cargo/serde@1.0"

    def test_nuget(self):
        assert _to_purl("Newtonsoft.Json", "13.0", "nuget") == "pkg:nuget/Newtonsoft.Json@13.0"

    def test_go(self):
        assert _to_purl("github.com/gin", "1.9", "go") == "pkg:golang/github.com/gin@1.9"

    def test_unknown_ecosystem(self):
        result = _to_purl("lib", "1.0", "custom")
        assert "lib" in result
        assert "1.0" in result


# =======================================================================
# Unit tests: CycloneDX
# =======================================================================


class TestCycloneDX:

    def test_structure(self):
        sbom = generate_cyclonedx("myrepo", "snap123", SAMPLE_DEPS)
        assert sbom["bomFormat"] == "CycloneDX"
        assert sbom["specVersion"] == "1.5"
        assert "urn:uuid:" in sbom["serialNumber"]
        assert sbom["version"] == 1

    def test_metadata(self):
        sbom = generate_cyclonedx("myrepo", "snap123", SAMPLE_DEPS)
        meta = sbom["metadata"]
        assert meta["component"]["name"] == "myrepo"
        assert "Eidos" in str(meta["tools"])
        assert "timestamp" in meta

    def test_components_count(self):
        sbom = generate_cyclonedx("r", "s", SAMPLE_DEPS)
        assert len(sbom["components"]) == 3

    def test_component_fields(self):
        sbom = generate_cyclonedx("r", "s", SAMPLE_DEPS)
        comp = sbom["components"][0]
        assert comp["type"] == "library"
        assert comp["name"] == "fastapi"
        assert comp["version"] == "0.115.0"
        assert "purl" in comp
        assert comp["scope"] == "required"

    def test_dev_scope(self):
        sbom = generate_cyclonedx("r", "s", SAMPLE_DEPS)
        pytest_comp = next(c for c in sbom["components"] if c["name"] == "pytest")
        assert pytest_comp["scope"] == "optional"

    def test_purl_in_components(self):
        sbom = generate_cyclonedx("r", "s", SAMPLE_DEPS)
        comp = sbom["components"][0]
        assert comp["purl"] == "pkg:pypi/fastapi@0.115.0"

    def test_empty_deps(self):
        sbom = generate_cyclonedx("r", "s", [])
        assert sbom["components"] == []


# =======================================================================
# Unit tests: SPDX
# =======================================================================


class TestSPDX:

    def test_structure(self):
        sbom = generate_spdx("myrepo", "snap123", SAMPLE_DEPS)
        assert sbom["spdxVersion"] == "SPDX-2.3"
        assert sbom["dataLicense"] == "CC0-1.0"
        assert "SPDXID" in sbom

    def test_creation_info(self):
        sbom = generate_spdx("r", "s", SAMPLE_DEPS)
        assert "Eidos" in str(sbom["creationInfo"]["creators"])

    def test_packages_count(self):
        sbom = generate_spdx("r", "s", SAMPLE_DEPS)
        assert len(sbom["packages"]) == 3

    def test_package_fields(self):
        sbom = generate_spdx("r", "s", SAMPLE_DEPS)
        pkg = sbom["packages"][0]
        assert pkg["name"] == "fastapi"
        assert pkg["versionInfo"] == "0.115.0"
        assert "SPDXRef-Package" in pkg["SPDXID"]
        assert len(pkg["externalRefs"]) == 1
        assert "pkg:" in pkg["externalRefs"][0]["referenceLocator"]

    def test_relationships(self):
        sbom = generate_spdx("r", "s", SAMPLE_DEPS)
        assert len(sbom["relationships"]) == 3
        assert sbom["relationships"][0]["relationshipType"] == "DESCRIBES"

    def test_empty_deps(self):
        sbom = generate_spdx("r", "s", [])
        assert sbom["packages"] == []
        assert sbom["relationships"] == []


# =======================================================================
# API tests
# =======================================================================


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await drop_tables()
    await create_tables()
    async for db in override_get_db():
        db.add(Repo(id="r1", name="demo-app", url="https://example.com"))
        db.add(RepoSnapshot(
            id="s1", repo_id="r1", commit_sha="abc",
            status=SnapshotStatus.completed, file_count=3,
        ))
        db.add(Dependency(
            snapshot_id="s1", name="fastapi", version="0.115.0",
            ecosystem="pypi", file_path="requirements.txt",
            is_dev=False, is_pinned=True,
        ))
        db.add(Dependency(
            snapshot_id="s1", name="pytest", version="8.0",
            ecosystem="pypi", file_path="requirements-dev.txt",
            is_dev=True, is_pinned=True,
        ))
        db.add(Dependency(
            snapshot_id="s1", name="react", version="18.2.0",
            ecosystem="npm", file_path="package.json",
            is_dev=False, is_pinned=True,
        ))
        await db.commit()
    yield
    await drop_tables()


@pytest_asyncio.fixture
async def client():
    with patch("app.api.repos.run_ingestion", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as ac:
            yield ac


class TestSBOMEndpoint:

    @pytest.mark.asyncio
    async def test_cyclonedx_default(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/export/sbom")
        assert resp.status_code == 200
        data = resp.json()
        assert data["bomFormat"] == "CycloneDX"
        assert len(data["components"]) == 3

    @pytest.mark.asyncio
    async def test_cyclonedx_explicit(self, client):
        resp = await client.get(
            "/repos/r1/snapshots/s1/export/sbom?format=cyclonedx",
        )
        assert resp.json()["bomFormat"] == "CycloneDX"

    @pytest.mark.asyncio
    async def test_spdx(self, client):
        resp = await client.get(
            "/repos/r1/snapshots/s1/export/sbom?format=spdx",
        )
        data = resp.json()
        assert data["spdxVersion"] == "SPDX-2.3"
        assert len(data["packages"]) == 3

    @pytest.mark.asyncio
    async def test_exclude_dev(self, client):
        resp = await client.get(
            "/repos/r1/snapshots/s1/export/sbom?include_dev=false",
        )
        data = resp.json()
        assert len(data["components"]) == 2  # no pytest

    @pytest.mark.asyncio
    async def test_invalid_format(self, client):
        resp = await client.get(
            "/repos/r1/snapshots/s1/export/sbom?format=invalid",
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_404_unknown_snapshot(self, client):
        resp = await client.get("/repos/r1/snapshots/bad/export/sbom")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_content_disposition(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/export/sbom")
        assert "attachment" in resp.headers.get("content-disposition", "")
        assert "cyclonedx" in resp.headers.get("content-disposition", "")

    @pytest.mark.asyncio
    async def test_spdx_content_disposition(self, client):
        resp = await client.get(
            "/repos/r1/snapshots/s1/export/sbom?format=spdx",
        )
        assert "spdx" in resp.headers.get("content-disposition", "")
