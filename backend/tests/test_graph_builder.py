"""
Tests for the graph builder.

Covers: graph construction, callers/callees lookup, neighborhood expansion,
module building, fan-in/fan-out, and symbol filtering.
"""

import pytest

from app.analysis.csharp_parser import parse_file
from app.analysis.graph_builder import build_graph, CodeGraph
from app.analysis.models import EdgeType, SymbolKind


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SERVICE_CODE = b"""\
using System;

namespace MyApp.Services
{
    public class OrderService
    {
        public void CreateOrder(int userId)
        {
            ValidateUser(userId);
            var order = new Order();
            NotifyUser(userId);
        }

        private void ValidateUser(int id)
        {
            Console.WriteLine("Validating");
        }

        private void NotifyUser(int id)
        {
            Console.WriteLine("Notifying");
        }
    }
}
"""

CALLER_CODE = b"""\
namespace MyApp.Controllers
{
    public class OrderController : ControllerBase
    {
        private readonly OrderService _service;

        public void Post(int userId)
        {
            _service.CreateOrder(userId);
        }
    }
}
"""

MULTI_NAMESPACE = b"""\
namespace MyApp.Data
{
    public class Repository
    {
        public object Find(int id) { return null; }
    }
}
"""


def _build_test_graph() -> CodeGraph:
    """Build a graph from multiple related files."""
    analyses = [
        parse_file(SERVICE_CODE, "Services/OrderService.cs"),
        parse_file(CALLER_CODE, "Controllers/OrderController.cs"),
        parse_file(MULTI_NAMESPACE, "Data/Repository.cs"),
    ]
    return build_graph(analyses)


class TestGraphConstruction:
    """Tests for building the code graph."""

    def test_graph_has_symbols(self):
        graph = _build_test_graph()
        assert len(graph.symbols) > 0

    def test_graph_has_edges(self):
        graph = _build_test_graph()
        assert len(graph.edges) > 0

    def test_graph_has_modules(self):
        graph = _build_test_graph()
        assert len(graph.modules) > 0
        module_names = set(graph.modules.keys())
        assert "MyApp.Services" in module_names
        assert "MyApp.Controllers" in module_names
        assert "MyApp.Data" in module_names

    def test_symbols_indexed_by_fq_name(self):
        graph = _build_test_graph()
        assert "MyApp.Services.OrderService" in graph.symbols
        assert "MyApp.Controllers.OrderController" in graph.symbols
        assert "MyApp.Data.Repository" in graph.symbols

    def test_files_indexed(self):
        graph = _build_test_graph()
        assert "Services/OrderService.cs" in graph.files
        assert "Controllers/OrderController.cs" in graph.files


class TestCallGraph:
    """Tests for call graph navigation."""

    def test_callees_of_method(self):
        graph = _build_test_graph()
        callees = graph.get_callees("MyApp.Services.OrderService.CreateOrder")
        # CreateOrder calls ValidateUser, creates Order, calls NotifyUser
        assert len(callees) >= 2

    def test_callers_of_method(self):
        graph = _build_test_graph()
        # CreateOrder is called by OrderController.Post
        callers = graph.get_callers("CreateOrder")
        assert len(callers) >= 1

    def test_children_of_class(self):
        graph = _build_test_graph()
        children = graph.get_children("MyApp.Services.OrderService")
        assert len(children) >= 3  # CreateOrder, ValidateUser, NotifyUser

    def test_fan_in(self):
        graph = _build_test_graph()
        # ValidateUser is called from CreateOrder
        assert graph.fan_in("ValidateUser") >= 1

    def test_fan_out(self):
        graph = _build_test_graph()
        assert graph.fan_out("MyApp.Services.OrderService.CreateOrder") >= 2


class TestNeighborhood:
    """Tests for BFS neighborhood expansion."""

    def test_neighborhood_depth_0(self):
        graph = _build_test_graph()
        hood = graph.get_neighborhood("MyApp.Services.OrderService.CreateOrder", depth=0)
        assert hood == {"MyApp.Services.OrderService.CreateOrder"}

    def test_neighborhood_depth_1(self):
        graph = _build_test_graph()
        hood = graph.get_neighborhood("MyApp.Services.OrderService.CreateOrder", depth=1)
        assert "MyApp.Services.OrderService.CreateOrder" in hood
        # Should include direct callees
        assert len(hood) > 1

    def test_neighborhood_depth_2_expands_further(self):
        graph = _build_test_graph()
        hood1 = graph.get_neighborhood("MyApp.Services.OrderService.CreateOrder", depth=1)
        hood2 = graph.get_neighborhood("MyApp.Services.OrderService.CreateOrder", depth=2)
        assert len(hood2) >= len(hood1)


class TestModules:
    """Tests for module (namespace) graph."""

    def test_module_file_count(self):
        graph = _build_test_graph()
        svc_module = graph.modules.get("MyApp.Services")
        assert svc_module is not None
        assert svc_module.file_count == 1

    def test_module_has_files(self):
        graph = _build_test_graph()
        svc_module = graph.modules["MyApp.Services"]
        assert "Services/OrderService.cs" in svc_module.files

    def test_module_dependencies(self):
        graph = _build_test_graph()
        # Controllers module uses System (via using)
        ctrl_module = graph.modules.get("MyApp.Controllers")
        if ctrl_module:
            # May have dependencies based on using directives
            assert isinstance(ctrl_module.dependencies, list)


class TestSymbolFiltering:
    """Tests for symbol lookup by kind and file."""

    def test_get_symbols_by_kind_class(self):
        graph = _build_test_graph()
        classes = graph.get_symbols_by_kind(SymbolKind.CLASS)
        names = {c.name for c in classes}
        assert "OrderService" in names
        assert "OrderController" in names
        assert "Repository" in names

    def test_get_symbols_by_kind_method(self):
        graph = _build_test_graph()
        methods = graph.get_symbols_by_kind(SymbolKind.METHOD)
        assert len(methods) > 0

    def test_get_symbols_in_file(self):
        graph = _build_test_graph()
        syms = graph.get_symbols_in_file("Services/OrderService.cs")
        assert len(syms) >= 4  # class + 3 methods minimum


class TestEmptyGraph:
    """Tests for edge cases."""

    def test_empty_graph(self):
        graph = build_graph([])
        assert len(graph.symbols) == 0
        assert len(graph.edges) == 0
        assert len(graph.modules) == 0

    def test_single_empty_file(self):
        analysis = parse_file(b"", "Empty.cs")
        graph = build_graph([analysis])
        assert len(graph.symbols) == 0
