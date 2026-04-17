"""
Data model and schema validation tests.

Tests all Pydantic schemas, DB model constraints, and serialization.
"""

import pytest
from pydantic import ValidationError

from app.auth.github_oauth import GitHubUser
from app.auth.google_oauth import GoogleUser
from app.guardrails.models import (
    EvalCategory,
    EvalSeverity,
    SanitizationResult,
)
from app.storage.models import SnapshotStatus
from app.storage.schemas import (
    AnalysisOverview,
    ChangedSymbolOut,
    CitationOut,
    EdgeOut,
    EntryPointOut,
    EvalCheckOut,
    EvalReportOut,
    FileOut,
    GeneratedDocOut,
    GenerateDocsRequest,
    GenerateDocsResponse,
    GraphNeighborhood,
    IndexingStats,
    IngestRequest,
    MetricsOut,
    ModuleOut,
    RepoCreate,
    RepoOut,
    ReviewFindingOut,
    ReviewReportOut,
    ReviewRequest,
    SearchResultOut,
    SnapshotDetail,
    SnapshotOut,
    SymbolOut,
)


class TestRepoSchemas:
    def test_repo_create_valid(self):
        r = RepoCreate(name="test", url="https://github.com/x/y")
        assert r.name == "test"

    def test_repo_create_invalid_url(self):
        with pytest.raises(ValidationError):
            RepoCreate(name="test", url="not-a-url")

    def test_repo_create_default_branch(self):
        r = RepoCreate(name="t", url="https://github.com/x/y")
        assert r.default_branch == "main"

    def test_repo_create_custom_branch(self):
        r = RepoCreate(name="t", url="https://github.com/x/y", default_branch="develop")
        assert r.default_branch == "develop"

    def test_repo_out(self):
        r = RepoOut(
            id="1", name="t", url="https://x.com", default_branch="main", created_at="2024-01-01"
        )
        assert r.last_indexed_at is None

    def test_ingest_request_optional_sha(self):
        r = IngestRequest()
        assert r.commit_sha is None

    def test_ingest_request_with_sha(self):
        r = IngestRequest(commit_sha="abc123")
        assert r.commit_sha == "abc123"


class TestSnapshotSchemas:
    def test_snapshot_out(self):
        s = SnapshotOut(
            id="s1",
            repo_id="r1",
            commit_sha=None,
            status=SnapshotStatus.pending,
            file_count=0,
            created_at="2024-01-01",
        )
        assert s.error_message is None

    def test_snapshot_detail(self):
        s = SnapshotDetail(
            id="s1",
            repo_id="r1",
            commit_sha="abc",
            status=SnapshotStatus.completed,
            file_count=1,
            created_at="2024-01-01",
            files=[FileOut(id=1, path="x.cs", language="csharp", hash="h", size_bytes=100)],
        )
        assert len(s.files) == 1


class TestSymbolSchemas:
    def test_symbol_out(self):
        s = SymbolOut(
            id=1,
            kind="class",
            name="Foo",
            fq_name="App.Foo",
            file_path="Foo.cs",
            start_line=1,
            end_line=10,
        )
        assert s.namespace == ""

    def test_edge_out(self):
        e = EdgeOut(id=1, source_fq_name="A", target_fq_name="B", edge_type="calls")
        assert e.line == 0

    def test_graph_neighborhood(self):
        sym = SymbolOut(
            id=1, kind="class", name="X", fq_name="X", file_path="x.cs", start_line=1, end_line=5
        )
        g = GraphNeighborhood(symbol=sym, callers=[], callees=[], children=[])
        assert len(g.callers) == 0


