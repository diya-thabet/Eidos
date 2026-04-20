"""
Comprehensive Rust parser tests.

Tests: use declarations, structs, traits, enums, functions, impl methods,
fields, constructors (fn new), trait impl edges, call extraction, doc
comments, type aliases, modules, visibility, edge cases, registry, pipeline.
"""

from app.analysis.models import EdgeType, SymbolKind
from app.analysis.rust_parser import RustParser, parse_file


def _parse(code: str, path: str = "test.rs"):
    return parse_file(code.encode("utf-8"), path)


def _sym(analysis, fq):
    return next((s for s in analysis.symbols if s.fq_name == fq), None)


def _edges_of(analysis, edge_type):
    return [e for e in analysis.edges if e.edge_type == edge_type]


# ------------------------------------------------------------------
# Use declarations
# ------------------------------------------------------------------


class TestUseDeclarations:
    def test_simple_use(self):
        r = _parse("use std::fmt;")
        assert "std::fmt" in r.using_directives

    def test_nested_use(self):
        r = _parse("use std::collections::HashMap;")
        assert "std::collections::HashMap" in r.using_directives

    def test_multiple_uses(self):
        r = _parse("use std::fmt;\nuse std::io;\nuse std::fs;")
        assert len(r.using_directives) == 3

    def test_import_edge(self):
        r = _parse("use std::fmt;", "lib.rs")
        imp = _edges_of(r, EdgeType.IMPORTS)
        assert any(e.target_fq_name == "std::fmt" for e in imp)

    def test_no_uses(self):
        r = _parse("fn main() {}")
        assert r.using_directives == []


# ------------------------------------------------------------------
# Module namespace
# ------------------------------------------------------------------


class TestModuleNamespace:
    def test_rs_path(self):
        r = _parse("struct A {}", "src/models/user.rs")
        assert r.namespace == "src.models.user"

    def test_lib_rs(self):
        r = _parse("struct A {}", "lib.rs")
        assert r.namespace == "lib"


# ------------------------------------------------------------------
# Struct declarations
# ------------------------------------------------------------------


class TestStructDeclaration:
    def test_simple_struct(self):
        r = _parse("struct Foo {}")
        s = _sym(r, "test.Foo")
        assert s is not None
        assert s.kind == SymbolKind.STRUCT

    def test_pub_struct(self):
        r = _parse("pub struct Foo {}")
        s = _sym(r, "test.Foo")
        assert "pub" in s.modifiers

    def test_struct_with_fields(self):
        r = _parse("struct User {\n    name: String,\n    age: u32,\n}")
        assert _sym(r, "test.User") is not None
        assert _sym(r, "test.User.name") is not None
        assert _sym(r, "test.User.age") is not None

    def test_field_type(self):
        r = _parse("struct Cfg {\n    port: u16,\n}")
        f = _sym(r, "test.Cfg.port")
        assert f.kind == SymbolKind.FIELD
        assert f.return_type == "u16"

    def test_pub_field(self):
        r = _parse("pub struct A {\n    pub x: i32,\n}")
        f = _sym(r, "test.A.x")
        assert "pub" in f.modifiers

    def test_field_containment(self):
        r = _parse("struct A {\n    x: i32,\n}")
        contains = _edges_of(r, EdgeType.CONTAINS)
        assert any(
            e.source_fq_name == "test.A" and e.target_fq_name == "test.A.x" for e in contains
        )

    def test_line_numbers(self):
        r = _parse("// comment\nstruct Foo {\n    x: i32,\n}\n")
        s = _sym(r, "test.Foo")
        assert s.start_line == 2
        assert s.end_line == 4

    def test_empty_struct(self):
        r = _parse("struct Empty {}")
        assert _sym(r, "test.Empty") is not None


# ------------------------------------------------------------------
# Trait declarations
# ------------------------------------------------------------------


class TestTraitDeclaration:
    def test_simple_trait(self):
        r = _parse("trait Repo {}")
        s = _sym(r, "test.Repo")
        assert s is not None
        assert s.kind == SymbolKind.INTERFACE

    def test_pub_trait(self):
        r = _parse("pub trait Repo {}")
        assert "pub" in _sym(r, "test.Repo").modifiers

    def test_trait_with_methods(self):
        r = _parse(
            "trait Repo {\n"
            "    fn find(&self, id: &str) -> Option<i32>;\n"
            "    fn save(&self, val: i32);\n"
            "}"
        )
        assert _sym(r, "test.Repo") is not None
        assert _sym(r, "test.Repo.find") is not None
        assert _sym(r, "test.Repo.save") is not None

    def test_trait_method_containment(self):
        r = _parse("trait Svc {\n    fn run(&self);\n}")
        contains = _edges_of(r, EdgeType.CONTAINS)
        assert any(
            e.source_fq_name == "test.Svc" and e.target_fq_name == "test.Svc.run" for e in contains
        )

    def test_trait_method_params(self):
        r = _parse("trait R {\n    fn get(&self, id: &str) -> i32;\n}")
        m = _sym(r, "test.R.get")
        assert len(m.parameters) >= 1

    def test_trait_method_return(self):
        r = _parse("trait R {\n    fn get(&self) -> String;\n}")
        m = _sym(r, "test.R.get")
        assert "String" in m.return_type


