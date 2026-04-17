"""
Tests for the C# parser.

Covers: classes, interfaces, structs, enums, methods, constructors,
properties, fields, inheritance, using directives, nested types,
method calls, and edge extraction.
"""

from app.analysis.csharp_parser import parse_file
from app.analysis.models import EdgeType, SymbolKind

# ---------------------------------------------------------------------------
# Fixtures: sample C# source files
# ---------------------------------------------------------------------------

SIMPLE_CLASS = b"""\
using System;
using System.Collections.Generic;

namespace MyApp.Services
{
    /// <summary>Service for managing users.</summary>
    public class UserService : IUserService
    {
        private readonly ILogger _logger;

        public UserService(ILogger logger)
        {
            _logger = logger;
        }

        public User GetById(int id)
        {
            _logger.LogInfo("Fetching user");
            return _repository.Find(id);
        }

        public void Delete(int id)
        {
            var user = GetById(id);
            _repository.Remove(user);
        }

        private int ComputeHash(string input)
        {
            return input.GetHashCode();
        }
    }
}
"""

INTERFACE_AND_ENUM = b"""\
namespace MyApp.Contracts
{
    public interface IUserService
    {
        User GetById(int id);
        void Delete(int id);
    }

    public enum UserRole
    {
        Admin,
        User,
        Guest
    }
}
"""

CONTROLLER = b"""\
using Microsoft.AspNetCore.Mvc;

namespace MyApp.Controllers
{
    [ApiController]
    [Route("api/[controller]")]
    public class UsersController : ControllerBase
    {
        private readonly IUserService _service;

        public UsersController(IUserService service)
        {
            _service = service;
        }

        [HttpGet("{id}")]
        public IActionResult Get(int id)
        {
            var user = _service.GetById(id);
            return Ok(user);
        }

        [HttpDelete("{id}")]
        public IActionResult Delete(int id)
        {
            _service.Delete(id);
            return NoContent();
        }
    }
}
"""

NESTED_CLASS = b"""\
namespace MyApp.Models
{
    public class Order
    {
        public class OrderItem
        {
            public string Name { get; set; }
            public int Quantity { get; set; }
        }

        public OrderItem CreateItem(string name)
        {
            return new OrderItem();
        }
    }
}
"""

STRUCT_AND_RECORD = b"""\
namespace MyApp.Models
{
    public struct Point
    {
        public int X { get; set; }
        public int Y { get; set; }
    }

    public record PersonRecord(string Name, int Age);
}
"""

STATIC_MAIN = b"""\
namespace MyApp
{
    public class Program
    {
        public static void Main(string[] args)
        {
            var builder = WebApplication.CreateBuilder(args);
            builder.Build().Run();
        }
    }
}
"""

MULTIPLE_METHODS_WITH_CALLS = b"""\
namespace MyApp.Logic
{
    public class Calculator
    {
        public int Add(int a, int b)
        {
            Log("Adding");
            return a + b;
        }

        public int Multiply(int a, int b)
        {
            var result = Add(a, 0);
            for (int i = 1; i < b; i++)
            {
                result = Add(result, a);
            }
            return result;
        }

        private void Log(string message)
        {
            Console.WriteLine(message);
        }
    }
}
"""


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


