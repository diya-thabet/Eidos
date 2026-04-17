"""
Comprehensive Java parser tests.

Tests: packages, imports, classes, interfaces, enums, records, annotations,
inheritance, implements, nested classes, constructors, methods, fields,
modifiers, parameters, return types, generics, Javadoc, call extraction,
object creation, static methods, abstract classes, multiple classes per file,
empty files, edge cases.
"""

from app.analysis.java_parser import JavaParser, parse_file
from app.analysis.models import EdgeType, SymbolKind


def _parse(code: str, path: str = "Test.java"):
    return parse_file(code.encode("utf-8"), path)


def _sym(analysis, fq):
    return next((s for s in analysis.symbols if s.fq_name == fq), None)


def _edges_of(analysis, edge_type):
    return [e for e in analysis.edges if e.edge_type == edge_type]


# ------------------------------------------------------------------
# Package & imports
# ------------------------------------------------------------------


class TestPackageDeclaration:
    def test_simple_package(self):
        r = _parse("package com.example; class A {}")
        assert r.namespace == "com.example"

    def test_nested_package(self):
        r = _parse("package com.example.app.service; class A {}")
        assert r.namespace == "com.example.app.service"

    def test_no_package(self):
        r = _parse("class A {}")
        assert r.namespace == ""

    def test_package_sets_fq_name(self):
        r = _parse("package org.foo; class Bar {}")
        assert _sym(r, "org.foo.Bar") is not None


class TestImports:
    def test_single_import(self):
        r = _parse("import java.util.List; class A {}")
        assert "java.util.List" in r.using_directives

    def test_multiple_imports(self):
        r = _parse(
            "import java.util.List;\nimport java.util.Map;\nimport java.io.File;\nclass A {}"
        )
        assert len(r.using_directives) == 3

    def test_import_edge_created(self):
        r = _parse("package p; import java.util.List; class A {}")
        imp_edges = _edges_of(r, EdgeType.IMPORTS)
        assert any(e.target_fq_name == "java.util.List" for e in imp_edges)

    def test_no_imports(self):
        r = _parse("class A {}")
        assert r.using_directives == []

    def test_static_import(self):
        r = _parse("import java.lang.Math; class A {}")
        assert len(r.using_directives) >= 1

    def test_wildcard_import(self):
        r = _parse("import java.util.*; class A {}")
        # tree-sitter may or may not parse wildcard; at minimum no crash
        assert isinstance(r.using_directives, list)


# ------------------------------------------------------------------
# Class declarations
# ------------------------------------------------------------------


class TestClassDeclaration:
    def test_simple_class(self):
        r = _parse("class Foo {}")
        s = _sym(r, "Foo")
        assert s is not None
        assert s.kind == SymbolKind.CLASS

    def test_public_class(self):
        r = _parse("public class Foo {}")
        s = _sym(r, "Foo")
        assert "public" in s.modifiers

    def test_abstract_class(self):
        r = _parse("public abstract class Foo {}")
        s = _sym(r, "Foo")
        assert "abstract" in s.modifiers

    def test_final_class(self):
        r = _parse("public final class Foo {}")
        s = _sym(r, "Foo")
        assert "final" in s.modifiers

    def test_class_with_package(self):
        r = _parse("package com.x; public class Foo {}")
        assert _sym(r, "com.x.Foo") is not None

    def test_class_line_numbers(self):
        r = _parse("package p;\n\npublic class Foo {\n}\n")
        s = _sym(r, "p.Foo")
        assert s.start_line == 3
        assert s.end_line == 4


