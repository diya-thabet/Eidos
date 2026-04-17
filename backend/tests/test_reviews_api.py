"""
Tests for the review API endpoints.

Covers: submit review, list reviews, response structure,
error handling, persistence.
"""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.storage.database import get_db
from app.storage.models import Edge, Repo, RepoSnapshot, SnapshotStatus, Symbol
from tests.conftest import create_tables, drop_tables, override_get_db, test_sessionmaker

app.dependency_overrides[get_db] = override_get_db

DIFF = """\
diff --git a/Services/Foo.cs b/Services/Foo.cs
--- a/Services/Foo.cs
+++ b/Services/Foo.cs
@@ -5,5 +5,5 @@ public class Foo
-    if (x == null) throw new ArgumentNullException();
+    // removed check
     return x.ToString();
"""


async def _seed():
    async with test_sessionmaker() as db:
        db.add(Repo(id="r-rev", name="test", url="https://example.com", default_branch="main"))
        db.add(
            RepoSnapshot(
                id="s-rev", repo_id="r-rev", commit_sha="abc", status=SnapshotStatus.completed
            )
        )
        await db.flush()

        db.add(
            Symbol(
                snapshot_id="s-rev",
                kind="method",
                name="DoWork",
                fq_name="MyApp.Foo.DoWork",
                file_path="Services/Foo.cs",
                start_line=4,
                end_line=8,
                namespace="MyApp",
                modifiers="public",
            )
        )
        await db.flush()

        db.add(
            Edge(
                snapshot_id="s-rev",
                source_fq_name="MyApp.Bar.Call",
                target_fq_name="MyApp.Foo.DoWork",
                edge_type="calls",
                file_path="Bar.cs",
                line=10,
            )
        )
        await db.commit()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await create_tables()
    await _seed()
    yield
    await drop_tables()


@pytest_asyncio.fixture
async def client():
    with patch("app.api.repos.run_ingestion", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


class TestReviewEndpoint:
    @pytest.mark.asyncio
    async def test_review_returns_200(self, client):
        resp = await client.post("/repos/r-rev/snapshots/s-rev/review", json={"diff": DIFF})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_response_structure(self, client):
        resp = await client.post("/repos/r-rev/snapshots/s-rev/review", json={"diff": DIFF})
        data = resp.json()
        assert "snapshot_id" in data
        assert "diff_summary" in data
        assert "files_changed" in data
        assert "changed_symbols" in data
        assert "findings" in data
        assert "impacted_symbols" in data
        assert "risk_score" in data
        assert "risk_level" in data

    @pytest.mark.asyncio
    async def test_findings_present(self, client):
        resp = await client.post("/repos/r-rev/snapshots/s-rev/review", json={"diff": DIFF})
        data = resp.json()
        assert len(data["findings"]) >= 1

    @pytest.mark.asyncio
    async def test_finding_structure(self, client):
        resp = await client.post("/repos/r-rev/snapshots/s-rev/review", json={"diff": DIFF})
        finding = resp.json()["findings"][0]
        assert "category" in finding
        assert "severity" in finding
        assert "title" in finding
        assert "description" in finding
        assert "file_path" in finding

    @pytest.mark.asyncio
    async def test_risk_score_is_number(self, client):
        resp = await client.post("/repos/r-rev/snapshots/s-rev/review", json={"diff": DIFF})
        data = resp.json()
        assert isinstance(data["risk_score"], int)
        assert data["risk_level"] in ("low", "medium", "high", "critical")

    @pytest.mark.asyncio
    async def test_review_persisted(self, client):
        await client.post("/repos/r-rev/snapshots/s-rev/review", json={"diff": DIFF})
        resp = await client.get("/repos/r-rev/snapshots/s-rev/reviews")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    @pytest.mark.asyncio
    async def test_snapshot_not_found(self, client):
        resp = await client.post("/repos/r-rev/snapshots/nonexistent/review", json={"diff": DIFF})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_empty_diff(self, client):
        resp = await client.post("/repos/r-rev/snapshots/s-rev/review", json={"diff": ""})
        data = resp.json()
        assert data["files_changed"] == []
        assert data["findings"] == []


class TestListReviews:
    @pytest.mark.asyncio
    async def test_list_empty(self, client):
        resp = await client.get("/repos/r-rev/snapshots/s-rev/reviews")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_after_review(self, client):
        await client.post("/repos/r-rev/snapshots/s-rev/review", json={"diff": DIFF})
        await client.post("/repos/r-rev/snapshots/s-rev/review", json={"diff": DIFF})
        resp = await client.get("/repos/r-rev/snapshots/s-rev/reviews")
        assert len(resp.json()) == 2

    @pytest.mark.asyncio
    async def test_review_has_id(self, client):
        await client.post("/repos/r-rev/snapshots/s-rev/review", json={"diff": DIFF})
        resp = await client.get("/repos/r-rev/snapshots/s-rev/reviews")
        assert resp.json()[0]["id"] is not None

    @pytest.mark.asyncio
    async def test_snapshot_not_found(self, client):
        resp = await client.get("/repos/r-rev/snapshots/bad/reviews")
        assert resp.status_code == 404
