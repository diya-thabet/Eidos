"""
Comprehensive Go parser tests.

Tests: packages, imports, structs, interfaces, functions, methods,
fields, receivers, call extraction, doc comments, type aliases,
edge cases, registry, pipeline integration.
"""

from app.analysis.go_parser import GoParser, parse_file
from app.analysis.models import EdgeType, SymbolKind


def _parse(code: str, path: str = "test.go"):
    return parse_file(code.encode("utf-8"), path)


def _sym(analysis, fq):
    return next((s for s in analysis.symbols if s.fq_name == fq), None)


def _edges_of(analysis, edge_type):
    return [e for e in analysis.edges if e.edge_type == edge_type]


# ------------------------------------------------------------------
# Package declaration
# ------------------------------------------------------------------


class TestPackageDeclaration:
    def test_simple_package(self):
        r = _parse("package main")
        assert r.namespace == "main"

    def test_lib_package(self):
        r = _parse("package mylib")
        assert r.namespace == "mylib"

    def test_package_sets_fq(self):
        r = _parse("package svc\ntype Foo struct{}")
        assert _sym(r, "svc.Foo") is not None


# ------------------------------------------------------------------
# Imports
# ------------------------------------------------------------------


class TestImports:
    def test_single_import(self):
        r = _parse('package x\nimport "fmt"')
        assert "fmt" in r.using_directives

    def test_grouped_imports(self):
        r = _parse('package x\nimport (\n\t"fmt"\n\t"os"\n\t"strings"\n)')
        assert len(r.using_directives) == 3
        assert "fmt" in r.using_directives
        assert "os" in r.using_directives

    def test_third_party_import(self):
        r = _parse('package x\nimport "github.com/gin-gonic/gin"')
        assert "github.com/gin-gonic/gin" in r.using_directives

    def test_import_edges(self):
        r = _parse('package svc\nimport "fmt"')
        imp = _edges_of(r, EdgeType.IMPORTS)
        assert any(e.target_fq_name == "fmt" for e in imp)

    def test_no_imports(self):
        r = _parse("package x")
        assert r.using_directives == []


# ------------------------------------------------------------------
# Struct declarations
# ------------------------------------------------------------------


class TestStructDeclaration:
    def test_simple_struct(self):
        r = _parse("package x\ntype User struct{}")
        s = _sym(r, "x.User")
        assert s is not None
        assert s.kind == SymbolKind.STRUCT

    def test_struct_with_fields(self):
        r = _parse("package x\ntype User struct {\n\tName string\n\tAge int\n}")
        assert _sym(r, "x.User") is not None
        assert _sym(r, "x.User.Name") is not None
        assert _sym(r, "x.User.Age") is not None

    def test_field_types(self):
        r = _parse("package x\ntype Cfg struct {\n\tPort int\n}")
        f = _sym(r, "x.Cfg.Port")
        assert f.kind == SymbolKind.FIELD
        assert f.return_type == "int"

    def test_field_containment_edge(self):
        r = _parse("package x\ntype A struct {\n\tX int\n}")
        contains = _edges_of(r, EdgeType.CONTAINS)
        assert any(e.source_fq_name == "x.A" and e.target_fq_name == "x.A.X" for e in contains)

    def test_line_numbers(self):
        r = _parse("package x\n\ntype User struct {\n\tName string\n}\n")
        s = _sym(r, "x.User")
        assert s.start_line == 3
        assert s.end_line == 5

    def test_empty_struct(self):
        r = _parse("package x\ntype Empty struct{}")
        assert _sym(r, "x.Empty") is not None


# ------------------------------------------------------------------
# Interface declarations
# ------------------------------------------------------------------