class TestInheritance:
    def test_extends(self):
        r = _parse("class Dog extends Animal {}")
        s = _sym(r, "Dog")
        assert "Animal" in s.base_types
        inh = _edges_of(r, EdgeType.INHERITS)
        assert any(e.target_fq_name == "Animal" for e in inh)

    def test_implements_single(self):
        r = _parse("class Foo implements Runnable {}")
        s = _sym(r, "Foo")
        assert "Runnable" in s.base_types
        impl = _edges_of(r, EdgeType.IMPLEMENTS)
        assert any(e.target_fq_name == "Runnable" for e in impl)

    def test_implements_multiple(self):
        r = _parse("class Foo implements Serializable, Comparable {}")
        impl = _edges_of(r, EdgeType.IMPLEMENTS)
        targets = {e.target_fq_name for e in impl}
        assert "Serializable" in targets
        assert "Comparable" in targets

    def test_extends_and_implements(self):
        r = _parse("class Foo extends Bar implements Baz, Qux {}")
        s = _sym(r, "Foo")
        assert "Bar" in s.base_types
        assert "Baz" in s.base_types
        assert "Qux" in s.base_types

    def test_no_inheritance(self):
        r = _parse("class Foo {}")
        assert _sym(r, "Foo").base_types == []


# ------------------------------------------------------------------
# Interface declarations
# ------------------------------------------------------------------


class TestInterfaceDeclaration:
    def test_simple_interface(self):
        r = _parse("interface Foo {}")
        s = _sym(r, "Foo")
        assert s.kind == SymbolKind.INTERFACE

    def test_interface_with_methods(self):
        r = _parse("interface Repo { void save(String s); String find(int id); }")
        syms = [s for s in r.symbols if s.kind == SymbolKind.METHOD]
        assert len(syms) == 2

    def test_interface_extends(self):
        r = _parse("interface Foo extends Bar {}")
        # interfaces use "extends" not "implements"
        s = _sym(r, "Foo")
        assert s is not None


# ------------------------------------------------------------------
# Enum declarations
# ------------------------------------------------------------------


class TestEnumDeclaration:
    def test_simple_enum(self):
        r = _parse("enum Color { RED, GREEN, BLUE }")
        s = _sym(r, "Color")
        assert s is not None
        assert s.kind == SymbolKind.ENUM

    def test_enum_with_method(self):
        r = _parse(
            "enum Status {\n    ACTIVE, INACTIVE;\n    public String label() { return name(); }\n}"
        )
        assert _sym(r, "Status") is not None
        assert _sym(r, "Status.label") is not None

    def test_enum_with_constructor(self):
        r = _parse(
            "enum Planet {\n"
            "    EARTH(1.0);\n"
            "    private double mass;\n"
            "    Planet(double mass) { this.mass = mass; }\n"
            "}"
        )
        assert _sym(r, "Planet") is not None
        ctors = [s for s in r.symbols if s.kind == SymbolKind.CONSTRUCTOR]
        assert len(ctors) >= 1


# ------------------------------------------------------------------
# Methods
# ------------------------------------------------------------------


class TestMethodDeclaration:
    def test_simple_method(self):
        r = _parse("class A { void run() {} }")
        m = _sym(r, "A.run")
        assert m is not None
        assert m.kind == SymbolKind.METHOD

    def test_method_parameters(self):
        r = _parse("class A { void go(String name, int count) {} }")
        m = _sym(r, "A.go")
        assert len(m.parameters) == 2
        assert any("String" in p for p in m.parameters)
        assert any("int" in p for p in m.parameters)

    def test_return_type(self):
        r = _parse("class A { String getName() { return null; } }")
        m = _sym(r, "A.getName")
        assert m.return_type == "String"

    def test_void_return_type(self):
        r = _parse("class A { void doIt() {} }")
        m = _sym(r, "A.doIt")
        assert m.return_type == "void"

    def test_static_method(self):
        r = _parse("class A { public static void main(String[] args) {} }")
        m = _sym(r, "A.main")
        assert "static" in m.modifiers
        assert "public" in m.modifiers

    def test_multiple_methods(self):
        r = _parse("class A { void a() {} void b() {} void c() {} }")
        methods = [s for s in r.symbols if s.kind == SymbolKind.METHOD]
        assert len(methods) == 3

    def test_method_signature(self):
        r = _parse("class A { public void run(String s) {} }")
        m = _sym(r, "A.run")
        assert "run" in m.signature
        assert "String" in m.signature

    def test_containment_edge(self):
        r = _parse("class A { void m() {} }")
        contains = _edges_of(r, EdgeType.CONTAINS)
        assert any(e.source_fq_name == "A" and e.target_fq_name == "A.m" for e in contains)


