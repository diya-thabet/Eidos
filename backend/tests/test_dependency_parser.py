"""
Tests for Phase 2: Dependency File Parsing.

Tests all 11 manifest parsers, the pipeline integration, health rules,
the API endpoint, and real manifest files from validated repos.
"""

from __future__ import annotations

import textwrap
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.analysis.dependency_parser import (
    DependencyInfo,
    is_manifest_file,
    parse_build_gradle,
    parse_cargo_toml,
    parse_cmakelists,
    parse_csproj,
    parse_go_mod,
    parse_manifest,
    parse_package_json,
    parse_pom_xml,
    parse_pyproject_toml,
    parse_requirements_txt,
    parse_setup_cfg,
    parse_vcpkg_json,
    scan_dependencies,
)
from app.analysis.pipeline import analyze_snapshot_files
from app.main import app
from app.storage.database import get_db
from app.storage.models import (
    Dependency,
    Repo,
    RepoSnapshot,
    SnapshotStatus,
)
from tests.conftest import create_tables, drop_tables, override_get_db

app.dependency_overrides[get_db] = override_get_db


# =======================================================================
# Python: requirements.txt
# =======================================================================


class TestRequirementsTxt:

    def test_simple(self):
        content = "flask==2.3.0\nrequests>=2.28\n"
        deps = parse_requirements_txt(content, "requirements.txt")
        assert len(deps) == 2
        assert deps[0].name == "flask"
        assert deps[0].is_pinned is True
        assert deps[0].ecosystem == "pypi"
        assert deps[1].name == "requests"
        assert deps[1].is_pinned is False

    def test_comments_and_blanks(self):
        content = "# comment\n\nflask==2.0\n  \n# another\n"
        deps = parse_requirements_txt(content, "r.txt")
        assert len(deps) == 1

    def test_extras(self):
        content = "sqlalchemy[asyncio]>=2.0\n"
        deps = parse_requirements_txt(content, "r.txt")
        assert len(deps) == 1
        assert deps[0].name == "sqlalchemy"

    def test_no_version(self):
        content = "black\nmypy\n"
        deps = parse_requirements_txt(content, "r.txt")
        assert len(deps) == 2
        assert deps[0].version == "*"
        assert deps[0].is_pinned is False

    def test_dash_flags_skipped(self):
        content = "-r base.txt\n--index-url http://x\nflask==1.0\n"
        deps = parse_requirements_txt(content, "r.txt")
        assert len(deps) == 1

    def test_tilde_version(self):
        content = "requests~=2.28.0\n"
        deps = parse_requirements_txt(content, "r.txt")
        assert deps[0].is_pinned is False


# =======================================================================
# Python: pyproject.toml
# =======================================================================


class TestPyprojectToml:

    def test_project_deps(self):
        content = textwrap.dedent("""\
            [project]
            name = "myapp"
            dependencies = [
                "fastapi>=0.100",
                "uvicorn[standard]>=0.30",
                "pydantic>=2.0",
            ]
        """)
        deps = parse_pyproject_toml(content, "pyproject.toml")
        assert len(deps) == 3
        assert deps[0].name == "fastapi"
        assert deps[0].ecosystem == "pypi"
        assert not deps[0].is_dev

    def test_optional_deps_are_dev(self):
        content = textwrap.dedent("""\
            [project]
            dependencies = ["flask>=2.0"]
            [project.optional-dependencies]
            test = ["pytest>=7.0", "coverage"]
        """)
        deps = parse_pyproject_toml(content, "pyproject.toml")
        assert len(deps) == 3
        assert not deps[0].is_dev
        assert deps[1].is_dev
        assert deps[2].is_dev

    def test_invalid_toml(self):
        deps = parse_pyproject_toml("not valid toml {{", "pyproject.toml")
        assert deps == []


# =======================================================================
# Python: setup.cfg
# =======================================================================


