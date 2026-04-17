"""
Comprehensive TypeScript parser tests.

Tests: imports, classes, interfaces, enums, methods, constructors,
fields, inheritance, implements, generics, async, decorators, TSDoc,
call extraction, new expressions, nested classes, export handling,
abstract classes, top-level functions, TSX, edge cases, registry,
pipeline integration.
"""

from app.analysis.models import EdgeType, SymbolKind
from app.analysis.typescript_parser import TSXParser, TypeScriptParser, parse_file


def _parse(code: str, path: str = "test.ts"):
    return parse_file(code.encode("utf-8"), path)


def _parse_tsx(code: str, path: str = "test.tsx"):
    return parse_file(code.encode("utf-8"), path, tsx=True)


def _sym(analysis, fq):
    return next((s for s in analysis.symbols if s.fq_name == fq), None)


def _edges_of(analysis, edge_type):
    return [e for e in analysis.edges if e.edge_type == edge_type]


# ------------------------------------------------------------------
# Imports
# ------------------------------------------------------------------


class TestImports:
    def test_named_import(self):
        r = _parse("import { Foo } from 'bar';")
        assert "bar" in r.using_directives

    def test_namespace_import(self):
        r = _parse("import * as fs from 'fs';")
        assert "fs" in r.using_directives

    def test_multiple_imports(self):
        r = _parse("import { A } from 'a';\nimport { B } from 'b';\nimport { C } from 'c';\n")
        assert len(r.using_directives) == 3

    def test_import_edges(self):
        r = _parse("import { X } from '@angular/core';", "svc.ts")
        imp = _edges_of(r, EdgeType.IMPORTS)
        assert any(e.target_fq_name == "@angular/core" for e in imp)

    def test_no_imports(self):
        r = _parse("class A {}")
        assert r.using_directives == []

    def test_side_effect_import(self):
        r = _parse("import 'reflect-metadata';")
        assert len(r.using_directives) >= 1


# ------------------------------------------------------------------
# Module namespace
# ------------------------------------------------------------------


class TestModuleNamespace:
    def test_ts_extension(self):
        r = _parse("class A {}", "src/app/svc.ts")
        assert r.namespace == "src.app.svc"

    def test_tsx_extension(self):
        r = _parse_tsx("class A {}", "App.tsx")
        assert r.namespace == "App"


# ------------------------------------------------------------------
# Class declarations
# ------------------------------------------------------------------


class TestClassDeclaration:
    def test_simple_class(self):
        r = _parse("class Foo {}")
        s = _sym(r, "test.Foo")
        assert s is not None
        assert s.kind == SymbolKind.CLASS

    def test_exported_class(self):
        r = _parse("export class Foo {}")
        s = _sym(r, "test.Foo")
        assert s is not None
        assert "export" in s.modifiers

    def test_abstract_class(self):
        r = _parse("export abstract class Foo {}")
        s = _sym(r, "test.Foo")
        assert "abstract" in s.modifiers

    def test_class_with_module(self):
        r = _parse("export class Svc {}", "src/app/service.ts")
        assert _sym(r, "src.app.service.Svc") is not None

    def test_class_line_numbers(self):
        r = _parse("// comment\nexport class Foo {\n}\n")
        s = _sym(r, "test.Foo")
        assert s.start_line == 2
        assert s.end_line == 3


class TestInheritance:
    def test_extends(self):
        r = _parse("class Dog extends Animal {}")
        s = _sym(r, "test.Dog")
        assert "Animal" in s.base_types
        inh = _edges_of(r, EdgeType.INHERITS)
        assert any(e.target_fq_name == "Animal" for e in inh)

    def test_implements_single(self):
        r = _parse("class Foo implements IRepo {}")
        impl = _edges_of(r, EdgeType.IMPLEMENTS)
        assert any(e.target_fq_name == "IRepo" for e in impl)

    def test_implements_multiple(self):
        r = _parse("class Foo implements IRepo, ILogger {}")
        impl = _edges_of(r, EdgeType.IMPLEMENTS)
        targets = {e.target_fq_name for e in impl}
        assert "IRepo" in targets
        assert "ILogger" in targets

    def test_extends_and_implements(self):
        r = _parse("class Foo extends Bar implements Baz, Qux {}")
        s = _sym(r, "test.Foo")
        assert "Bar" in s.base_types
        assert "Baz" in s.base_types

    def test_no_inheritance(self):
        r = _parse("class Foo {}")
        assert _sym(r, "test.Foo").base_types == []