# ------------------------------------------------------------------
# Constructors
# ------------------------------------------------------------------


class TestConstructorDeclaration:
    def test_simple_constructor(self):
        r = _parse("class Foo { Foo() {} }")
        c = _sym(r, "Foo.Foo")
        assert c is not None
        assert c.kind == SymbolKind.CONSTRUCTOR

    def test_constructor_with_params(self):
        r = _parse("class Foo { Foo(int x, String y) {} }")
        c = _sym(r, "Foo.Foo")
        assert len(c.parameters) == 2

    def test_constructor_calls(self):
        r = _parse("class Foo { Foo() { init(); new Bar(); } }")
        calls = _edges_of(r, EdgeType.CALLS)
        targets = {e.target_fq_name for e in calls}
        assert "init" in targets
        assert "Bar" in targets


# ------------------------------------------------------------------
# Fields
# ------------------------------------------------------------------


class TestFieldDeclaration:
    def test_simple_field(self):
        r = _parse("class A { private int count; }")
        f = _sym(r, "A.count")
        assert f is not None
        assert f.kind == SymbolKind.FIELD

    def test_field_modifiers(self):
        r = _parse("class A { private static final int MAX = 100; }")
        f = _sym(r, "A.MAX")
        assert "private" in f.modifiers
        assert "static" in f.modifiers
        assert "final" in f.modifiers

    def test_multiple_fields(self):
        r = _parse("class A { int x; int y; int z; }")
        fields = [s for s in r.symbols if s.kind == SymbolKind.FIELD]
        assert len(fields) == 3


# ------------------------------------------------------------------
# Call extraction
# ------------------------------------------------------------------


class TestCallExtraction:
    def test_method_call(self):
        r = _parse("class A { void go() { doSomething(); } }")
        calls = _edges_of(r, EdgeType.CALLS)
        assert any(e.target_fq_name == "doSomething" for e in calls)

    def test_chained_call(self):
        r = _parse("class A { void go() { foo(); bar(); } }")
        calls = _edges_of(r, EdgeType.CALLS)
        targets = {e.target_fq_name for e in calls}
        assert "foo" in targets
        assert "bar" in targets

    def test_object_creation(self):
        r = _parse("class A { void go() { new ArrayList(); } }")
        calls = _edges_of(r, EdgeType.CALLS)
        assert any(e.target_fq_name == "ArrayList" for e in calls)

    def test_call_line_number(self):
        r = _parse("class A {\n  void go() {\n    foo();\n  }\n}")
        calls = _edges_of(r, EdgeType.CALLS)
        assert len(calls) >= 1
        assert calls[0].line == 3

    def test_nested_calls(self):
        r = _parse("class A { void go() { outer(inner()); } }")
        calls = _edges_of(r, EdgeType.CALLS)
        targets = {e.target_fq_name for e in calls}
        assert "outer" in targets
        assert "inner" in targets


# ------------------------------------------------------------------
# Nested classes
# ------------------------------------------------------------------


class TestNestedClasses:
    def test_inner_class(self):
        r = _parse("class Outer { class Inner {} }")
        assert _sym(r, "Outer") is not None
        assert _sym(r, "Outer.Inner") is not None

    def test_inner_class_containment(self):
        r = _parse("class Outer { class Inner {} }")
        contains = _edges_of(r, EdgeType.CONTAINS)
        assert any(
            e.source_fq_name == "Outer" and e.target_fq_name == "Outer.Inner" for e in contains
        )

    def test_deep_nesting(self):
        r = _parse("class A { class B { class C {} } }")
        assert _sym(r, "A") is not None
        assert _sym(r, "A.B") is not None
        assert _sym(r, "A.B.C") is not None

    def test_static_inner_class(self):
        r = _parse("class Outer { static class Helper {} }")
        h = _sym(r, "Outer.Helper")
        assert h is not None
        assert "static" in h.modifiers


