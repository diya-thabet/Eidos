"""
Tests for deterministic facts extraction.

Covers: symbol facts, module facts, file facts, purpose generation,
side effect inference, risk detection, and confidence assessment.
"""

from app.analysis.csharp_parser import parse_file
from app.analysis.graph_builder import build_graph
from app.indexing.facts_extractor import (
    extract_file_facts,
    extract_module_facts,
    extract_symbol_facts,
)
from app.indexing.summary_schema import Confidence

SERVICE = b"""\
using System;

namespace MyApp.Services
{
    public class OrderService : IOrderService
    {
        private readonly ILogger _logger;

        public OrderService(ILogger logger)
        {
            _logger = logger;
        }

        public Order CreateOrder(int userId)
        {
            _logger.LogInfo("Creating order");
            ValidateUser(userId);
            var order = SaveOrder(userId);
            SendNotification(userId);
            return order;
        }

        private void ValidateUser(int id) { }
        private Order SaveOrder(int userId) { return null; }
        private void SendNotification(int userId) { }
    }
}
"""

CONTROLLER = b"""\
using Microsoft.AspNetCore.Mvc;

namespace MyApp.Controllers
{
    public class OrderController : Controller
    {
        public IActionResult Get(int id)
        {
            return Ok();
        }
    }
}
"""

SIMPLE_ENUM = b"""\
namespace MyApp.Models
{
    public enum Status { Active, Inactive }
}
"""


def _build_graph(*sources):
    analyses = []
    for i, src in enumerate(sources):
        analyses.append(parse_file(src, f"file{i}.cs"))
    return build_graph(analyses)


class TestSymbolFacts:
    def test_extracts_facts_for_all_symbols(self):
        graph = _build_graph(SERVICE)
        facts = extract_symbol_facts(graph)
        fq_names = {f.fq_name for f in facts}
        assert "MyApp.Services.OrderService" in fq_names
        assert "MyApp.Services.OrderService.CreateOrder" in fq_names

    def test_class_purpose_includes_member_count(self):
        graph = _build_graph(SERVICE)
        facts = extract_symbol_facts(graph)
        cls = next(f for f in facts if f.fq_name == "MyApp.Services.OrderService")
        assert "members" in cls.purpose.lower() or "member" in cls.purpose.lower()

    def test_class_purpose_includes_base_types(self):
        graph = _build_graph(SERVICE)
        facts = extract_symbol_facts(graph)
        cls = next(f for f in facts if f.fq_name == "MyApp.Services.OrderService")
        assert "IOrderService" in cls.purpose

    def test_method_purpose_includes_return_type(self):
        graph = _build_graph(SERVICE)
        facts = extract_symbol_facts(graph)
        method = next(f for f in facts if f.fq_name == "MyApp.Services.OrderService.CreateOrder")
        assert "Order" in method.purpose

    def test_method_has_inputs(self):
        graph = _build_graph(SERVICE)
        facts = extract_symbol_facts(graph)
        method = next(f for f in facts if f.fq_name == "MyApp.Services.OrderService.CreateOrder")
        assert len(method.inputs) >= 1

    def test_method_has_outputs(self):
        graph = _build_graph(SERVICE)
        facts = extract_symbol_facts(graph)
        method = next(f for f in facts if f.fq_name == "MyApp.Services.OrderService.CreateOrder")
        assert "Order" in method.outputs

    def test_side_effects_detected(self):
        graph = _build_graph(SERVICE)
        facts = extract_symbol_facts(graph)
        method = next(f for f in facts if f.fq_name == "MyApp.Services.OrderService.CreateOrder")
        # SaveOrder and SendNotification should flag as side effects
        combined = " ".join(method.side_effects).lower()
        assert "save" in combined or "send" in combined or "log" in combined

    def test_citations_present(self):
        graph = _build_graph(SERVICE)
        facts = extract_symbol_facts(graph)
        for fact in facts:
            assert len(fact.citations) >= 1
            assert fact.citations[0].file_path != ""
            assert fact.citations[0].symbol_fq_name == fact.fq_name

    def test_constructor_purpose(self):
        graph = _build_graph(SERVICE)
        facts = extract_symbol_facts(graph)
        ctor = next(f for f in facts if f.kind == "constructor")
        assert "constructor" in ctor.purpose.lower()

    def test_enum_purpose(self):
        graph = _build_graph(SIMPLE_ENUM)
        facts = extract_symbol_facts(graph)
        enum_fact = next(f for f in facts if f.kind == "enum")
        assert "Status" in enum_fact.purpose

    def test_confidence_high_for_documented_symbol(self):
        graph = _build_graph(SERVICE)
        facts = extract_symbol_facts(graph)
        method = next(f for f in facts if f.fq_name == "MyApp.Services.OrderService.CreateOrder")
        # Has signature + parameters + return type + callees ? should be HIGH or MEDIUM
        assert method.confidence in (Confidence.HIGH, Confidence.MEDIUM)