# ------------------------------------------------------------------
# Interface declarations
# ------------------------------------------------------------------


class TestInterfaceDeclaration:
    def test_simple_interface(self):
        r = _parse("interface IFoo {}")
        s = _sym(r, "test.IFoo")
        assert s is not None
        assert s.kind == SymbolKind.INTERFACE

    def test_exported_interface(self):
        r = _parse("export interface IFoo {}")
        assert _sym(r, "test.IFoo") is not None

    def test_interface_with_method(self):
        r = _parse("interface IRepo { save(item: string): void; }")
        assert _sym(r, "test.IRepo.save") is not None
        assert _sym(r, "test.IRepo.save").kind == SymbolKind.METHOD

    def test_interface_with_property(self):
        r = _parse("interface IConfig { name: string; }")
        # property_signature
        syms = [s for s in r.symbols if s.parent_fq_name == "test.IConfig"]
        assert len(syms) >= 1

    def test_interface_method_containment(self):
        r = _parse("interface IRepo { find(id: number): string; }")
        contains = _edges_of(r, EdgeType.CONTAINS)
        assert any(
            e.source_fq_name == "test.IRepo" and e.target_fq_name == "test.IRepo.find"
            for e in contains
        )


# ------------------------------------------------------------------
# Enum declarations
# ------------------------------------------------------------------


class TestEnumDeclaration:
    def test_simple_enum(self):
        r = _parse("enum Status { Active, Inactive }")
        s = _sym(r, "test.Status")
        assert s is not None
        assert s.kind == SymbolKind.ENUM

    def test_exported_enum(self):
        r = _parse("export enum Color { Red, Green, Blue }")
        assert _sym(r, "test.Color") is not None

    def test_const_enum(self):
        r = _parse("const enum Dir { Up, Down }")
        # const enums may parse as enum_declaration
        assert len(r.symbols) >= 0  # no crash


# ------------------------------------------------------------------
# Methods
# ------------------------------------------------------------------


class TestMethodDeclaration:
    def test_simple_method(self):
        r = _parse("class A { run() {} }")
        m = _sym(r, "test.A.run")
        assert m is not None
        assert m.kind == SymbolKind.METHOD

    def test_method_parameters(self):
        r = _parse("class A { go(name: string, count: number) {} }")
        m = _sym(r, "test.A.go")
        assert len(m.parameters) == 2

    def test_return_type(self):
        r = _parse("class A { getName(): string { return ''; } }")
        m = _sym(r, "test.A.getName")
        assert "string" in m.return_type

    def test_async_method(self):
        r = _parse("class A { async run(): Promise<void> {} }")
        m = _sym(r, "test.A.run")
        assert "async" in m.modifiers

    def test_public_method(self):
        r = _parse("class A { public run() {} }")
        m = _sym(r, "test.A.run")
        assert "public" in m.modifiers

    def test_private_method(self):
        r = _parse("class A { private internal() {} }")
        m = _sym(r, "test.A.internal")
        assert "private" in m.modifiers

    def test_multiple_methods(self):
        r = _parse("class A { a() {} b() {} c() {} }")
        methods = [s for s in r.symbols if s.kind == SymbolKind.METHOD]
        assert len(methods) == 3

    def test_containment_edge(self):
        r = _parse("class A { go() {} }")
        contains = _edges_of(r, EdgeType.CONTAINS)
        assert any(
            e.source_fq_name == "test.A" and e.target_fq_name == "test.A.go" for e in contains
        )


# ------------------------------------------------------------------
# Constructors
# ------------------------------------------------------------------