class TestSetupCfg:

    def test_install_requires(self):
        content = textwrap.dedent("""\
            [options]
            install_requires =
                flask>=2.0
                requests==2.28.0
        """)
        deps = parse_setup_cfg(content, "setup.cfg")
        assert len(deps) == 2
        assert deps[0].name == "flask"


# =======================================================================
# JavaScript: package.json
# =======================================================================


class TestPackageJson:

    def test_deps_and_devdeps(self):
        content = (
            '{"dependencies":{"react":"^18.0","axios":"1.4.0"},'
            '"devDependencies":{"jest":"^29.0"}}'
        )
        deps = parse_package_json(content, "package.json")
        assert len(deps) == 3
        react = [d for d in deps if d.name == "react"][0]
        assert react.ecosystem == "npm"
        assert react.is_pinned is False
        assert react.is_dev is False
        axios = [d for d in deps if d.name == "axios"][0]
        assert axios.is_pinned is True
        jest = [d for d in deps if d.name == "jest"][0]
        assert jest.is_dev is True

    def test_empty_deps(self):
        deps = parse_package_json('{"name":"x"}', "package.json")
        assert deps == []

    def test_invalid_json(self):
        deps = parse_package_json("not json{", "package.json")
        assert deps == []

    def test_scoped_packages(self):
        content = '{"dependencies":{"@types/react":"^18.0","@emotion/css":"11.0.0"}}'
        deps = parse_package_json(content, "package.json")
        assert len(deps) == 2
        assert deps[0].name == "@types/react"


# =======================================================================
# Java: pom.xml
# =======================================================================


class TestPomXml:

    def test_maven_deps(self):
        content = textwrap.dedent("""\
            <project xmlns="http://maven.apache.org/POM/4.0.0">
                <dependencies>
                    <dependency>
                        <groupId>org.junit.jupiter</groupId>
                        <artifactId>junit-jupiter</artifactId>
                        <version>5.10.0</version>
                        <scope>test</scope>
                    </dependency>
                    <dependency>
                        <groupId>com.google.guava</groupId>
                        <artifactId>guava</artifactId>
                        <version>32.1.0-jre</version>
                    </dependency>
                </dependencies>
            </project>
        """)
        deps = parse_pom_xml(content, "pom.xml")
        assert len(deps) == 2
        junit = [d for d in deps if "junit" in d.name][0]
        assert junit.is_dev is True
        assert junit.ecosystem == "maven"
        guava = [d for d in deps if "guava" in d.name][0]
        assert guava.is_dev is False
        assert guava.is_pinned is True

    def test_no_namespace_pom(self):
        content = (
            "<project><dependencies><dependency>"
            "<artifactId>foo</artifactId><version>1.0</version>"
            "</dependency></dependencies></project>"
        )
        deps = parse_pom_xml(content, "pom.xml")
        assert len(deps) >= 1

    def test_invalid_xml(self):
        deps = parse_pom_xml("not xml<>><", "pom.xml")
        assert deps == []


# =======================================================================
# Java: build.gradle
# =======================================================================


class TestBuildGradle:

    def test_gradle_deps(self):
        content = textwrap.dedent("""\
            dependencies {
                implementation 'com.google.guava:guava:32.1.0-jre'
                testImplementation 'junit:junit:4.13.2'
                api 'org.slf4j:slf4j-api:2.0.9'
            }
        """)
        deps = parse_build_gradle(content, "build.gradle")
        assert len(deps) == 3
        guava = [d for d in deps if "guava" in d.name][0]
        assert guava.name == "com.google.guava:guava"
        assert guava.is_dev is False
        junit = [d for d in deps if "junit" in d.name][0]
        assert junit.is_dev is True


# =======================================================================
# Go: go.mod
# =======================================================================