class TestInterfaceDeclaration:
    def test_simple_interface(self):
        r = _parse("package x\ntype Repo interface{}")
        s = _sym(r, "x.Repo")
        assert s is not None
        assert s.kind == SymbolKind.INTERFACE

    def test_interface_with_methods(self):
        r = _parse(
            "package x\ntype Repo interface {\n"
            "\tFind(id string) error\n"
            "\tSave(item string) error\n"
            "}"
        )
        assert _sym(r, "x.Repo") is not None
        assert _sym(r, "x.Repo.Find") is not None
        assert _sym(r, "x.Repo.Save") is not None

    def test_interface_method_containment(self):
        r = _parse("package x\ntype Svc interface {\n\tRun() error\n}")
        contains = _edges_of(r, EdgeType.CONTAINS)
        assert any(
            e.source_fq_name == "x.Svc" and e.target_fq_name == "x.Svc.Run" for e in contains
        )

    def test_interface_method_params(self):
        r = _parse("package x\ntype R interface {\n\tGet(id string) error\n}")
        m = _sym(r, "x.R.Get")
        assert len(m.parameters) >= 1


# ------------------------------------------------------------------
# Functions (top-level)
# ------------------------------------------------------------------


class TestFunctionDeclaration:
    def test_simple_function(self):
        r = _parse("package x\nfunc Run() {}")
        s = _sym(r, "x.Run")
        assert s is not None
        assert s.kind == SymbolKind.METHOD

    def test_function_parameters(self):
        r = _parse("package x\nfunc Add(a int, b int) int { return 0 }")
        s = _sym(r, "x.Add")
        assert len(s.parameters) == 2

    def test_function_return_type(self):
        r = _parse('package x\nfunc Get() string { return "" }')
        s = _sym(r, "x.Get")
        assert "string" in s.return_type

    def test_function_multi_return(self):
        r = _parse('package x\nfunc Load() (string, error) { return "", nil }')
        s = _sym(r, "x.Load")
        assert "error" in s.return_type

    def test_function_calls(self):
        r = _parse("package x\nfunc Run() { helper() }")
        calls = _edges_of(r, EdgeType.CALLS)
        assert any(e.target_fq_name == "helper" for e in calls)

    def test_main_function(self):
        r = _parse("package main\nfunc main() {}")
        assert _sym(r, "main.main") is not None

    def test_function_signature(self):
        r = _parse('package x\nfunc Run(n int) string { return "" }')
        s = _sym(r, "x.Run")
        assert "Run" in s.signature
        assert "int" in s.signature


# ------------------------------------------------------------------
# Methods (with receiver)
# ------------------------------------------------------------------


class TestMethodDeclaration:
    def test_pointer_receiver(self):
        r = _parse("package x\ntype A struct{}\nfunc (a *A) Run() {}")
        m = _sym(r, "x.A.Run")
        assert m is not None
        assert m.parent_fq_name == "x.A"

    def test_value_receiver(self):
        r = _parse("package x\ntype A struct{}\nfunc (a A) Run() {}")
        m = _sym(r, "x.A.Run")
        assert m is not None

    def test_method_containment(self):
        r = _parse("package x\ntype A struct{}\nfunc (a *A) Do() {}")
        contains = _edges_of(r, EdgeType.CONTAINS)
        assert any(e.source_fq_name == "x.A" and e.target_fq_name == "x.A.Do" for e in contains)

    def test_method_calls(self):
        r = _parse("package x\ntype A struct{}\nfunc (a *A) Run() { helper(); other() }")
        targets = {e.target_fq_name for e in _edges_of(r, EdgeType.CALLS)}
        assert "helper" in targets
        assert "other" in targets

    def test_method_parameters(self):
        r = _parse("package x\ntype A struct{}\nfunc (a *A) Set(key string, val int) {}")
        m = _sym(r, "x.A.Set")
        assert len(m.parameters) == 2

    def test_method_return_type(self):
        r = _parse('package x\ntype A struct{}\nfunc (a *A) Get() string { return "" }')
        m = _sym(r, "x.A.Get")
        assert "string" in m.return_type

    def test_selector_call(self):
        r = _parse("package x\ntype A struct{}\nfunc (a *A) Run() { fmt.Println() }")
        calls = _edges_of(r, EdgeType.CALLS)
        assert any(e.target_fq_name == "Println" for e in calls)