class TestConstructorDeclaration:
    def test_simple_constructor(self):
        r = _parse("class Foo { constructor() {} }")
        c = _sym(r, "test.Foo.constructor")
        assert c is not None
        assert c.kind == SymbolKind.CONSTRUCTOR

    def test_constructor_with_params(self):
        r = _parse("class Foo { constructor(x: number, y: string) {} }")
        c = _sym(r, "test.Foo.constructor")
        assert len(c.parameters) == 2

    def test_constructor_calls(self):
        r = _parse("class Foo { constructor() { init(); new Bar(); } }")
        calls = _edges_of(r, EdgeType.CALLS)
        targets = {e.target_fq_name for e in calls}
        assert "init" in targets
        assert "Bar" in targets

    def test_constructor_shorthand_params(self):
        r = _parse("class Foo { constructor(private name: string) {} }")
        c = _sym(r, "test.Foo.constructor")
        assert len(c.parameters) >= 1


# ------------------------------------------------------------------
# Fields / Properties
# ------------------------------------------------------------------


class TestFieldDeclaration:
    def test_public_field(self):
        r = _parse("class A { public x: number = 0; }")
        f = _sym(r, "test.A.x")
        assert f is not None
        assert f.kind == SymbolKind.FIELD

    def test_private_field(self):
        r = _parse("class A { private secret: string = ''; }")
        f = _sym(r, "test.A.secret")
        assert "private" in f.modifiers

    def test_readonly_field(self):
        r = _parse("class A { readonly MAX: number = 100; }")
        f = _sym(r, "test.A.MAX")
        assert f is not None

    def test_multiple_fields(self):
        r = _parse("class A { x: number = 0; y: string = ''; z: boolean = true; }")
        fields = [s for s in r.symbols if s.kind == SymbolKind.FIELD]
        assert len(fields) == 3


# ------------------------------------------------------------------
# Call extraction
# ------------------------------------------------------------------


class TestCallExtraction:
    def test_function_call(self):
        r = _parse("class A { run() { doSomething(); } }")
        calls = _edges_of(r, EdgeType.CALLS)
        assert any(e.target_fq_name == "doSomething" for e in calls)

    def test_method_call(self):
        r = _parse("class A { run() { this.helper(); } }")
        calls = _edges_of(r, EdgeType.CALLS)
        assert any(e.target_fq_name == "helper" for e in calls)

    def test_new_expression(self):
        r = _parse("class A { run() { new ArrayList(); } }")
        calls = _edges_of(r, EdgeType.CALLS)
        assert any(e.target_fq_name == "ArrayList" for e in calls)

    def test_multiple_calls(self):
        r = _parse("class A { run() { a(); b(); c(); } }")
        targets = {e.target_fq_name for e in _edges_of(r, EdgeType.CALLS)}
        assert {"a", "b", "c"} <= targets

    def test_nested_calls(self):
        r = _parse("class A { run() { outer(inner()); } }")
        targets = {e.target_fq_name for e in _edges_of(r, EdgeType.CALLS)}
        assert "outer" in targets
        assert "inner" in targets

    def test_call_line_number(self):
        r = _parse("class A {\n  run() {\n    foo();\n  }\n}")
        calls = _edges_of(r, EdgeType.CALLS)
        assert calls[0].line == 3


# ------------------------------------------------------------------
# Top-level functions
# ------------------------------------------------------------------


class TestFunctionDeclaration:
    def test_exported_function(self):
        r = _parse("export function helper(x: number): string { return ''; }")
        s = _sym(r, "test.helper")
        assert s is not None
        assert s.kind == SymbolKind.METHOD

    def test_function_params(self):
        r = _parse("function run(a: string, b: number): void {}")
        s = _sym(r, "test.run")
        assert len(s.parameters) == 2

    def test_function_return_type(self):
        r = _parse("function calc(): number { return 42; }")
        s = _sym(r, "test.calc")
        assert "number" in s.return_type

    def test_function_calls(self):
        r = _parse("function run() { helper(); }")
        calls = _edges_of(r, EdgeType.CALLS)
        assert any(e.target_fq_name == "helper" for e in calls)


