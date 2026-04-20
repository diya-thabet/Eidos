"""
Comprehensive C++ parser tests.

Tests: includes, namespaces, classes, structs, enums, inheritance,
constructors, destructors, methods, fields, templates, free functions,
call extraction, new expressions, doc comments, edge cases, registry,
pipeline.
"""

from app.analysis.cpp_parser import CppParser, parse_file
from app.analysis.models import EdgeType, SymbolKind


def _parse(code: str, path: str = "test.cpp"):
    return parse_file(code.encode("utf-8"), path)


def _sym(a, fq):
    return next((s for s in a.symbols if s.fq_name == fq), None)


def _edges_of(a, t):
    return [e for e in a.edges if e.edge_type == t]


class TestIncludes:
    def test_system_include(self):
        r = _parse("#include <iostream>\n")
        assert "iostream" in r.using_directives

    def test_local_include(self):
        r = _parse('#include "app.h"\n')
        assert "app.h" in r.using_directives

    def test_multiple(self):
        r = _parse('#include <iostream>\n#include <string>\n#include "app.h"\n')
        assert len(r.using_directives) == 3

    def test_import_edge(self):
        r = _parse("#include <vector>\n", "main.cpp")
        assert any(e.target_fq_name == "vector" for e in _edges_of(r, EdgeType.IMPORTS))


class TestModuleNamespace:
    def test_cpp_extension(self):
        r = _parse("int x;", "src/main.cpp")
        assert r.namespace == "src.main"

    def test_hpp_extension(self):
        r = _parse("int x;", "include/util.hpp")
        assert r.namespace == "include.util"

    def test_h_extension(self):
        r = _parse("int x;", "util.h")
        assert r.namespace == "util"


class TestNamespace:
    def test_simple_namespace(self):
        r = _parse("namespace myns {\nclass Foo {};\n}")
        ns = _sym(r, "test.myns")
        assert ns is not None
        assert ns.kind == SymbolKind.NAMESPACE

    def test_class_in_namespace(self):
        r = _parse("namespace ns {\nclass A {};\n}")
        assert _sym(r, "test.ns.A") is not None

    def test_function_in_namespace(self):
        r = _parse("namespace ns {\nvoid run() {}\n}")
        assert _sym(r, "test.ns.run") is not None


class TestClassDeclaration:
    def test_simple_class(self):
        r = _parse("class Foo {};")
        s = _sym(r, "test.Foo")
        assert s is not None
        assert s.kind == SymbolKind.CLASS

    def test_struct(self):
        r = _parse("struct Point { int x; int y; };")
        s = _sym(r, "test.Point")
        assert s is not None
        assert s.kind == SymbolKind.STRUCT

    def test_inheritance(self):
        r = _parse("class Dog : public Animal {};")
        s = _sym(r, "test.Dog")
        assert "Animal" in s.base_types
        inh = _edges_of(r, EdgeType.INHERITS)
        assert any(e.target_fq_name == "Animal" for e in inh)

    def test_multiple_bases(self):
        r = _parse("class A : public B, public C {};")
        s = _sym(r, "test.A")
        assert "B" in s.base_types
        assert "C" in s.base_types

    def test_no_bases(self):
        r = _parse("class A {};")
        assert _sym(r, "test.A").base_types == []


class TestConstructor:
    def test_constructor(self):
        r = _parse("class Foo {\npublic:\n    Foo(int x) {}\n};")
        c = _sym(r, "test.Foo.Foo")
        assert c is not None
        assert c.kind == SymbolKind.CONSTRUCTOR

    def test_destructor(self):
        r = _parse("class Foo {\npublic:\n    ~Foo() {}\n};")
        d = _sym(r, "test.Foo.~Foo")
        assert d is not None


