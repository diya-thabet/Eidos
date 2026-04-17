"""
Comprehensive Python parser tests.

Tests: imports, classes, functions, methods, constructors, inheritance,
nested classes, decorators, async, docstrings, parameters, return types,
call extraction, module namespace, edge cases, registry, pipeline.
"""

from app.analysis.models import EdgeType, SymbolKind
from app.analysis.python_parser import PythonParser, parse_file


def _parse(code: str, path: str = "test.py"):
    return parse_file(code.encode("utf-8"), path)


def _sym(analysis, fq):
    return next((s for s in analysis.symbols if s.fq_name == fq), None)


def _edges_of(analysis, edge_type):
    return [e for e in analysis.edges if e.edge_type == edge_type]


# ------------------------------------------------------------------
# Imports
# ------------------------------------------------------------------


class TestImports:
    def test_import_statement(self):
        r = _parse("import os")
        assert "os" in r.using_directives

    def test_from_import(self):
        r = _parse("from pathlib import Path")
        assert "pathlib" in r.using_directives

    def test_multiple_imports(self):
        r = _parse("import os\nimport sys\nfrom typing import List\n")
        assert len(r.using_directives) == 3

    def test_import_edges(self):
        r = _parse("import os\nfrom pathlib import Path\n", "app/main.py")
        imp = _edges_of(r, EdgeType.IMPORTS)
        assert any(e.target_fq_name == "os" for e in imp)
        assert any(e.target_fq_name == "pathlib" for e in imp)

    def test_no_imports(self):
        r = _parse("x = 1")
        assert r.using_directives == []

    def test_dotted_import(self):
        r = _parse("import os.path")
        assert "os.path" in r.using_directives


# ------------------------------------------------------------------
# Module namespace
# ------------------------------------------------------------------


class TestModuleNamespace:
    def test_module_from_path(self):
        r = _parse("x = 1", "app/core/config.py")
        assert r.namespace == "app.core.config"

    def test_simple_filename(self):
        r = _parse("x = 1", "main.py")
        assert r.namespace == "main"

    def test_nested_path(self):
        r = _parse("x = 1", "a/b/c/d.py")
        assert r.namespace == "a.b.c.d"


# ------------------------------------------------------------------
# Class declarations
# ------------------------------------------------------------------


class TestClassDeclaration:
    def test_simple_class(self):
        r = _parse("class Foo:\n    pass")
        s = _sym(r, "test.Foo")
        assert s is not None
        assert s.kind == SymbolKind.CLASS

    def test_class_with_base(self):
        r = _parse("class Dog(Animal):\n    pass")
        s = _sym(r, "test.Dog")
        assert "Animal" in s.base_types

    def test_multiple_bases(self):
        r = _parse("class Foo(Bar, Baz, Qux):\n    pass")
        s = _sym(r, "test.Foo")
        assert s.base_types == ["Bar", "Baz", "Qux"]

    def test_no_bases(self):
        r = _parse("class Foo:\n    pass")
        assert _sym(r, "test.Foo").base_types == []

    def test_inheritance_edges(self):
        r = _parse("class Foo(Bar, Baz):\n    pass")
        inh = _edges_of(r, EdgeType.INHERITS)
        targets = {e.target_fq_name for e in inh}
        assert "Bar" in targets
        assert "Baz" in targets

    def test_class_line_numbers(self):
        r = _parse("x = 1\n\nclass Foo:\n    pass\n")
        s = _sym(r, "test.Foo")
        assert s.start_line == 3
        assert s.end_line == 4

    def test_class_fq_with_module(self):
        r = _parse("class Foo:\n    pass", "app/service.py")
        assert _sym(r, "app.service.Foo") is not None


# ------------------------------------------------------------------
# Methods and functions
# ------------------------------------------------------------------