class TestBasicParsing:
    """Tests for basic symbol extraction."""

    def test_extracts_namespace(self):
        result = parse_file(SIMPLE_CLASS, "Services/UserService.cs")
        assert result.namespace == "MyApp.Services"

    def test_extracts_using_directives(self):
        result = parse_file(SIMPLE_CLASS, "Services/UserService.cs")
        assert "System" in result.using_directives
        assert "System.Collections.Generic" in result.using_directives

    def test_extracts_class(self):
        result = parse_file(SIMPLE_CLASS, "Services/UserService.cs")
        classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
        assert len(classes) == 1
        assert classes[0].name == "UserService"
        assert classes[0].fq_name == "MyApp.Services.UserService"

    def test_extracts_class_modifiers(self):
        result = parse_file(SIMPLE_CLASS, "Services/UserService.cs")
        cls = next(s for s in result.symbols if s.kind == SymbolKind.CLASS)
        assert "public" in cls.modifiers

    def test_extracts_base_types(self):
        result = parse_file(SIMPLE_CLASS, "Services/UserService.cs")
        cls = next(s for s in result.symbols if s.kind == SymbolKind.CLASS)
        assert "IUserService" in cls.base_types

    def test_extracts_methods(self):
        result = parse_file(SIMPLE_CLASS, "Services/UserService.cs")
        methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
        method_names = {m.name for m in methods}
        assert "GetById" in method_names
        assert "Delete" in method_names
        assert "ComputeHash" in method_names

    def test_extracts_constructor(self):
        result = parse_file(SIMPLE_CLASS, "Services/UserService.cs")
        ctors = [s for s in result.symbols if s.kind == SymbolKind.CONSTRUCTOR]
        assert len(ctors) == 1
        assert ctors[0].fq_name == "MyApp.Services.UserService.UserService"

    def test_extracts_field(self):
        result = parse_file(SIMPLE_CLASS, "Services/UserService.cs")
        fields = [s for s in result.symbols if s.kind == SymbolKind.FIELD]
        assert len(fields) >= 1
        field_names = {f.name for f in fields}
        assert "_logger" in field_names

    def test_method_has_parameters(self):
        result = parse_file(SIMPLE_CLASS, "Services/UserService.cs")
        get_by_id = next(s for s in result.symbols if s.name == "GetById")
        assert len(get_by_id.parameters) == 1
        assert "int" in get_by_id.parameters[0]
        assert "id" in get_by_id.parameters[0]

    def test_method_has_return_type(self):
        result = parse_file(SIMPLE_CLASS, "Services/UserService.cs")
        get_by_id = next(s for s in result.symbols if s.name == "GetById")
        assert get_by_id.return_type == "User"

    def test_method_has_signature(self):
        result = parse_file(SIMPLE_CLASS, "Services/UserService.cs")
        get_by_id = next(s for s in result.symbols if s.name == "GetById")
        assert "GetById" in get_by_id.signature
        assert "int id" in get_by_id.signature

    def test_line_numbers(self):
        result = parse_file(SIMPLE_CLASS, "Services/UserService.cs")
        cls = next(s for s in result.symbols if s.kind == SymbolKind.CLASS)
        assert cls.start_line >= 1
        assert cls.end_line > cls.start_line

    def test_parent_fq_name(self):
        result = parse_file(SIMPLE_CLASS, "Services/UserService.cs")
        method = next(s for s in result.symbols if s.name == "GetById")
        assert method.parent_fq_name == "MyApp.Services.UserService"


class TestInterfaceAndEnum:
    """Tests for interface and enum extraction."""

    def test_extracts_interface(self):
        result = parse_file(INTERFACE_AND_ENUM, "Contracts/IUserService.cs")
        interfaces = [s for s in result.symbols if s.kind == SymbolKind.INTERFACE]
        assert len(interfaces) == 1
        assert interfaces[0].name == "IUserService"
        assert interfaces[0].fq_name == "MyApp.Contracts.IUserService"

    def test_extracts_enum(self):
        result = parse_file(INTERFACE_AND_ENUM, "Contracts/IUserService.cs")
        enums = [s for s in result.symbols if s.kind == SymbolKind.ENUM]
        assert len(enums) == 1
        assert enums[0].name == "UserRole"


class TestController:
    """Tests for ASP.NET controller parsing."""

    def test_extracts_controller_class(self):
        result = parse_file(CONTROLLER, "Controllers/UsersController.cs")
        cls = next(s for s in result.symbols if s.kind == SymbolKind.CLASS)
        assert cls.name == "UsersController"
        assert "ControllerBase" in cls.base_types

    def test_extracts_action_methods(self):
        result = parse_file(CONTROLLER, "Controllers/UsersController.cs")
        methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
        method_names = {m.name for m in methods}
        assert "Get" in method_names
        assert "Delete" in method_names


class TestNestedTypes:
    """Tests for nested class extraction."""

    def test_extracts_nested_class(self):
        result = parse_file(NESTED_CLASS, "Models/Order.cs")
        classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
        assert len(classes) == 2
        names = {c.name for c in classes}
        assert "Order" in names
        assert "OrderItem" in names

    def test_nested_class_fq_name(self):
        result = parse_file(NESTED_CLASS, "Models/Order.cs")
        item = next(s for s in result.symbols if s.name == "OrderItem")
        assert item.fq_name == "MyApp.Models.Order.OrderItem"
        assert item.parent_fq_name == "MyApp.Models.Order"

    def test_containment_edge(self):
        result = parse_file(NESTED_CLASS, "Models/Order.cs")
        contains = [e for e in result.edges if e.edge_type == EdgeType.CONTAINS]
        # Order contains OrderItem + CreateItem + properties
        parent_targets = {(e.source_fq_name, e.target_fq_name) for e in contains}
        assert ("MyApp.Models.Order", "MyApp.Models.Order.OrderItem") in parent_targets