# ------------------------------------------------------------------
# Enum declarations
# ------------------------------------------------------------------


class TestEnumDeclaration:
    def test_simple_enum(self):
        r = _parse("enum Status { Active, Inactive }")
        s = _sym(r, "test.Status")
        assert s is not None
        assert s.kind == SymbolKind.ENUM

    def test_pub_enum(self):
        r = _parse("pub enum Color { Red, Green, Blue }")
        assert "pub" in _sym(r, "test.Color").modifiers


# ------------------------------------------------------------------
# Impl blocks
# ------------------------------------------------------------------


class TestImplBlock:
    def test_inherent_impl(self):
        r = _parse("struct User {}\nimpl User {\n    fn greet(&self) {}\n}")
        m = _sym(r, "test.User.greet")
        assert m is not None
        assert m.parent_fq_name == "test.User"

    def test_impl_constructor(self):
        r = _parse("struct User {}\nimpl User {\n    fn new() -> Self { User {} }\n}")
        c = _sym(r, "test.User.new")
        assert c is not None
        assert c.kind == SymbolKind.CONSTRUCTOR

    def test_impl_containment(self):
        r = _parse("struct A {}\nimpl A {\n    fn run(&self) {}\n}")
        contains = _edges_of(r, EdgeType.CONTAINS)
        assert any(
            e.source_fq_name == "test.A" and e.target_fq_name == "test.A.run" for e in contains
        )

    def test_trait_impl(self):
        r = _parse(
            "struct SqlRepo {}\n"
            "trait Repo { fn find(&self); }\n"
            "impl Repo for SqlRepo {\n"
            "    fn find(&self) {}\n"
            "}"
        )
        impl = _edges_of(r, EdgeType.IMPLEMENTS)
        assert any(e.source_fq_name == "test.SqlRepo" and e.target_fq_name == "Repo" for e in impl)

    def test_impl_calls(self):
        r = _parse("struct A {}\nimpl A {\n    fn run(&self) { helper(); other(); }\n}")
        targets = {e.target_fq_name for e in _edges_of(r, EdgeType.CALLS)}
        assert "helper" in targets
        assert "other" in targets

    def test_multiple_methods_in_impl(self):
        r = _parse(
            "struct A {}\nimpl A {\n    fn a(&self) {}\n    fn b(&self) {}\n    fn c(&self) {}\n}"
        )
        methods = [s for s in r.symbols if s.parent_fq_name == "test.A"]
        assert len(methods) == 3


# ------------------------------------------------------------------
# Functions (top-level)
# ------------------------------------------------------------------


class TestFunctionDeclaration:
    def test_simple_function(self):
        r = _parse("fn run() {}")
        s = _sym(r, "test.run")
        assert s is not None
        assert s.kind == SymbolKind.METHOD

    def test_pub_function(self):
        r = _parse("pub fn run() {}")
        assert "pub" in _sym(r, "test.run").modifiers

    def test_function_params(self):
        r = _parse("fn add(a: i32, b: i32) -> i32 { a + b }")
        s = _sym(r, "test.add")
        assert len(s.parameters) == 2

    def test_function_return(self):
        r = _parse("fn get() -> String { String::new() }")
        s = _sym(r, "test.get")
        assert "String" in s.return_type

    def test_function_calls(self):
        r = _parse("fn run() { helper(); process(); }")
        targets = {e.target_fq_name for e in _edges_of(r, EdgeType.CALLS)}
        assert "helper" in targets
        assert "process" in targets

    def test_function_signature(self):
        r = _parse("fn run(x: i32) -> String { String::new() }")
        s = _sym(r, "test.run")
        assert "run" in s.signature
        assert "i32" in s.signature


# ------------------------------------------------------------------
# Call extraction
# ------------------------------------------------------------------