class TestFunctionDeclaration:
    def test_top_level_function(self):
        r = _parse("def run():\n    pass")
        s = _sym(r, "test.run")
        assert s is not None
        assert s.kind == SymbolKind.METHOD

    def test_method_in_class(self):
        r = _parse("class A:\n    def go(self):\n        pass")
        m = _sym(r, "test.A.go")
        assert m is not None
        assert m.kind == SymbolKind.METHOD

    def test_constructor(self):
        r = _parse("class A:\n    def __init__(self):\n        pass")
        c = _sym(r, "test.A.__init__")
        assert c is not None
        assert c.kind == SymbolKind.CONSTRUCTOR

    def test_parameters(self):
        r = _parse("def run(a, b, c):\n    pass")
        s = _sym(r, "test.run")
        assert s.parameters == ["a", "b", "c"]

    def test_typed_parameters(self):
        r = _parse("def run(name: str, count: int):\n    pass")
        s = _sym(r, "test.run")
        assert len(s.parameters) == 2
        assert any("str" in p for p in s.parameters)

    def test_self_excluded(self):
        r = _parse("class A:\n    def go(self, x):\n        pass")
        m = _sym(r, "test.A.go")
        assert "self" not in " ".join(m.parameters)

    def test_cls_excluded(self):
        r = _parse("class A:\n    def go(cls, x):\n        pass")
        m = _sym(r, "test.A.go")
        assert "cls" not in " ".join(m.parameters)

    def test_return_type(self):
        r = _parse("def run() -> bool:\n    pass")
        s = _sym(r, "test.run")
        assert s.return_type == "bool"

    def test_no_return_type(self):
        r = _parse("def run():\n    pass")
        assert _sym(r, "test.run").return_type == ""

    def test_signature(self):
        r = _parse("def run(a: int, b: str) -> bool:\n    pass")
        s = _sym(r, "test.run")
        assert "run" in s.signature
        assert "int" in s.signature

    def test_multiple_methods(self):
        r = _parse(
            "class A:\n"
            "    def a(self):\n        pass\n"
            "    def b(self):\n        pass\n"
            "    def c(self):\n        pass\n"
        )
        methods = [s for s in r.symbols if s.kind == SymbolKind.METHOD]
        assert len(methods) == 3

    def test_containment_edge(self):
        r = _parse("class A:\n    def go(self):\n        pass")
        contains = _edges_of(r, EdgeType.CONTAINS)
        assert any(
            e.source_fq_name == "test.A" and e.target_fq_name == "test.A.go" for e in contains
        )


# ------------------------------------------------------------------
# Call extraction
# ------------------------------------------------------------------


class TestCallExtraction:
    def test_simple_call(self):
        r = _parse("def run():\n    helper()")
        calls = _edges_of(r, EdgeType.CALLS)
        assert any(e.target_fq_name == "helper" for e in calls)

    def test_method_call(self):
        r = _parse("def run():\n    obj.method()")
        calls = _edges_of(r, EdgeType.CALLS)
        assert any(e.target_fq_name == "method" for e in calls)

    def test_multiple_calls(self):
        r = _parse("def run():\n    a()\n    b()\n    c()")
        calls = _edges_of(r, EdgeType.CALLS)
        targets = {e.target_fq_name for e in calls}
        assert {"a", "b", "c"} <= targets

    def test_nested_calls(self):
        r = _parse("def run():\n    outer(inner())")
        calls = _edges_of(r, EdgeType.CALLS)
        targets = {e.target_fq_name for e in calls}
        assert "outer" in targets
        assert "inner" in targets

    def test_call_in_constructor(self):
        r = _parse("class A:\n    def __init__(self):\n        self.setup()")
        calls = _edges_of(r, EdgeType.CALLS)
        assert any(e.target_fq_name == "setup" for e in calls)

    def test_call_line_number(self):
        r = _parse("def run():\n    x = 1\n    helper()\n")
        calls = _edges_of(r, EdgeType.CALLS)
        assert len(calls) >= 1
        assert calls[0].line == 3


# ------------------------------------------------------------------
# Nested classes
# ------------------------------------------------------------------