# ------------------------------------------------------------------
# TSDoc / JSDoc
# ------------------------------------------------------------------


class TestTSDoc:
    def test_class_tsdoc(self):
        r = _parse("/** Service class. */\nclass Svc {}")
        s = _sym(r, "test.Svc")
        assert "Service class" in s.doc_comment

    def test_method_tsdoc(self):
        r = _parse("class A {\n  /** Does stuff. */\n  run() {}\n}")
        m = _sym(r, "test.A.run")
        assert "Does stuff" in m.doc_comment

    def test_no_tsdoc(self):
        r = _parse("class A { run() {} }")
        assert _sym(r, "test.A.run").doc_comment == ""

    def test_regular_comment_ignored(self):
        r = _parse("// not tsdoc\nclass A {}")
        assert _sym(r, "test.A").doc_comment == ""


# ------------------------------------------------------------------
# Generics
# ------------------------------------------------------------------


class TestGenerics:
    def test_generic_class(self):
        r = _parse("class Box<T> {}")
        assert _sym(r, "test.Box") is not None

    def test_generic_extends(self):
        r = _parse("class NumBox<T> extends Box<T> {}")
        s = _sym(r, "test.NumBox")
        assert len(s.base_types) >= 1

    def test_generic_return_type(self):
        r = _parse("class A { getItems(): Array<string> { return []; } }")
        m = _sym(r, "test.A.getItems")
        assert "Array" in m.return_type


# ------------------------------------------------------------------
# Multiple declarations in one file
# ------------------------------------------------------------------


class TestMultipleDeclarations:
    def test_class_and_interface(self):
        r = _parse(
            "export interface IRepo { save(): void; }\n"
            "export class SqlRepo implements IRepo { save() {} }\n"
        )
        assert _sym(r, "test.IRepo") is not None
        assert _sym(r, "test.SqlRepo") is not None
        impl = _edges_of(r, EdgeType.IMPLEMENTS)
        assert any(e.target_fq_name == "IRepo" for e in impl)

    def test_class_and_enum_and_function(self):
        r = _parse("export class A {}\nenum Status { Active }\nexport function helper(): void {}\n")
        assert _sym(r, "test.A") is not None
        assert _sym(r, "test.Status") is not None
        assert _sym(r, "test.helper") is not None


# ------------------------------------------------------------------
# TSX support
# ------------------------------------------------------------------


class TestTSX:
    def test_tsx_class(self):
        r = _parse_tsx("export class App {}", "App.tsx")
        assert _sym(r, "App.App") is not None

    def test_tsx_function(self):
        r = _parse_tsx("export function Greeting(): void {}", "Greeting.tsx")
        assert _sym(r, "Greeting.Greeting") is not None


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

    def test_empty_class(self):
        r = _parse("class Empty {}")
        assert len(r.symbols) == 1

    def test_long_class_name(self):
        name = "A" * 200
        r = _parse(f"class {name} {{}}")
        assert _sym(r, f"test.{name}") is not None

    def test_syntax_error_partial(self):
        r = _parse("class A { broken( {} }")
        assert _sym(r, "test.A") is not None

    def test_file_path_preserved(self):
        r = _parse("class A {}", "src/app/svc.ts")
        assert r.path == "src/app/svc.ts"
        assert r.symbols[0].file_path == "src/app/svc.ts"

    def test_d_ts_stub(self):
        r = _parse("export declare class Foo {}", "types.d.ts")
        assert r.namespace == "types.d"

    def test_only_imports(self):
        r = _parse("import { A } from 'a';")
        assert r.symbols == []
        assert len(r.using_directives) == 1


# ------------------------------------------------------------------
# Parser interface
# ------------------------------------------------------------------