# ------------------------------------------------------------------
# Call extraction
# ------------------------------------------------------------------


class TestCallExtraction:
    def test_simple_call(self):
        r = _parse("package x\nfunc Run() { doStuff() }")
        calls = _edges_of(r, EdgeType.CALLS)
        assert any(e.target_fq_name == "doStuff" for e in calls)

    def test_multiple_calls(self):
        r = _parse("package x\nfunc Run() { a(); b(); c() }")
        targets = {e.target_fq_name for e in _edges_of(r, EdgeType.CALLS)}
        assert {"a", "b", "c"} <= targets

    def test_nested_calls(self):
        r = _parse("package x\nfunc Run() { outer(inner()) }")
        targets = {e.target_fq_name for e in _edges_of(r, EdgeType.CALLS)}
        assert "outer" in targets
        assert "inner" in targets

    def test_method_call_on_object(self):
        r = _parse("package x\nfunc Run() { obj.Method() }")
        calls = _edges_of(r, EdgeType.CALLS)
        assert any(e.target_fq_name == "Method" for e in calls)

    def test_call_line_number(self):
        r = _parse("package x\nfunc Run() {\n\tx := 1\n\thelper()\n}")
        calls = _edges_of(r, EdgeType.CALLS)
        assert calls[0].line == 4


# ------------------------------------------------------------------
# Doc comments
# ------------------------------------------------------------------


class TestDocComments:
    def test_struct_doc(self):
        r = _parse("package x\n// User is a model.\ntype User struct{}")
        s = _sym(r, "x.User")
        assert "User is a model" in s.doc_comment

    def test_function_doc(self):
        r = _parse("package x\n// Run starts.\nfunc Run() {}")
        s = _sym(r, "x.Run")
        assert "Run starts" in s.doc_comment

    def test_no_doc(self):
        r = _parse("package x\nfunc Run() {}")
        assert _sym(r, "x.Run").doc_comment == ""


# ------------------------------------------------------------------
# Type aliases
# ------------------------------------------------------------------


class TestTypeAlias:
    def test_simple_alias(self):
        r = _parse("package x\ntype ID string")
        s = _sym(r, "x.ID")
        assert s is not None

    def test_numeric_alias(self):
        r = _parse("package x\ntype Status int")
        assert _sym(r, "x.Status") is not None


# ------------------------------------------------------------------
# Multiple declarations
# ------------------------------------------------------------------


class TestMultipleDeclarations:
    def test_struct_and_interface(self):
        r = _parse(
            "package x\ntype Repo interface { Find() error }\ntype SqlRepo struct { db string }\n"
        )
        assert _sym(r, "x.Repo") is not None
        assert _sym(r, "x.SqlRepo") is not None

    def test_full_file(self):
        r = _parse(
            "package svc\n"
            'import "fmt"\n'
            "type User struct { Name string }\n"
            "type Repo interface { Find(id string) error }\n"
            "func NewUser(name string) *User { return nil }\n"
            "func (u *User) Greet() { fmt.Println() }\n"
        )
        assert r.namespace == "svc"
        assert "fmt" in r.using_directives
        assert _sym(r, "svc.User") is not None
        assert _sym(r, "svc.User.Name") is not None
        assert _sym(r, "svc.Repo") is not None
        assert _sym(r, "svc.Repo.Find") is not None
        assert _sym(r, "svc.NewUser") is not None
        assert _sym(r, "svc.User.Greet") is not None
        calls = _edges_of(r, EdgeType.CALLS)
        assert any(e.target_fq_name == "Println" for e in calls)


# ------------------------------------------------------------------
# Edge cases
# ------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_file(self):
        r = _parse("")
        assert r.symbols == []

    def test_package_only(self):
        r = _parse("package x")
        assert r.namespace == "x"
        assert r.symbols == []

    def test_comment_only(self):
        r = _parse("package x\n// just a comment\n")
        assert r.symbols == []

    def test_syntax_error_partial(self):
        r = _parse("package x\ntype A struct { broken }")
        assert _sym(r, "x.A") is not None

    def test_file_path_preserved(self):
        r = _parse("package x\ntype A struct{}", "cmd/main.go")
        assert r.path == "cmd/main.go"
        assert r.symbols[0].file_path == "cmd/main.go"

    def test_long_name(self):
        name = "A" * 200
        r = _parse(f"package x\ntype {name} struct{{}}")
        assert _sym(r, f"x.{name}") is not None