class TestStructAndRecord:
    """Tests for struct and record extraction."""

    def test_extracts_struct(self):
        result = parse_file(STRUCT_AND_RECORD, "Models/Types.cs")
        structs = [s for s in result.symbols if s.kind == SymbolKind.STRUCT]
        assert len(structs) == 1
        assert structs[0].name == "Point"

    def test_extracts_record(self):
        result = parse_file(STRUCT_AND_RECORD, "Models/Types.cs")
        records = [s for s in result.symbols if s.kind == SymbolKind.RECORD]
        assert len(records) == 1
        assert records[0].name == "PersonRecord"


class TestEdgeExtraction:
    """Tests for call graph edge extraction."""

    def test_extracts_call_edges(self):
        result = parse_file(SIMPLE_CLASS, "Services/UserService.cs")
        calls = [e for e in result.edges if e.edge_type == EdgeType.CALLS]
        targets = {e.target_fq_name for e in calls}
        assert "LogInfo" in targets or "Log" in targets or len(calls) > 0

    def test_extracts_inheritance_edge(self):
        result = parse_file(SIMPLE_CLASS, "Services/UserService.cs")
        inherits = [
            e for e in result.edges if e.edge_type in (EdgeType.IMPLEMENTS, EdgeType.INHERITS)
        ]
        assert any(e.target_fq_name == "IUserService" for e in inherits)

    def test_extracts_import_edges(self):
        result = parse_file(SIMPLE_CLASS, "Services/UserService.cs")
        imports = [e for e in result.edges if e.edge_type == EdgeType.IMPORTS]
        targets = {e.target_fq_name for e in imports}
        assert "System" in targets
        assert "System.Collections.Generic" in targets

    def test_method_call_within_class(self):
        result = parse_file(MULTIPLE_METHODS_WITH_CALLS, "Logic/Calculator.cs")
        calls = [e for e in result.edges if e.edge_type == EdgeType.CALLS]
        # Multiply calls Add
        multiply_calls = [e for e in calls if e.source_fq_name == "MyApp.Logic.Calculator.Multiply"]
        assert any(e.target_fq_name == "Add" for e in multiply_calls)

    def test_object_creation_edge(self):
        result = parse_file(NESTED_CLASS, "Models/Order.cs")
        calls = [e for e in result.edges if e.edge_type == EdgeType.CALLS]
        # CreateItem creates OrderItem
        assert any(e.target_fq_name == "OrderItem" for e in calls)

    def test_call_edge_has_line_number(self):
        result = parse_file(MULTIPLE_METHODS_WITH_CALLS, "Logic/Calculator.cs")
        calls = [e for e in result.edges if e.edge_type == EdgeType.CALLS]
        for call in calls:
            assert call.line > 0
            assert call.file_path == "Logic/Calculator.cs"


class TestStaticMain:
    """Tests for Program/Main detection."""

    def test_extracts_program_class(self):
        result = parse_file(STATIC_MAIN, "Program.cs")
        classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
        assert any(c.name == "Program" for c in classes)

    def test_extracts_main_method(self):
        result = parse_file(STATIC_MAIN, "Program.cs")
        methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
        main = next((m for m in methods if m.name == "Main"), None)
        assert main is not None
        assert "static" in main.modifiers


class TestEdgeCases:
    """Tests for edge cases and robustness."""

    def test_empty_file(self):
        result = parse_file(b"", "Empty.cs")
        assert result.symbols == []
        assert result.edges == []

    def test_file_with_only_comments(self):
        result = parse_file(b"// This is a comment\n/* block */\n", "Comments.cs")
        assert result.symbols == []

    def test_file_with_only_using(self):
        result = parse_file(b"using System;\nusing System.Linq;\n", "Usings.cs")
        assert len(result.using_directives) == 2
        assert result.symbols == []

    def test_malformed_code_does_not_crash(self):
        # tree-sitter is error-tolerant; we should get partial results
        bad_code = b"namespace Foo { public class Bar { public void Baz( } }"
        result = parse_file(bad_code, "Bad.cs")
        # Should not raise; may extract partial symbols
        assert isinstance(result.symbols, list)

    def test_file_path_preserved(self):
        result = parse_file(SIMPLE_CLASS, "deep/path/to/UserService.cs")
        assert result.path == "deep/path/to/UserService.cs"
        for sym in result.symbols:
            assert sym.file_path == "deep/path/to/UserService.cs"
