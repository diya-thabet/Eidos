"""
Comprehensive C parser tests.

Tests: includes, structs, enums, functions, typedefs, fields,
call extraction, doc comments, static functions, edge cases,
registry, pipeline.
"""

from app.analysis.c_parser import CParser, parse_file
from app.analysis.models import EdgeType, SymbolKind


def _parse(code: str, path: str = "test.c"):
    return parse_file(code.encode("utf-8"), path)


def _sym(a, fq):
    return next((s for s in a.symbols if s.fq_name == fq), None)


def _edges_of(a, t):
    return [e for e in a.edges if e.edge_type == t]


class TestIncludes:
    def test_system_include(self):
        r = _parse("#include <stdio.h>\n")
        assert "stdio.h" in r.using_directives

    def test_local_include(self):
        r = _parse('#include "myheader.h"\n')
        assert "myheader.h" in r.using_directives

    def test_multiple(self):
        r = _parse('#include <stdio.h>\n#include <stdlib.h>\n#include "app.h"\n')
        assert len(r.using_directives) == 3

    def test_include_edge(self):
        r = _parse("#include <stdio.h>\n", "main.c")
        imp = _edges_of(r, EdgeType.IMPORTS)
        assert any(e.target_fq_name == "stdio.h" for e in imp)

    def test_no_includes(self):
        r = _parse("int main() { return 0; }")
        assert r.using_directives == []


class TestModuleNamespace:
    def test_c_extension(self):
        r = _parse("int x;", "src/main.c")
        assert r.namespace == "src.main"

    def test_h_extension(self):
        r = _parse("int x;", "include/util.h")
        assert r.namespace == "include.util"


class TestStructDeclaration:
    def test_simple_struct(self):
        r = _parse("struct Foo {};")
        assert _sym(r, "test.Foo") is not None
        assert _sym(r, "test.Foo").kind == SymbolKind.STRUCT

    def test_struct_fields(self):
        r = _parse("struct P {\n    int x;\n    int y;\n};")
        assert _sym(r, "test.P.x") is not None
        assert _sym(r, "test.P.y") is not None

    def test_field_type(self):
        r = _parse("struct A {\n    int val;\n};")
        f = _sym(r, "test.A.val")
        assert f.kind == SymbolKind.FIELD
        assert f.return_type == "int"

    def test_containment(self):
        r = _parse("struct A {\n    int x;\n};")
        c = _edges_of(r, EdgeType.CONTAINS)
        assert any(e.source_fq_name == "test.A" for e in c)

    def test_empty_struct(self):
        r = _parse("struct Empty {};")
        assert _sym(r, "test.Empty") is not None


class TestEnumDeclaration:
    def test_simple_enum(self):
        r = _parse("enum Color { RED, GREEN, BLUE };")
        assert _sym(r, "test.Color") is not None
        assert _sym(r, "test.Color").kind == SymbolKind.ENUM


class TestTypedef:
    def test_typedef_struct(self):
        r = _parse("typedef struct { int x; int y; } Point;")
        s = _sym(r, "test.Point")
        assert s is not None
        assert s.kind == SymbolKind.STRUCT
        assert _sym(r, "test.Point.x") is not None

    def test_typedef_alias(self):
        r = _parse("typedef int MyInt;")
        assert _sym(r, "test.MyInt") is not None


class TestFunctionDeclaration:
    def test_simple_function(self):
        r = _parse("int add(int a, int b) { return a + b; }")
        s = _sym(r, "test.add")
        assert s is not None
        assert s.kind == SymbolKind.METHOD

    def test_params(self):
        r = _parse("int add(int a, int b) { return 0; }")
        s = _sym(r, "test.add")
        assert len(s.parameters) == 2

    def test_return_type(self):
        r = _parse("float calc() { return 1.0; }")
        assert _sym(r, "test.calc").return_type == "float"

    def test_void_return(self):
        r = _parse("void run() {}")
        assert _sym(r, "test.run").return_type == "void"

    def test_static_function(self):
        r = _parse("static int internal() { return 0; }")
        s = _sym(r, "test.internal")
        assert "static" in s.modifiers

    def test_calls(self):
        r = _parse("void run() { helper(); process(); }")
        targets = {e.target_fq_name for e in _edges_of(r, EdgeType.CALLS)}
        assert "helper" in targets
        assert "process" in targets

    def test_signature(self):
        r = _parse("int add(int a, int b) { return 0; }")
        assert "add" in _sym(r, "test.add").signature


class TestCallExtraction:
    def test_simple(self):
        r = _parse("void run() { doIt(); }")
        assert any(e.target_fq_name == "doIt" for e in _edges_of(r, EdgeType.CALLS))

    def test_multiple(self):
        r = _parse("void run() { a(); b(); c(); }")
        t = {e.target_fq_name for e in _edges_of(r, EdgeType.CALLS)}
        assert {"a", "b", "c"} <= t

    def test_member_call(self):
        r = _parse("void run() { obj->method(); }")
        assert any(e.target_fq_name == "method" for e in _edges_of(r, EdgeType.CALLS))

    def test_line_number(self):
        r = _parse("void run() {\n    int x = 1;\n    helper();\n}")
        calls = _edges_of(r, EdgeType.CALLS)
        assert calls[0].line == 3


class TestDocComments:
    def test_doc_comment(self):
        r = _parse("/** Adds two ints. */\nint add(int a, int b) { return 0; }")
        assert "Adds two" in _sym(r, "test.add").doc_comment

    def test_no_doc(self):
        r = _parse("int add(int a, int b) { return 0; }")
        assert _sym(r, "test.add").doc_comment == ""


class TestEdgeCases:
    def test_empty_file(self):
        r = _parse("")
        assert r.symbols == []

    def test_syntax_error(self):
        r = _parse("struct A { broken };")
        assert _sym(r, "test.A") is not None

    def test_file_path(self):
        r = _parse("struct A {};", "src/util.c")
        assert r.path == "src/util.c"

    def test_long_name(self):
        name = "A" * 200
        r = _parse(f"struct {name} {{}};")
        assert _sym(r, f"test.{name}") is not None


class TestCParserInterface:
    def test_language_id(self):
        assert CParser().language_id == "c"

    def test_parse_via_interface(self):
        p = CParser()
        r = p.parse_file(b"struct Foo {};", "foo.c")
        assert _sym(r, "foo.Foo") is not None


class TestRegistryIntegration:
    def test_c_registered(self):
        from app.analysis.parser_registry import supported_languages

        assert "c" in supported_languages()

    def test_get_parser(self):
        from app.analysis.parser_registry import get_parser

        assert get_parser("c") is not None


class TestPipelineIntegration:
    def test_analyze_c_files(self, tmp_path):
        from app.analysis.pipeline import analyze_snapshot_files

        (tmp_path / "main.c").write_text("struct Svc { int x; };\nvoid run() { helper(); }\n")
        records = [{"path": "main.c", "language": "c"}]
        graph = analyze_snapshot_files(tmp_path, records)
        assert "main.Svc" in graph.symbols
        assert "main.run" in graph.symbols