class TestCallExtraction:
    def test_simple_call(self):
        r = _parse("fn run() { doStuff(); }")
        calls = _edges_of(r, EdgeType.CALLS)
        assert any(e.target_fq_name == "doStuff" for e in calls)

    def test_method_call(self):
        r = _parse("fn run() { self.method(); }")
        calls = _edges_of(r, EdgeType.CALLS)
        assert any(e.target_fq_name == "method" for e in calls)

    def test_scoped_call(self):
        r = _parse("fn run() { User::new(); }")
        calls = _edges_of(r, EdgeType.CALLS)
        assert any(e.target_fq_name == "new" for e in calls)

    def test_multiple_calls(self):
        r = _parse("fn run() { a(); b(); c(); }")
        targets = {e.target_fq_name for e in _edges_of(r, EdgeType.CALLS)}
        assert {"a", "b", "c"} <= targets

    def test_nested_calls(self):
        r = _parse("fn run() { outer(inner()); }")
        targets = {e.target_fq_name for e in _edges_of(r, EdgeType.CALLS)}
        assert "outer" in targets
        assert "inner" in targets

    def test_call_line_number(self):
        r = _parse("fn run() {\n    let x = 1;\n    helper();\n}")
        calls = _edges_of(r, EdgeType.CALLS)
        assert calls[0].line == 3


# ------------------------------------------------------------------
# Doc comments
# ------------------------------------------------------------------


class TestDocComments:
    def test_struct_doc(self):
        r = _parse("/// A user.\nstruct User {}")
        s = _sym(r, "test.User")
        assert "A user" in s.doc_comment

    def test_function_doc(self):
        r = _parse("/// Runs it.\nfn run() {}")
        s = _sym(r, "test.run")
        assert "Runs it" in s.doc_comment

    def test_no_doc(self):
        r = _parse("fn run() {}")
        assert _sym(r, "test.run").doc_comment == ""

    def test_regular_comment_ignored(self):
        r = _parse("// not doc\nfn run() {}")
        assert _sym(r, "test.run").doc_comment == ""


# ------------------------------------------------------------------
# Type alias
# ------------------------------------------------------------------


class TestTypeAlias:
    def test_simple_alias(self):
        r = _parse("type UserId = String;")
        s = _sym(r, "test.UserId")
        assert s is not None

    def test_numeric_alias(self):
        r = _parse("type Count = u64;")
        assert _sym(r, "test.Count") is not None


# ------------------------------------------------------------------
# Modules
# ------------------------------------------------------------------


class TestModules:
    def test_inline_mod(self):
        r = _parse("mod inner {\n    pub struct Foo {}\n}")
        assert _sym(r, "test.inner") is not None
        assert _sym(r, "test.inner").kind == SymbolKind.NAMESPACE
        assert _sym(r, "test.inner.Foo") is not None

    def test_empty_mod(self):
        r = _parse("mod empty {}")
        assert _sym(r, "test.empty") is not None


# ------------------------------------------------------------------
# Multiple declarations
# ------------------------------------------------------------------


class TestMultipleDeclarations:
    def test_full_file(self):
        r = _parse(
            "use std::fmt;\n"
            "pub struct User { name: String }\n"
            "pub trait Repo { fn find(&self) -> i32; }\n"
            "enum Status { Active }\n"
            "impl User {\n"
            "    pub fn new(name: String) -> Self { User { name } }\n"
            "    pub fn greet(&self) { helper(); }\n"
            "}\n"
            "impl Repo for User {\n"
            "    fn find(&self) -> i32 { 0 }\n"
            "}\n"
            "fn top() {}\n"
        )
        assert r.namespace == "test"
        assert "std::fmt" in r.using_directives
        assert _sym(r, "test.User") is not None
        assert _sym(r, "test.User.name") is not None
        assert _sym(r, "test.Repo") is not None
        assert _sym(r, "test.Repo.find") is not None
        assert _sym(r, "test.Status") is not None
        assert _sym(r, "test.User.new") is not None
        assert _sym(r, "test.User.greet") is not None
        assert _sym(r, "test.top") is not None
        impl = _edges_of(r, EdgeType.IMPLEMENTS)
        assert any(e.target_fq_name == "Repo" for e in impl)
        calls = _edges_of(r, EdgeType.CALLS)
        assert any(e.target_fq_name == "helper" for e in calls)


# ------------------------------------------------------------------
# Edge cases
# ------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_file(self):
        r = _parse("")
        assert r.symbols == []

    def test_comment_only(self):
        r = _parse("// just a comment\n")
        assert r.symbols == []

    def test_syntax_error_partial(self):
        r = _parse("struct A { broken }")
        # tree-sitter is error-tolerant
        assert _sym(r, "test.A") is not None

    def test_file_path_preserved(self):
        r = _parse("struct A {}", "src/lib.rs")
        assert r.path == "src/lib.rs"
        assert r.symbols[0].file_path == "src/lib.rs"

    def test_long_name(self):
        name = "A" * 200
        r = _parse(f"struct {name} {{}}")
        assert _sym(r, f"test.{name}") is not None