class TestMethodDeclaration:
    def test_simple_method(self):
        r = _parse("class A {\npublic:\n    void run() {}\n};")
        m = _sym(r, "test.A.run")
        assert m is not None
        assert m.kind == SymbolKind.METHOD

    def test_method_return(self):
        r = _parse("class A {\n    int get() { return 0; }\n};")
        assert _sym(r, "test.A.get").return_type == "int"

    def test_method_params(self):
        r = _parse("class A {\n    void set(int a, int b) {}\n};")
        m = _sym(r, "test.A.set")
        assert len(m.parameters) == 2

    def test_containment(self):
        r = _parse("class A {\n    void run() {}\n};")
        c = _edges_of(r, EdgeType.CONTAINS)
        assert any(e.source_fq_name == "test.A" and e.target_fq_name == "test.A.run" for e in c)

    def test_method_calls(self):
        r = _parse("class A {\n    void run() { helper(); }\n};")
        calls = _edges_of(r, EdgeType.CALLS)
        assert any(e.target_fq_name == "helper" for e in calls)

    def test_pure_virtual(self):
        r = _parse("class A {\npublic:\n    virtual void speak() = 0;\n};")
        m = _sym(r, "test.A.speak")
        assert m is not None

    def test_multiple_methods(self):
        r = _parse("class A {\n    void a() {}\n    void b() {}\n    void c() {}\n};")
        methods = [s for s in r.symbols if s.parent_fq_name == "test.A"]
        assert len(methods) == 3


class TestFieldDeclaration:
    def test_simple_field(self):
        r = _parse("class A {\n    int x;\n};")
        f = _sym(r, "test.A.x")
        assert f is not None
        assert f.kind == SymbolKind.FIELD

    def test_field_type(self):
        r = _parse("class A {\n    float val;\n};")
        assert _sym(r, "test.A.val").return_type == "float"

    def test_field_containment(self):
        r = _parse("class A {\n    int x;\n};")
        c = _edges_of(r, EdgeType.CONTAINS)
        assert any(e.target_fq_name == "test.A.x" for e in c)


class TestEnum:
    def test_enum(self):
        r = _parse("enum Color { Red, Green };")
        assert _sym(r, "test.Color") is not None
        assert _sym(r, "test.Color").kind == SymbolKind.ENUM

    def test_enum_class(self):
        r = _parse("enum class Status { Active, Inactive };")
        assert _sym(r, "test.Status") is not None


class TestCallExtraction:
    def test_simple(self):
        r = _parse("void run() { helper(); }")
        assert any(e.target_fq_name == "helper" for e in _edges_of(r, EdgeType.CALLS))

    def test_member_call(self):
        r = _parse("void run() { obj.method(); }")
        assert any(e.target_fq_name == "method" for e in _edges_of(r, EdgeType.CALLS))

    def test_arrow_call(self):
        r = _parse("void run() { ptr->method(); }")
        assert any(e.target_fq_name == "method" for e in _edges_of(r, EdgeType.CALLS))

    def test_scoped_call(self):
        r = _parse("void run() { ns::func(); }")
        assert any(e.target_fq_name == "func" for e in _edges_of(r, EdgeType.CALLS))

    def test_new_expression(self):
        r = _parse("void run() { new Foo(); }")
        assert any(e.target_fq_name == "Foo" for e in _edges_of(r, EdgeType.CALLS))

    def test_multiple(self):
        r = _parse("void run() { a(); b(); c(); }")
        t = {e.target_fq_name for e in _edges_of(r, EdgeType.CALLS)}
        assert {"a", "b", "c"} <= t


class TestFreeFunctions:
    def test_free_function(self):
        r = _parse("int add(int a, int b) { return a + b; }")
        s = _sym(r, "test.add")
        assert s is not None
        assert s.kind == SymbolKind.METHOD

    def test_function_in_namespace(self):
        r = _parse("namespace ns {\nvoid helper() { process(); }\n}")
        s = _sym(r, "test.ns.helper")
        assert s is not None
        calls = _edges_of(r, EdgeType.CALLS)
        assert any(e.target_fq_name == "process" for e in calls)


class TestDocComments:
    def test_class_doc(self):
        r = _parse("/** My class. */\nclass Foo {};")
        assert "My class" in _sym(r, "test.Foo").doc_comment

    def test_no_doc(self):
        r = _parse("class Foo {};")
        assert _sym(r, "test.Foo").doc_comment == ""