class TestNestedClasses:
    def test_inner_class(self):
        r = _parse("class Outer:\n    class Inner:\n        pass")
        assert _sym(r, "test.Outer") is not None
        assert _sym(r, "test.Outer.Inner") is not None

    def test_inner_containment(self):
        r = _parse("class Outer:\n    class Inner:\n        pass")
        contains = _edges_of(r, EdgeType.CONTAINS)
        assert any(
            e.source_fq_name == "test.Outer" and e.target_fq_name == "test.Outer.Inner"
            for e in contains
        )

    def test_deep_nesting(self):
        r = _parse("class A:\n    class B:\n        class C:\n            pass\n")
        assert _sym(r, "test.A") is not None
        assert _sym(r, "test.A.B") is not None
        assert _sym(r, "test.A.B.C") is not None


# ------------------------------------------------------------------
# Docstrings
# ------------------------------------------------------------------


class TestDocstrings:
    def test_class_docstring(self):
        r = _parse('class Foo:\n    """A class."""\n    pass')
        s = _sym(r, "test.Foo")
        assert "A class" in s.doc_comment

    def test_method_docstring(self):
        r = _parse('class A:\n    def run(self):\n        """Does stuff."""\n        pass\n')
        m = _sym(r, "test.A.run")
        assert "Does stuff" in m.doc_comment

    def test_no_docstring(self):
        r = _parse("def run():\n    pass")
        assert _sym(r, "test.run").doc_comment == ""

    def test_single_quote_docstring(self):
        r = _parse("def run():\n    '''Single.'''\n    pass")
        assert "Single" in _sym(r, "test.run").doc_comment

    def test_function_docstring(self):
        r = _parse('def top():\n    """Top level."""\n    pass')
        assert "Top level" in _sym(r, "test.top").doc_comment


# ------------------------------------------------------------------
# Decorators
# ------------------------------------------------------------------


class TestDecorators:
    def test_decorated_function(self):
        r = _parse("@staticmethod\ndef run():\n    pass")
        s = _sym(r, "test.run")
        assert s is not None

    def test_decorated_class(self):
        r = _parse("@dataclass\nclass Foo:\n    x: int = 0")
        s = _sym(r, "test.Foo")
        assert s is not None


# ------------------------------------------------------------------
# Async
# ------------------------------------------------------------------


class TestAsync:
    def test_async_function(self):
        r = _parse("async def run():\n    pass")
        s = _sym(r, "test.run")
        assert s is not None

    def test_async_method(self):
        r = _parse("class A:\n    async def go(self):\n        pass")
        m = _sym(r, "test.A.go")
        assert m is not None


# ------------------------------------------------------------------
# Default / keyword params
# ------------------------------------------------------------------


class TestDefaultParams:
    def test_default_parameter(self):
        r = _parse("def run(x=5):\n    pass")
        s = _sym(r, "test.run")
        assert "x" in s.parameters

    def test_star_args(self):
        r = _parse("def run(*args, **kwargs):\n    pass")
        s = _sym(r, "test.run")
        assert len(s.parameters) >= 1


# ------------------------------------------------------------------
# Multiple classes in one file
# ------------------------------------------------------------------


class TestMultipleDefinitions:
    def test_two_classes(self):
        r = _parse("class A:\n    pass\nclass B:\n    pass\n")
        assert _sym(r, "test.A") is not None
        assert _sym(r, "test.B") is not None

    def test_class_and_function(self):
        r = _parse("class Foo:\n    pass\ndef bar():\n    pass\n")
        assert _sym(r, "test.Foo") is not None
        assert _sym(r, "test.bar") is not None

    def test_mixed_complex(self):
        r = _parse(
            "import os\n"
            "class Svc(Base):\n"
            "    def __init__(self):\n        pass\n"
            "    def run(self, x: int) -> bool:\n"
            "        helper()\n        return True\n"
            "def standalone(a, b):\n    pass\n"
        )
        assert _sym(r, "test.Svc") is not None
        assert _sym(r, "test.Svc.__init__") is not None
        assert _sym(r, "test.Svc.run") is not None
        assert _sym(r, "test.standalone") is not None
        assert "Base" in _sym(r, "test.Svc").base_types


