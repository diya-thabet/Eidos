# Multi-Language Parser Architecture

## Overview

Eidos uses a **plugin-based parser architecture** that makes adding new
language support a matter of implementing one interface and registering it.
The system currently supports **C#**, **Java**, **Python**, **TypeScript/TSX**, **Go**, **Rust**, **C**, and **C++**.

## Architecture

```
                            parser_registry.py
                            (lazy discovery)
                                   |
   +------+------+--------+---------+---------+------+-------+-----+-----+
   |      |      |        |         |         |      |       |     |     |
  C#    Java   Python  TypeScript  TSX      Go    Rust     C    C++   ...
   |      |      |        |         |         |      |       |     |
 ts-c#  ts-java ts-py  ts-typescript        ts-go  ts-rust ts-c  ts-cpp
```

All parsers implement the `LanguageParser` abstract base class:

```python
class LanguageParser(ABC):
    @property
    @abstractmethod
    def language_id(self) -> str: ...

    @abstractmethod
    def parse_file(self, source: bytes, file_path: str) -> FileAnalysis: ...
```

## Supported Languages

| Language | Parser File | Grammar | Extensions | Symbols Extracted |
|----------|------------|---------|------------|-------------------|
| C# | `csharp_parser.py` | `tree-sitter-c-sharp` | `.cs`, `.csx` | classes, interfaces, structs, enums, records, delegates, methods, constructors, properties, fields |
| Java | `java_parser.py` | `tree-sitter-java` | `.java` | classes, interfaces, enums, records, annotations, methods, constructors, fields |
| Python | `python_parser.py` | `tree-sitter-python` | `.py`, `.pyi` | classes, functions, methods, constructors (__init__), properties (@property), nested classes, decorators (@staticmethod, @classmethod) |
| TypeScript | `typescript_parser.py` | `tree-sitter-typescript` | `.ts` | classes, interfaces, enums, type aliases, methods, constructors, fields, top-level functions, arrow functions (const fn = () => {}) |
| TSX | `typescript_parser.py` | `tree-sitter-typescript` | `.tsx` | same as TypeScript (shared parser with TSX grammar) |
| Go | `go_parser.py` | `tree-sitter-go` | `.go` | structs, interfaces, functions, methods (with receiver), fields, type aliases |
| Rust | `rust_parser.py` | `tree-sitter-rust` | `.rs` | structs, traits, enums, impl methods, constructors (fn new), fields, type aliases, inline modules |
| C | `c_parser.py` | `tree-sitter-c` | `.c`, `.h` | structs, enums, functions, typedefs, fields, static functions |
| C++ | `cpp_parser.py` | `tree-sitter-cpp` | `.cpp`, `.cc`, `.cxx`, `.hpp`, `.hxx`, `.h` | classes, structs, enums, namespaces, constructors, destructors, methods, fields, templates, free functions, inheritance |

## Edges Extracted (All Languages)

| Edge Type | Meaning | Example |
|-----------|---------|---------|
| `CALLS` | Function/method invocation | `run()` calls `helper()` |
| `INHERITS` | Class extends another | `Dog extends Animal` |
| `IMPLEMENTS` | Class implements interface | `SqlRepo implements IRepo` |
| `CONTAINS` | Parent-child relationship | `class Foo` contains `method bar` |
| `IMPORTS` | Import/using directive | `import java.util.List` |

## How to Add a New Language

### Step 1: Create the parser

Create `app/analysis/<lang>_parser.py`:

```python
import tree_sitter_<lang> as ts_lang
from tree_sitter import Language, Parser
from app.analysis.base_parser import LanguageParser
from app.analysis.models import FileAnalysis

class <Lang>Parser(LanguageParser):
    @property
    def language_id(self) -> str:
        return "<lang>"

    def parse_file(self, source: bytes, file_path: str) -> FileAnalysis:
        # ... tree-sitter parsing logic ...
```

### Step 2: Register in `parser_registry.py`

Add to `_init_registry()`:

```python
try:
    from app.analysis.<lang>_parser import <Lang>Parser
    _registry["<lang>"] = <Lang>Parser()
except Exception:
    logger.info("<Lang> parser unavailable")
```

### Step 3: Map file extensions

In `app/core/ingestion.py`, add to `LANGUAGE_MAP`:

```python
".<ext>": "<lang>",
```

### Step 4: Add the dependency

In `pyproject.toml`:

```toml
"tree-sitter-<lang>>=0.23",
```

### Step 5: Write tests

Create `tests/test_<lang>_parser.py` following the patterns in
`test_java_parser.py` or `test_python_parser.py`.

## Test Coverage

| Test File | Tests | Coverage |
|-----------|-------|---------|
| `test_csharp_parser.py` | 59 | C# symbols, edges, namespaces, generics, nested types |
| `test_java_parser.py` | 79 | Java packages, imports, classes, enums, generics, Javadoc |
| `test_python_parser.py` | 66 | Python imports, classes, functions, decorators, docstrings |
| `test_typescript_parser.py` | 83 | TypeScript/TSX imports, classes, interfaces, enums, generics, TSDoc, calls, abstract, pipeline |
| `test_hardening.py` | 82 | Parser enhancements, cross-language pipeline, binary input, input validation, security |
| `test_go_parser.py` | 58 | Go packages, imports, structs, interfaces, functions, methods, receivers, fields, calls, pipeline |
| `test_rust_parser.py` | 63 | Rust use decls, structs, traits, enums, impl blocks, trait impl, constructors, fields, calls, modules, pipeline |
| `test_c_parser.py` | 42 | C includes, structs, enums, functions, typedefs, fields, calls, static, pipeline |
| `test_cpp_parser.py` | 45 | C++ namespaces, classes, inheritance, constructors, destructors, new expressions, scoped calls, pipeline |
| `test_pipeline.py` | existing | Pipeline dispatch to all parsers |

## Design Decisions

1. **Lazy registration** -- Parsers are only imported when first needed.
   A missing `tree-sitter-java` does not crash the app; Java parsing
   is simply unavailable.

2. **Error-tolerant parsing** -- tree-sitter produces partial ASTs even
   for files with syntax errors, so broken files don't halt ingestion.

3. **Uniform output** -- Every parser produces the same `FileAnalysis`
   data model, so downstream consumers (graph builder, summarizer,
   indexer) work identically regardless of language.

4. **No grammar customization** -- We use upstream tree-sitter grammars
   unmodified, avoiding maintenance burden.

5. **Adapter pattern for C#** -- The original C# parser predates the
   interface, so `CSharpParserAdapter` wraps it without modifying it.