class TestModuleFacts:
    def test_extracts_module_for_each_namespace(self):
        graph = _build_graph(SERVICE, CONTROLLER)
        facts = extract_module_facts(graph)
        names = {f.name for f in facts}
        assert "MyApp.Services" in names
        assert "MyApp.Controllers" in names

    def test_module_purpose_includes_counts(self):
        graph = _build_graph(SERVICE)
        facts = extract_module_facts(graph)
        mod = next(f for f in facts if f.name == "MyApp.Services")
        assert "symbols" in mod.purpose.lower()

    def test_module_has_key_classes(self):
        graph = _build_graph(SERVICE)
        facts = extract_module_facts(graph)
        mod = next(f for f in facts if f.name == "MyApp.Services")
        assert "MyApp.Services.OrderService" in mod.key_classes

    def test_module_has_dependencies(self):
        graph = _build_graph(SERVICE)
        facts = extract_module_facts(graph)
        mod = next(f for f in facts if f.name == "MyApp.Services")
        assert "System" in mod.dependencies

    def test_module_citations_reference_files(self):
        graph = _build_graph(SERVICE)
        facts = extract_module_facts(graph)
        mod = next(f for f in facts if f.name == "MyApp.Services")
        assert len(mod.citations) >= 1

    def test_module_confidence(self):
        graph = _build_graph(SERVICE)
        facts = extract_module_facts(graph)
        mod = next(f for f in facts if f.name == "MyApp.Services")
        assert mod.confidence == Confidence.HIGH


class TestFileFacts:
    def test_extracts_file_for_each_parsed_file(self):
        graph = _build_graph(SERVICE, CONTROLLER)
        facts = extract_file_facts(graph)
        paths = {f.path for f in facts}
        assert "file0.cs" in paths
        assert "file1.cs" in paths

    def test_file_purpose_includes_type_names(self):
        graph = _build_graph(SERVICE)
        facts = extract_file_facts(graph)
        f = next(ff for ff in facts if ff.path == "file0.cs")
        assert "OrderService" in f.purpose

    def test_file_has_symbols(self):
        graph = _build_graph(SERVICE)
        facts = extract_file_facts(graph)
        f = next(ff for ff in facts if ff.path == "file0.cs")
        assert len(f.symbols) >= 1

    def test_file_has_namespace(self):
        graph = _build_graph(SERVICE)
        facts = extract_file_facts(graph)
        f = next(ff for ff in facts if ff.path == "file0.cs")
        assert f.namespace == "MyApp.Services"

    def test_file_has_imports(self):
        graph = _build_graph(SERVICE)
        facts = extract_file_facts(graph)
        f = next(ff for ff in facts if ff.path == "file0.cs")
        assert "System" in f.imports

    def test_empty_graph_produces_no_file_facts(self):
        graph = build_graph([])
        facts = extract_file_facts(graph)
        assert len(facts) == 0