# ------------------------------------------------------------------
# Edge cases
# ------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_file(self):
        r = _parse("")
        assert r.symbols == []

    def test_comment_only(self):
        r = _parse("# just a comment\n")
        assert r.symbols == []

    def test_empty_class(self):
        r = _parse("class Empty:\n    pass")
        assert len(r.symbols) == 1

    def test_very_long_name(self):
        name = "A" * 200
        r = _parse(f"class {name}:\n    pass")
        assert _sym(r, f"test.{name}") is not None

    def test_syntax_error_partial(self):
        r = _parse("class A:\n    def broken(\n")
        # tree-sitter is error-tolerant
        assert _sym(r, "test.A") is not None

    def test_file_path_preserved(self):
        r = _parse("class A:\n    pass", "src/pkg/mod.py")
        assert r.path == "src/pkg/mod.py"
        assert r.symbols[0].file_path == "src/pkg/mod.py"

    def test_pyi_stub(self):
        r = _parse("def foo(x: int) -> str: ...", "mod.pyi")
        assert r.namespace == "mod"


# ------------------------------------------------------------------
# Parser interface
# ------------------------------------------------------------------


class TestPythonParserInterface:
    def test_language_id(self):
        assert PythonParser().language_id == "python"

    def test_parse_via_interface(self):
        p = PythonParser()
        r = p.parse_file(b"class Foo:\n    pass", "foo.py")
        assert _sym(r, "foo.Foo") is not None

    def test_complex_parse(self):
        p = PythonParser()
        code = (
            b"import os\n"
            b"from typing import List\n"
            b"class Svc(Base):\n"
            b"    def __init__(self, items: List[str]):\n"
            b"        self.items = items\n"
            b"    def run(self) -> bool:\n"
            b"        process()\n"
            b"        return True\n"
        )
        r = p.parse_file(code, "app/svc.py")
        assert r.namespace == "app.svc"
        assert _sym(r, "app.svc.Svc") is not None
        assert _sym(r, "app.svc.Svc.__init__") is not None
        assert _sym(r, "app.svc.Svc.run") is not None
        calls = _edges_of(r, EdgeType.CALLS)
        assert any(e.target_fq_name == "process" for e in calls)


# ------------------------------------------------------------------
# Registry integration
# ------------------------------------------------------------------


class TestRegistryIntegration:
    def test_python_registered(self):
        from app.analysis.parser_registry import supported_languages

        assert "python" in supported_languages()

    def test_get_parser(self):
        from app.analysis.parser_registry import get_parser

        p = get_parser("python")
        assert p is not None
        assert p.language_id == "python"

    def test_all_three_registered(self):
        from app.analysis.parser_registry import supported_languages

        langs = supported_languages()
        assert "csharp" in langs
        assert "java" in langs
        assert "python" in langs


# ------------------------------------------------------------------
# Pipeline integration
# ------------------------------------------------------------------


class TestPipelineIntegration:
    def test_analyze_python_files(self, tmp_path):
        from app.analysis.pipeline import analyze_snapshot_files

        f = tmp_path / "svc.py"
        f.write_text("class Svc:\n    def run(self):\n        helper()\n")
        records = [{"path": "svc.py", "language": "python"}]
        graph = analyze_snapshot_files(tmp_path, records)
        assert "svc.Svc" in graph.symbols
        assert "svc.Svc.run" in graph.symbols

    def test_mixed_three_languages(self, tmp_path):
        from app.analysis.pipeline import analyze_snapshot_files

        (tmp_path / "A.java").write_text("class JavaA { void go() {} }")
        (tmp_path / "B.cs").write_text("class CSharpB { void Run() {} }")
        (tmp_path / "c.py").write_text("class PythonC:\n    def do(self):\n        pass\n")

        records = [
            {"path": "A.java", "language": "java"},
            {"path": "B.cs", "language": "csharp"},
            {"path": "c.py", "language": "python"},
        ]
        graph = analyze_snapshot_files(tmp_path, records)
        assert "JavaA" in graph.symbols
        assert "CSharpB" in graph.symbols
        assert "c.PythonC" in graph.symbols