# ------------------------------------------------------------------
# Parser interface
# ------------------------------------------------------------------


class TestRustParserInterface:
    def test_language_id(self):
        assert RustParser().language_id == "rust"

    def test_parse_via_interface(self):
        p = RustParser()
        r = p.parse_file(b"struct Foo {}", "foo.rs")
        assert _sym(r, "foo.Foo") is not None

    def test_complex_parse(self):
        p = RustParser()
        code = (
            b"use std::fmt;\n"
            b"/// Handler struct.\n"
            b"pub struct Handler {\n"
            b"    name: String,\n"
            b"}\n"
            b"pub trait Service {\n"
            b"    fn run(&self) -> Result<(), String>;\n"
            b"}\n"
            b"impl Handler {\n"
            b"    pub fn new(name: String) -> Self {\n"
            b"        Handler { name }\n"
            b"    }\n"
            b"    pub fn handle(&self) {\n"
            b"        helper();\n"
            b"    }\n"
            b"}\n"
            b"impl Service for Handler {\n"
            b"    fn run(&self) -> Result<(), String> {\n"
            b"        Ok(())\n"
            b"    }\n"
            b"}\n"
        )
        r = p.parse_file(code, "src/handler.rs")
        assert r.namespace == "src.handler"
        assert _sym(r, "src.handler.Handler") is not None
        assert _sym(r, "src.handler.Handler.name") is not None
        assert _sym(r, "src.handler.Service") is not None
        assert _sym(r, "src.handler.Service.run") is not None
        assert _sym(r, "src.handler.Handler.new") is not None
        assert _sym(r, "src.handler.Handler.new").kind == SymbolKind.CONSTRUCTOR
        assert _sym(r, "src.handler.Handler.handle") is not None
        assert "Handler struct" in _sym(r, "src.handler.Handler").doc_comment
        impl = _edges_of(r, EdgeType.IMPLEMENTS)
        assert any(e.target_fq_name == "Service" for e in impl)
        calls = _edges_of(r, EdgeType.CALLS)
        assert any(e.target_fq_name == "helper" for e in calls)


# ------------------------------------------------------------------
# Registry integration
# ------------------------------------------------------------------


class TestRegistryIntegration:
    def test_rust_registered(self):
        from app.analysis.parser_registry import supported_languages

        assert "rust" in supported_languages()

    def test_get_parser(self):
        from app.analysis.parser_registry import get_parser

        p = get_parser("rust")
        assert p is not None
        assert p.language_id == "rust"

    def test_all_seven_registered(self):
        from app.analysis.parser_registry import supported_languages

        langs = supported_languages()
        expected = {"csharp", "java", "python", "typescript", "tsx", "go", "rust"}
        assert expected <= langs


# ------------------------------------------------------------------
# Pipeline integration
# ------------------------------------------------------------------


class TestPipelineIntegration:
    def test_analyze_rust_files(self, tmp_path):
        from app.analysis.pipeline import analyze_snapshot_files

        f = tmp_path / "main.rs"
        f.write_text("struct Svc {}\nimpl Svc {\n    fn run(&self) { helper(); }\n}\n")
        records = [{"path": "main.rs", "language": "rust"}]
        graph = analyze_snapshot_files(tmp_path, records)
        assert "main.Svc" in graph.symbols
        assert "main.Svc.run" in graph.symbols

    def test_mixed_six_languages(self, tmp_path):
        from app.analysis.pipeline import analyze_snapshot_files

        (tmp_path / "A.cs").write_text("class CsA { void Run() {} }")
        (tmp_path / "B.java").write_text("class JavaB { void go() {} }")
        (tmp_path / "c.py").write_text("class PyC:\n    def do(self):\n        pass\n")
        (tmp_path / "d.ts").write_text("export class TsD { run() {} }")
        (tmp_path / "e.go").write_text("package main\ntype GoE struct{}\nfunc (g *GoE) Run() {}")
        (tmp_path / "f.rs").write_text("struct RustF {}\nimpl RustF { fn run(&self) {} }")

        records = [
            {"path": "A.cs", "language": "csharp"},
            {"path": "B.java", "language": "java"},
            {"path": "c.py", "language": "python"},
            {"path": "d.ts", "language": "typescript"},
            {"path": "e.go", "language": "go"},
            {"path": "f.rs", "language": "rust"},
        ]
        graph = analyze_snapshot_files(tmp_path, records)
        assert "CsA" in graph.symbols
        assert "JavaB" in graph.symbols
        assert "c.PyC" in graph.symbols
        assert "d.TsD" in graph.symbols
        assert "main.GoE" in graph.symbols
        assert "f.RustF" in graph.symbols