# ------------------------------------------------------------------
# Javadoc
# ------------------------------------------------------------------


class TestJavadoc:
    def test_javadoc_on_class(self):
        r = _parse("/** This is Foo. */\nclass Foo {}")
        s = _sym(r, "Foo")
        assert "This is Foo" in s.doc_comment

    def test_javadoc_on_method(self):
        r = _parse("class A {\n    /** Does stuff. */\n    void doStuff() {}\n}")
        m = _sym(r, "A.doStuff")
        assert "Does stuff" in m.doc_comment

    def test_no_javadoc(self):
        r = _parse("class A { void go() {} }")
        m = _sym(r, "A.go")
        assert m.doc_comment == ""

    def test_regular_comment_ignored(self):
        r = _parse("// not javadoc\nclass A {}")
        s = _sym(r, "A")
        assert s.doc_comment == ""


# ------------------------------------------------------------------
# Generics
# ------------------------------------------------------------------


class TestGenerics:
    def test_generic_class(self):
        r = _parse("class Box<T> {}")
        s = _sym(r, "Box")
        assert s is not None

    def test_generic_extends(self):
        r = _parse("class NumBox<T extends Number> extends Box<T> {}")
        s = _sym(r, "NumBox")
        assert len(s.base_types) >= 1

    def test_generic_method_param(self):
        r = _parse("class A { void process(List<String> items) {} }")
        m = _sym(r, "A.process")
        assert len(m.parameters) == 1
        assert "List" in m.parameters[0]

    def test_generic_return_type(self):
        r = _parse("class A { List<String> getItems() { return null; } }")
        m = _sym(r, "A.getItems")
        assert "List" in m.return_type


# ------------------------------------------------------------------
# Multiple classes in one file
# ------------------------------------------------------------------


class TestMultipleClasses:
    def test_two_classes(self):
        r = _parse("class A { void a() {} }\nclass B { void b() {} }\n")
        assert _sym(r, "A") is not None
        assert _sym(r, "B") is not None
        assert _sym(r, "A.a") is not None
        assert _sym(r, "B.b") is not None

    def test_interface_and_class(self):
        r = _parse(
            "interface Repo { void save(); }\n"
            "class SqlRepo implements Repo { public void save() {} }\n"
        )
        assert _sym(r, "Repo") is not None
        assert _sym(r, "SqlRepo") is not None
        impl = _edges_of(r, EdgeType.IMPLEMENTS)
        assert any(e.target_fq_name == "Repo" for e in impl)


# ------------------------------------------------------------------
# Edge cases
# ------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_file(self):
        r = _parse("")
        assert r.symbols == []
        assert r.namespace == ""

    def test_only_package(self):
        r = _parse("package com.example;")
        assert r.namespace == "com.example"
        assert r.symbols == []

    def test_comment_only(self):
        r = _parse("// just a comment\n/* block */")
        assert r.symbols == []

    def test_empty_class(self):
        r = _parse("class Empty {}")
        assert _sym(r, "Empty") is not None
        assert len(r.symbols) == 1

    def test_very_long_class_name(self):
        name = "A" * 200
        r = _parse(f"class {name} {{}}")
        assert _sym(r, name) is not None

    def test_unicode_in_string(self):
        r = _parse('class A { String s = "unicode chars"; }')
        assert _sym(r, "A") is not None

    def test_syntax_error_partial_parse(self):
        # tree-sitter is error-tolerant and should parse what it can
        r = _parse("class A { void broken( {} }")
        assert _sym(r, "A") is not None

    def test_file_path_preserved(self):
        r = _parse("class A {}", "src/main/java/A.java")
        assert r.path == "src/main/java/A.java"
        assert r.symbols[0].file_path == "src/main/java/A.java"


# ------------------------------------------------------------------
# Parser class interface
# ------------------------------------------------------------------