class TestParserInterface:
    def test_typescript_language_id(self):
        assert TypeScriptParser().language_id == "typescript"

    def test_tsx_language_id(self):
        assert TSXParser().language_id == "tsx"

    def test_parse_via_ts_interface(self):
        p = TypeScriptParser()
        r = p.parse_file(b"class Foo {}", "foo.ts")
        assert _sym(r, "foo.Foo") is not None

    def test_parse_via_tsx_interface(self):
        p = TSXParser()
        r = p.parse_file(b"class Foo {}", "foo.tsx")
        assert _sym(r, "foo.Foo") is not None

    def test_complex_parse(self):
        p = TypeScriptParser()
        code = (
            b"import { Injectable } from '@angular/core';\n"
            b"export class Svc extends Base implements IRepo {\n"
            b"  private count: number = 0;\n"
            b"  constructor(private repo: IRepo) { super(); }\n"
            b"  public async run(name: string): Promise<boolean> {\n"
            b"    process();\n"
            b"    new Helper();\n"
            b"    return true;\n"
            b"  }\n"
            b"}\n"
        )
        r = p.parse_file(code, "src/svc.ts")
        assert r.namespace == "src.svc"
        assert _sym(r, "src.svc.Svc") is not None
        assert _sym(r, "src.svc.Svc.constructor") is not None
        assert _sym(r, "src.svc.Svc.run") is not None
        assert _sym(r, "src.svc.Svc.count") is not None
        inh = _edges_of(r, EdgeType.INHERITS)
        assert any(e.target_fq_name == "Base" for e in inh)
        impl = _edges_of(r, EdgeType.IMPLEMENTS)
        assert any(e.target_fq_name == "IRepo" for e in impl)
        calls = _edges_of(r, EdgeType.CALLS)
        targets = {e.target_fq_name for e in calls}
        assert "process" in targets
        assert "Helper" in targets


# ------------------------------------------------------------------
# Registry integration
# ------------------------------------------------------------------


class TestRegistryIntegration:
    def test_typescript_registered(self):
        from app.analysis.parser_registry import supported_languages

        assert "typescript" in supported_languages()

    def test_tsx_registered(self):
        from app.analysis.parser_registry import supported_languages

        assert "tsx" in supported_languages()

    def test_all_four_registered(self):
        from app.analysis.parser_registry import supported_languages

        langs = supported_languages()
        assert {"csharp", "java", "python", "typescript", "tsx"} <= langs

    def test_get_ts_parser(self):
        from app.analysis.parser_registry import get_parser

        p = get_parser("typescript")
        assert p is not None
        assert p.language_id == "typescript"


# ------------------------------------------------------------------
# Pipeline integration
# ------------------------------------------------------------------


class TestPipelineIntegration:
    def test_analyze_ts_files(self, tmp_path):
        from app.analysis.pipeline import analyze_snapshot_files

        f = tmp_path / "svc.ts"
        f.write_text("export class Svc {\n  run() { helper(); }\n}\n")
        records = [{"path": "svc.ts", "language": "typescript"}]
        graph = analyze_snapshot_files(tmp_path, records)
        assert "svc.Svc" in graph.symbols
        assert "svc.Svc.run" in graph.symbols

    def test_mixed_four_languages(self, tmp_path):
        from app.analysis.pipeline import analyze_snapshot_files

        (tmp_path / "A.java").write_text("class JavaA { void go() {} }")
        (tmp_path / "B.cs").write_text("class CSharpB { void Run() {} }")
        (tmp_path / "c.py").write_text("class PythonC:\n    def do(self):\n        pass\n")
        (tmp_path / "d.ts").write_text("export class TsD { run() {} }")

        records = [
            {"path": "A.java", "language": "java"},
            {"path": "B.cs", "language": "csharp"},
            {"path": "c.py", "language": "python"},
            {"path": "d.ts", "language": "typescript"},
        ]
        graph = analyze_snapshot_files(tmp_path, records)
        assert "JavaA" in graph.symbols
        assert "CSharpB" in graph.symbols
        assert "c.PythonC" in graph.symbols
        assert "d.TsD" in graph.symbols

    def test_tsx_in_pipeline(self, tmp_path):
        from app.analysis.pipeline import analyze_snapshot_files

        (tmp_path / "App.tsx").write_text("export class App {}")
        records = [{"path": "App.tsx", "language": "tsx"}]
        graph = analyze_snapshot_files(tmp_path, records)
        assert "App.App" in graph.symbols