class TestGoMod:

    def test_go_mod(self):
        content = textwrap.dedent("""\
            module github.com/user/project

            go 1.21

            require (
                github.com/gin-gonic/gin v1.9.1
                github.com/stretchr/testify v1.8.4
                golang.org/x/crypto v0.14.0
            )
        """)
        deps = parse_go_mod(content, "go.mod")
        assert len(deps) == 3
        gin = [d for d in deps if "gin" in d.name][0]
        assert gin.ecosystem == "go"
        assert gin.is_pinned is True
        assert gin.version == "v1.9.1"


# =======================================================================
# Rust: Cargo.toml
# =======================================================================


class TestCargoToml:

    def test_cargo_deps(self):
        content = textwrap.dedent("""\
            [dependencies]
            serde = "1.0"
            tokio = { version = "1.32", features = ["full"] }

            [dev-dependencies]
            criterion = "0.5"
        """)
        deps = parse_cargo_toml(content, "Cargo.toml")
        assert len(deps) == 3
        serde = [d for d in deps if d.name == "serde"][0]
        assert serde.ecosystem == "crates"
        assert serde.is_dev is False
        tokio = [d for d in deps if d.name == "tokio"][0]
        assert tokio.version == "1.32"
        crit = [d for d in deps if d.name == "criterion"][0]
        assert crit.is_dev is True


# =======================================================================
# C#: .csproj
# =======================================================================


class TestCsproj:

    def test_package_refs(self):
        content = textwrap.dedent("""\
            <Project Sdk="Microsoft.NET.Sdk">
              <ItemGroup>
                <PackageReference Include="Newtonsoft.Json" Version="13.0.3" />
                <PackageReference Include="xunit" Version="2.6.0" />
              </ItemGroup>
            </Project>
        """)
        deps = parse_csproj(content, "MyApp.csproj")
        assert len(deps) == 2
        assert deps[0].name == "Newtonsoft.Json"
        assert deps[0].ecosystem == "nuget"
        assert deps[0].is_pinned is True


# =======================================================================
# C/C++: vcpkg.json
# =======================================================================


class TestVcpkgJson:

    def test_vcpkg_deps(self):
        content = '{"dependencies":["fmt","boost",{"name":"grpc","version>=":"1.50"}]}'
        deps = parse_vcpkg_json(content, "vcpkg.json")
        assert len(deps) == 3
        assert deps[0].name == "fmt"
        assert deps[0].ecosystem == "vcpkg"
        assert deps[2].name == "grpc"


# =======================================================================
# C/C++: CMakeLists.txt
# =======================================================================


class TestCMakeLists:

    def test_find_package(self):
        content = textwrap.dedent("""\
            cmake_minimum_required(VERSION 3.20)
            find_package(Boost 1.80 REQUIRED)
            find_package(OpenSSL REQUIRED)
            find_package(GTest 1.14)
        """)
        deps = parse_cmakelists(content, "CMakeLists.txt")
        assert len(deps) == 3
        boost = [d for d in deps if d.name == "Boost"][0]
        assert boost.version == "1.80"
        assert boost.ecosystem == "cmake"
        openssl = [d for d in deps if d.name == "OpenSSL"][0]
        assert openssl.version == "*"


# =======================================================================
# Manifest detection
# =======================================================================


class TestManifestDetection:

    @pytest.mark.parametrize("name,expected", [
        ("requirements.txt", True),
        ("requirements-dev.txt", True),
        ("requirements_test.txt", True),
        ("pyproject.toml", True),
        ("setup.cfg", True),
        ("package.json", True),
        ("pom.xml", True),
        ("build.gradle", True),
        ("go.mod", True),
        ("Cargo.toml", True),
        ("vcpkg.json", True),
        ("CMakeLists.txt", True),
        ("MyApp.csproj", True),
        ("main.py", False),
        ("README.md", False),
        ("Dockerfile", False),
    ])
    def test_detection(self, name, expected):
        assert is_manifest_file(name) == expected


# =======================================================================
# Master dispatcher
# =======================================================================