class TestJavaParserInterface:
    def test_language_id(self):
        p = JavaParser()
        assert p.language_id == "java"

    def test_parse_via_interface(self):
        p = JavaParser()
        r = p.parse_file(b"class Foo {}", "Foo.java")
        assert _sym(r, "Foo") is not None

    def test_parse_complex_via_interface(self):
        p = JavaParser()
        code = (
            b"package com.x;\n"
            b"import java.util.List;\n"
            b"public class Svc extends Base implements Iface {\n"
            b"    private List<String> items;\n"
            b"    public Svc(List<String> items) { this.items = items; }\n"
            b"    public void run() { process(); new Helper(); }\n"
            b"}\n"
        )
        r = p.parse_file(code, "Svc.java")
        assert r.namespace == "com.x"
        assert _sym(r, "com.x.Svc") is not None
        assert _sym(r, "com.x.Svc.run") is not None
        assert _sym(r, "com.x.Svc.items") is not None
        assert _sym(r, "com.x.Svc.Svc") is not None
        inh = _edges_of(r, EdgeType.INHERITS)
        assert any(e.target_fq_name == "Base" for e in inh)
        impl = _edges_of(r, EdgeType.IMPLEMENTS)
        assert any(e.target_fq_name == "Iface" for e in impl)
        calls = _edges_of(r, EdgeType.CALLS)
        targets = {e.target_fq_name for e in calls}
        assert "process" in targets
        assert "Helper" in targets


# ------------------------------------------------------------------
# Registry integration
# ------------------------------------------------------------------


class TestParserRegistry:
    def test_java_registered(self):
        from app.analysis.parser_registry import get_parser, supported_languages

        assert "java" in supported_languages()
        assert get_parser("java") is not None

    def test_csharp_still_registered(self):
        from app.analysis.parser_registry import get_parser, supported_languages

        assert "csharp" in supported_languages()
        assert get_parser("csharp") is not None

    def test_unknown_returns_none(self):
        from app.analysis.parser_registry import get_parser

        assert get_parser("cobol") is None

    def test_java_parser_matches(self):
        from app.analysis.parser_registry import get_parser

        p = get_parser("java")
        assert p is not None
        assert p.language_id == "java"


# ------------------------------------------------------------------
# Pipeline integration
# ------------------------------------------------------------------


class TestPipelineIntegration:
    def test_analyze_java_files(self, tmp_path):
        from app.analysis.pipeline import analyze_snapshot_files

        java_file = tmp_path / "Foo.java"
        java_file.write_text(
            "package com.test;\npublic class Foo {\n    public void bar() { baz(); }\n}\n"
        )
        records = [{"path": "Foo.java", "language": "java"}]
        graph = analyze_snapshot_files(tmp_path, records)
        assert "com.test.Foo" in graph.symbols
        assert "com.test.Foo.bar" in graph.symbols

    def test_mixed_java_csharp(self, tmp_path):
        from app.analysis.pipeline import analyze_snapshot_files

        java_file = tmp_path / "Foo.java"
        java_file.write_text("class JavaFoo { void go() {} }")

        cs_file = tmp_path / "Bar.cs"
        cs_file.write_text("class CSharpBar { void Run() {} }")

        records = [
            {"path": "Foo.java", "language": "java"},
            {"path": "Bar.cs", "language": "csharp"},
        ]
        graph = analyze_snapshot_files(tmp_path, records)
        assert "JavaFoo" in graph.symbols
        assert "CSharpBar" in graph.symbols

    def test_unsupported_language_skipped(self, tmp_path):
        from app.analysis.pipeline import analyze_snapshot_files

        f = tmp_path / "script.py"
        f.write_text("print('hello')")
        records = [{"path": "script.py", "language": "python"}]
        graph = analyze_snapshot_files(tmp_path, records)
        assert len(graph.symbols) == 0

    def test_missing_file_skipped(self, tmp_path):
        from app.analysis.pipeline import analyze_snapshot_files

        records = [{"path": "Ghost.java", "language": "java"}]
        graph = analyze_snapshot_files(tmp_path, records)
        assert len(graph.symbols) == 0