# ------------------------------------------------------------------
# Parser interface
# ------------------------------------------------------------------


class TestGoParserInterface:
    def test_language_id(self):
        assert GoParser().language_id == "go"

    def test_parse_via_interface(self):
        p = GoParser()
        r = p.parse_file(b"package x\ntype Foo struct{}", "foo.go")
        assert _sym(r, "x.Foo") is not None

    def test_complex_parse(self):
        p = GoParser()
        code = (
            b"package svc\n"
            b'import "fmt"\n'
            b"type Handler struct { name string }\n"
            b"type Service interface { Run() error }\n"
            b"func NewHandler(n string) *Handler { return nil }\n"
            b"func (h *Handler) Handle() { fmt.Println(); helper() }\n"
        )
        r = p.parse_file(code, "svc/handler.go")
        assert r.namespace == "svc"
        assert _sym(r, "svc.Handler") is not None
        assert _sym(r, "svc.Handler.name") is not None
        assert _sym(r, "svc.Service") is not None
        assert _sym(r, "svc.Service.Run") is not None
        assert _sym(r, "svc.NewHandler") is not None
        assert _sym(r, "svc.Handler.Handle") is not None
        calls = _edges_of(r, EdgeType.CALLS)
        targets = {e.target_fq_name for e in calls}
        assert "Println" in targets
        assert "helper" in targets


# ------------------------------------------------------------------
# Registry integration
# ------------------------------------------------------------------


class TestRegistryIntegration:
    def test_go_registered(self):
        from app.analysis.parser_registry import supported_languages

        assert "go" in supported_languages()

    def test_get_parser(self):
        from app.analysis.parser_registry import get_parser

        p = get_parser("go")
        assert p is not None
        assert p.language_id == "go"

    def test_all_six_registered(self):
        from app.analysis.parser_registry import supported_languages

        langs = supported_languages()
        assert {"csharp", "java", "python", "typescript", "tsx", "go"} <= langs


# ------------------------------------------------------------------
# Pipeline integration
# ------------------------------------------------------------------


class TestPipelineIntegration:
    def test_analyze_go_files(self, tmp_path):
        from app.analysis.pipeline import analyze_snapshot_files

        f = tmp_path / "main.go"
        f.write_text("package main\ntype Svc struct{}\nfunc (s *Svc) Run() { helper() }\n")
        records = [{"path": "main.go", "language": "go"}]
        graph = analyze_snapshot_files(tmp_path, records)
        assert "main.Svc" in graph.symbols
        assert "main.Svc.Run" in graph.symbols

    def test_mixed_five_languages(self, tmp_path):
        from app.analysis.pipeline import analyze_snapshot_files

        (tmp_path / "A.cs").write_text("class CsA { void Run() {} }")
        (tmp_path / "B.java").write_text("class JavaB { void go() {} }")
        (tmp_path / "c.py").write_text("class PyC:\n    def do(self):\n        pass\n")
        (tmp_path / "d.ts").write_text("export class TsD { run() {} }")
        (tmp_path / "e.go").write_text("package main\ntype GoE struct{}\nfunc (g *GoE) Run() {}")

        records = [
            {"path": "A.cs", "language": "csharp"},
            {"path": "B.java", "language": "java"},
            {"path": "c.py", "language": "python"},
            {"path": "d.ts", "language": "typescript"},
            {"path": "e.go", "language": "go"},
        ]
        graph = analyze_snapshot_files(tmp_path, records)
        assert "CsA" in graph.symbols
        assert "JavaB" in graph.symbols
        assert "c.PyC" in graph.symbols
        assert "d.TsD" in graph.symbols
        assert "main.GoE" in graph.symbols