class TestAnalysisSchemas:
    def test_entry_point(self):
        e = EntryPointOut(symbol_fq_name="A.Main", kind="method", file_path="a.cs", line=5)
        assert e.route == ""

    def test_metrics(self):
        m = MetricsOut(
            fq_name="A",
            kind="method",
            lines_of_code=50,
            fan_in=3,
            fan_out=2,
            child_count=0,
            is_public=True,
            is_static=False,
        )
        assert m.fan_in == 3

    def test_module_out(self):
        m = ModuleOut(
            name="App",
            file_count=3,
            symbol_count=10,
            files=["a.cs", "b.cs", "c.cs"],
            dependencies=["Lib"],
        )
        assert len(m.files) == 3

    def test_overview(self):
        o = AnalysisOverview(
            snapshot_id="s1",
            total_symbols=10,
            total_edges=5,
            total_modules=2,
            symbols_by_kind={"class": 3},
            entry_points=[],
            hotspots=[],
        )
        assert o.total_symbols == 10


class TestIndexingSchemas:
    def test_citation(self):
        c = CitationOut(file_path="x.cs")
        assert c.symbol_fq_name == ""

    def test_search_result(self):
        s = SearchResultOut(scope_type="symbol", text="hello", score=0.9, refs=[])
        assert s.metadata == {}

    def test_indexing_stats(self):
        s = IndexingStats(
            symbol_summaries=10, module_summaries=2, file_summaries=5, vectors_stored=17
        )
        assert s.vectors_stored == 17


class TestReviewSchemas:
    def test_review_request(self):
        r = ReviewRequest(diff="--- a/x.cs\n+++ b/x.cs\n@@ -1 +1 @@\n-old\n+new")
        assert r.max_hops == 3

    def test_changed_symbol(self):
        c = ChangedSymbolOut(
            fq_name="A", kind="method", file_path="a.cs", start_line=1, end_line=10
        )
        assert c.change_type == "modified"

    def test_review_finding(self):
        f = ReviewFindingOut(
            category="bug",
            severity="high",
            title="Null ref",
            description="Possible null",
            file_path="x.cs",
        )
        assert f.suggestion == ""

    def test_review_report(self):
        r = ReviewReportOut(
            snapshot_id="s1",
            diff_summary="1 file",
            files_changed=["x.cs"],
            changed_symbols=[],
            findings=[],
            impacted_symbols=[],
            risk_score=50,
            risk_level="medium",
        )
        assert r.llm_summary == ""


class TestDocgenSchemas:
    def test_generate_request_defaults(self):
        r = GenerateDocsRequest()
        assert r.doc_type is None
        assert r.scope_id == ""

    def test_generated_doc_out(self):
        d = GeneratedDocOut(doc_type="readme", title="README", markdown="# Hi")
        assert d.llm_narrative == ""

    def test_generate_response(self):
        r = GenerateDocsResponse(snapshot_id="s1", documents=[], total=0)
        assert r.total == 0


class TestEvalSchemas:
    def test_eval_check_out(self):
        c = EvalCheckOut(
            category="hallucination",
            name="h1",
            passed=True,
            severity="pass",
            score=1.0,
            message="ok",
        )
        assert c.details == {}

    def test_eval_report_out(self):
        r = EvalReportOut(
            snapshot_id="s1",
            scope="snapshot",
            overall_score=0.8,
            overall_severity="pass",
            checks=[],
            summary="ok",
        )
        assert r.id is None


class TestGuardrailModels:
    def test_eval_categories(self):
        assert len(EvalCategory) >= 8

    def test_eval_severities(self):
        assert EvalSeverity.PASS.value == "pass"
        assert EvalSeverity.WARNING.value == "warning"
        assert EvalSeverity.FAIL.value == "fail"

    def test_sanitization_result(self):
        r = SanitizationResult(clean_text="clean")
        assert not r.was_modified


class TestOAuthDataclasses:
    def test_github_user(self):
        u = GitHubUser(id=1, login="octo", name="Octo", email="o@g.com", avatar_url="http://a")
        assert u.login == "octo"

    def test_google_user(self):
        u = GoogleUser(
            id="123", email="u@gmail.com", name="U", picture="http://p", verified_email=True
        )
        assert u.verified_email

    def test_google_user_unverified(self):
        u = GoogleUser(id="1", email="x@y.com", name="X", picture="", verified_email=False)
        assert not u.verified_email