class TestFullFile:
    def test_complete(self):
        r = _parse(
            "#include <string>\n"
            "namespace app {\n"
            "class Svc : public Base {\n"
            "    int count_;\n"
            "public:\n"
            "    Svc(int n) : count_(n) {}\n"
            "    void run() { helper(); }\n"
            "};\n"
            "enum Status { OK, ERR };\n"
            "void freeFunc() {}\n"
            "}\n"
        )
        assert "string" in r.using_directives
        assert _sym(r, "test.app") is not None
        assert _sym(r, "test.app.Svc") is not None
        assert "Base" in _sym(r, "test.app.Svc").base_types
        assert _sym(r, "test.app.Svc.count_") is not None
        assert _sym(r, "test.app.Svc.Svc") is not None
        assert _sym(r, "test.app.Svc.Svc").kind == SymbolKind.CONSTRUCTOR
        assert _sym(r, "test.app.Svc.run") is not None
        assert _sym(r, "test.app.Status") is not None
        assert _sym(r, "test.app.freeFunc") is not None


class TestEdgeCases:
    def test_empty(self):
        r = _parse("")
        assert r.symbols == []

    def test_syntax_error(self):
        r = _parse("class A { broken };")
        assert _sym(r, "test.A") is not None

    def test_file_path(self):
        r = _parse("class A {};", "src/util.cpp")
        assert r.path == "src/util.cpp"

    def test_long_name(self):
        n = "X" * 200
        r = _parse(f"class {n} {{}};")
        assert _sym(r, f"test.{n}") is not None


class TestCppParserInterface:
    def test_language_id(self):
        assert CppParser().language_id == "cpp"

    def test_parse_via_interface(self):
        p = CppParser()
        r = p.parse_file(b"class Foo {};", "foo.cpp")
        assert _sym(r, "foo.Foo") is not None


class TestRegistryIntegration:
    def test_cpp_registered(self):
        from app.analysis.parser_registry import supported_languages

        assert "cpp" in supported_languages()

    def test_all_parsers(self):
        from app.analysis.parser_registry import supported_languages

        langs = supported_languages()
        expected = {
            "csharp",
            "java",
            "python",
            "typescript",
            "tsx",
            "go",
            "rust",
            "c",
            "cpp",
        }
        assert expected <= langs


class TestPipelineIntegration:
    def test_analyze_cpp_files(self, tmp_path):
        from app.analysis.pipeline import analyze_snapshot_files

        (tmp_path / "main.cpp").write_text(
            "class Svc {\npublic:\n    void run() { helper(); }\n};\n"
        )
        records = [{"path": "main.cpp", "language": "cpp"}]
        graph = analyze_snapshot_files(tmp_path, records)
        assert "main.Svc" in graph.symbols
        assert "main.Svc.run" in graph.symbols

    def test_mixed_all_languages(self, tmp_path):
        from app.analysis.pipeline import analyze_snapshot_files

        (tmp_path / "a.cs").write_text("class CsA { void Run() {} }")
        (tmp_path / "b.java").write_text("class JavaB { void go() {} }")
        (tmp_path / "c.py").write_text("class PyC:\n    def do(self):\n        pass\n")
        (tmp_path / "d.ts").write_text("export class TsD { run() {} }")
        (tmp_path / "e.go").write_text("package main\ntype GoE struct{}\nfunc (g *GoE) Run() {}")
        (tmp_path / "f.rs").write_text("struct RsF {}\nimpl RsF { fn run(&self) {} }")
        (tmp_path / "g.c").write_text("void c_func() {}")
        (tmp_path / "h.cpp").write_text("class CppH {};\n")

        records = [
            {"path": "a.cs", "language": "csharp"},
            {"path": "b.java", "language": "java"},
            {"path": "c.py", "language": "python"},
            {"path": "d.ts", "language": "typescript"},
            {"path": "e.go", "language": "go"},
            {"path": "f.rs", "language": "rust"},
            {"path": "g.c", "language": "c"},
            {"path": "h.cpp", "language": "cpp"},
        ]
        graph = analyze_snapshot_files(tmp_path, records)
        assert "CsA" in graph.symbols
        assert "JavaB" in graph.symbols
        assert "c.PyC" in graph.symbols
        assert "d.TsD" in graph.symbols
        assert "main.GoE" in graph.symbols
        assert "f.RsF" in graph.symbols
        assert "g.c_func" in graph.symbols
        assert "h.CppH" in graph.symbols