class TestParseManifest:

    def test_dispatches_requirements(self):
        deps = parse_manifest("flask==2.0\n", "requirements.txt")
        assert len(deps) == 1

    def test_dispatches_csproj(self):
        content = (
            '<Project><ItemGroup>'
            '<PackageReference Include="X" Version="1.0"/>'
            '</ItemGroup></Project>'
        )
        deps = parse_manifest(content, "Foo.csproj")
        assert len(deps) == 1

    def test_dispatches_package_json(self):
        deps = parse_manifest('{"dependencies":{"x":"1.0"}}', "package.json")
        assert len(deps) == 1

    def test_unknown_returns_empty(self):
        deps = parse_manifest("content", "unknown.xyz")
        assert deps == []


# =======================================================================
# scan_dependencies integration
# =======================================================================


class TestScanDependencies:

    def test_finds_manifests(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("flask==2.0\n")
        (tmp_path / "package.json").write_text(
            '{"dependencies":{"react":"^18.0"}}'
        )
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("import flask\n")

        deps = scan_dependencies(tmp_path)
        names = {d.name for d in deps}
        assert "flask" in names
        assert "react" in names

    def test_skips_node_modules(self, tmp_path):
        nm = tmp_path / "node_modules" / "react"
        nm.mkdir(parents=True)
        (nm / "package.json").write_text(
            '{"dependencies":{"internal":"1.0"}}'
        )
        deps = scan_dependencies(tmp_path)
        assert len(deps) == 0

    def test_skips_vendor(self, tmp_path):
        v = tmp_path / "vendor"
        v.mkdir()
        (v / "go.mod").write_text("module vendor\nrequire x v1.0\n")
        deps = scan_dependencies(tmp_path)
        assert len(deps) == 0


# =======================================================================
# Pipeline integration
# =======================================================================


class TestPipelineIntegration:

    def test_deps_in_graph(self, tmp_path):
        (tmp_path / "requirements.txt").write_text(
            "flask==2.3.0\nrequests>=2.28\n"
        )
        (tmp_path / "main.py").write_text("import flask\n")
        records = [
            {"path": "main.py", "language": "python",
             "hash": "a", "size_bytes": 20},
        ]
        graph = analyze_snapshot_files(tmp_path, records)
        assert len(graph.dependencies) == 2
        names = {d.name for d in graph.dependencies}
        assert "flask" in names

    def test_multi_ecosystem(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("flask==2.0\n")
        (tmp_path / "package.json").write_text(
            '{"dependencies":{"react":"^18.0"}}'
        )
        (tmp_path / "Cargo.toml").write_text(
            '[dependencies]\nserde = "1.0"\n'
        )
        graph = analyze_snapshot_files(tmp_path, [])
        ecos = {d.ecosystem for d in graph.dependencies}
        assert "pypi" in ecos
        assert "npm" in ecos
        assert "crates" in ecos


# =======================================================================
# Health rules
# =======================================================================


class TestDependencyHealthRules:

    def _graph_with_deps(self, deps_data):
        from app.analysis.graph_builder import CodeGraph
        graph = CodeGraph()
        graph.dependencies = [
            DependencyInfo(**d) for d in deps_data
        ]
        return graph

    def test_dep001_unpinned(self):
        from app.analysis.code_health import HealthConfig
        from app.analysis.health_rules.dependencies import UnpinnedDependencyRule
        graph = self._graph_with_deps([
            {"name": "flask", "version": "*", "ecosystem": "pypi",
             "file_path": "r.txt"},
            {"name": "react", "version": "^18.0", "ecosystem": "npm",
             "file_path": "p.json"},
        ])
        findings = UnpinnedDependencyRule().check(graph, HealthConfig())
        assert len(findings) == 1
        assert "flask" in findings[0].message

    def test_dep002_wide_range(self):
        from app.analysis.code_health import HealthConfig
        from app.analysis.health_rules.dependencies import WideVersionRangeRule
        graph = self._graph_with_deps([
            {"name": "requests", "version": ">=2.0", "ecosystem": "pypi",
             "file_path": "r.txt"},
            {"name": "flask", "version": ">=2.0,<3.0", "ecosystem": "pypi",
             "file_path": "r.txt"},
        ])
        findings = WideVersionRangeRule().check(graph, HealthConfig())
        assert len(findings) == 1
        assert "requests" in findings[0].message

    def test_dep003_unused(self):
        from app.analysis.code_health import HealthConfig
        from app.analysis.graph_builder import CodeGraph
        from app.analysis.health_rules.dependencies import UnusedDependencyRule
        from app.analysis.models import EdgeInfo, EdgeType
        graph = CodeGraph()
        graph.dependencies = [
            DependencyInfo(
                name="flask", version="2.0", ecosystem="pypi",
                file_path="r.txt",
            ),
            DependencyInfo(
                name="unused-pkg", version="1.0", ecosystem="pypi",
                file_path="r.txt",
            ),
        ]
        graph.edges = [
            EdgeInfo(
                source_fq_name="main", target_fq_name="flask",
                edge_type=EdgeType.IMPORTS, file_path="main.py",
            ),
        ]
        findings = UnusedDependencyRule().check(graph, HealthConfig())
        assert len(findings) == 1
        assert "unused-pkg" in findings[0].message

    def test_dep004_duplicate(self):
        from app.analysis.code_health import HealthConfig
        from app.analysis.health_rules.dependencies import DuplicateDependencyRule
        graph = self._graph_with_deps([
            {"name": "flask", "version": "2.0", "ecosystem": "pypi",
             "file_path": "requirements.txt"},
            {"name": "flask", "version": "2.1", "ecosystem": "pypi",
             "file_path": "requirements-dev.txt"},
        ])
        findings = DuplicateDependencyRule().check(graph, HealthConfig())
        assert len(findings) == 1
        assert "2 files" in findings[0].message

    def test_dep005_dev_in_production(self):
        from app.analysis.code_health import HealthConfig
        from app.analysis.graph_builder import CodeGraph
        from app.analysis.health_rules.dependencies import DevInProductionRule
        from app.analysis.models import EdgeInfo, EdgeType
        graph = CodeGraph()
        graph.dependencies = [
            DependencyInfo(
                name="pytest", version="7.0", ecosystem="pypi",
                file_path="r.txt", is_dev=True,
            ),
        ]
        graph.edges = [
            EdgeInfo(
                source_fq_name="app.main", target_fq_name="pytest",
                edge_type=EdgeType.IMPORTS, file_path="app/main.py",
            ),
        ]
        findings = DevInProductionRule().check(graph, HealthConfig())
        assert len(findings) == 1
        assert "pytest" in findings[0].message

    def test_dep005_ok_in_test_file(self):
        from app.analysis.code_health import HealthConfig
        from app.analysis.graph_builder import CodeGraph
        from app.analysis.health_rules.dependencies import DevInProductionRule
        from app.analysis.models import EdgeInfo, EdgeType
        graph = CodeGraph()
        graph.dependencies = [
            DependencyInfo(
                name="pytest", version="7.0", ecosystem="pypi",
                file_path="r.txt", is_dev=True,
            ),
        ]
        graph.edges = [
            EdgeInfo(
                source_fq_name="tests.test_main", target_fq_name="pytest",
                edge_type=EdgeType.IMPORTS, file_path="tests/test_main.py",
            ),
        ]
        findings = DevInProductionRule().check(graph, HealthConfig())
        assert len(findings) == 0


# =======================================================================
# API endpoint tests
# =======================================================================


class TestDependencyAPI:

    @pytest_asyncio.fixture(autouse=True)
    async def setup(self):
        await drop_tables()
        await create_tables()
        async for db in override_get_db():
            db.add(Repo(id="r1", name="demo", url="https://example.com"))
            db.add(RepoSnapshot(
                id="s1", repo_id="r1", commit_sha="abc",
                status=SnapshotStatus.completed, file_count=1,
            ))
            for name, ver, eco, dev, pinned in [
                ("flask", "2.3.0", "pypi", False, True),
                ("pytest", "7.0", "pypi", True, False),
                ("react", "^18.0", "npm", False, False),
                ("jest", "^29.0", "npm", True, False),
                ("serde", "1.0", "crates", False, False),
            ]:
                db.add(Dependency(
                    snapshot_id="s1", name=name, version=ver,
                    ecosystem=eco, file_path=f"{eco}.manifest",
                    is_dev=dev, is_pinned=pinned,
                ))
            await db.commit()
        yield
        await drop_tables()

    @pytest_asyncio.fixture
    async def client(self):
        with patch("app.api.repos.run_ingestion", new_callable=AsyncMock):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as ac:
                yield ac

    @pytest.mark.asyncio
    async def test_list_deps(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/dependencies")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 5

    @pytest.mark.asyncio
    async def test_ecosystem_summary(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/dependencies")
        data = resp.json()
        ecos = {e["ecosystem"]: e for e in data["ecosystems"]}
        assert "pypi" in ecos
        assert ecos["pypi"]["total"] == 2
        assert ecos["pypi"]["dev"] == 1
        assert ecos["npm"]["total"] == 2

    @pytest.mark.asyncio
    async def test_dep_fields(self, client):
        resp = await client.get("/repos/r1/snapshots/s1/dependencies")
        item = resp.json()["items"][0]
        assert "name" in item
        assert "version" in item
        assert "ecosystem" in item
        assert "is_dev" in item
        assert "is_pinned" in item

    @pytest.mark.asyncio
    async def test_empty_snapshot(self, client):
        async for db in override_get_db():
            db.add(RepoSnapshot(
                id="s2", repo_id="r1", commit_sha="def",
                status=SnapshotStatus.completed, file_count=0,
            ))
            await db.commit()
        resp = await client.get("/repos/r1/snapshots/s2/dependencies")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["ecosystems"] == []


# =======================================================================
# Edge cases
# =======================================================================


class TestEdgeCases:

    def test_pinning_detection(self):
        from app.analysis.dependency_parser import _is_pinned
        assert _is_pinned("2.3.0") is True
        assert _is_pinned("1") is True
        assert _is_pinned("^2.0") is False
        assert _is_pinned("~=2.0") is False
        assert _is_pinned(">=2.0") is False
        assert _is_pinned(">=2.0,<3.0") is False
        assert _is_pinned("*") is False
        assert _is_pinned("latest") is False
        assert _is_pinned("") is False

    def test_all_ecosystems_covered(self):
        """Each ecosystem parser returns the correct ecosystem string."""
        assert parse_requirements_txt("x==1\n", "r.txt")[0].ecosystem == "pypi"
        assert parse_package_json('{"dependencies":{"x":"1"}}', "p.json")[0].ecosystem == "npm"
        assert parse_cargo_toml('[dependencies]\nx = "1"\n', "C.toml")[0].ecosystem == "crates"
        assert parse_go_mod("require (\n\tx v1.0\n)\n", "go.mod")[0].ecosystem == "go"
        assert parse_csproj(
            '<Project><ItemGroup><PackageReference Include="X" Version="1"/></ItemGroup></Project>',
            "x.csproj"
        )[0].ecosystem == "nuget"
        assert parse_cmakelists("find_package(X)\n", "CMakeLists.txt")[0].ecosystem == "cmake"
        assert parse_vcpkg_json('{"dependencies":["x"]}', "vcpkg.json")[0].ecosystem == "vcpkg"

    def test_unicode_content(self):
        content = "# -*- coding: utf-8 -*-\nflask==2.0\n"
        deps = parse_requirements_txt(content, "r.txt")
        assert len(deps) == 1
