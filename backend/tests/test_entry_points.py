"""
Tests for entry point detection.

Covers: ASP.NET controllers, Main methods, Startup classes,
background workers, and controller action methods.
"""

import pytest

from app.analysis.csharp_parser import parse_file
from app.analysis.entry_points import detect_entry_points
from app.analysis.graph_builder import build_graph


CONTROLLER = b"""\
using Microsoft.AspNetCore.Mvc;

namespace MyApp.Controllers
{
    public class UsersController : Controller
    {
        public IActionResult Index()
        {
            return View();
        }

        public IActionResult Details(int id)
        {
            return View();
        }

        private void HelperMethod() { }
    }
}
"""

PROGRAM_WITH_MAIN = b"""\
namespace MyApp
{
    public class Program
    {
        public static void Main(string[] args)
        {
            CreateHostBuilder(args).Build().Run();
        }

        public static IHostBuilder CreateHostBuilder(string[] args)
        {
            return Host.CreateDefaultBuilder(args);
        }
    }
}
"""

STARTUP = b"""\
namespace MyApp
{
    public class Startup
    {
        public void ConfigureServices(IServiceCollection services) { }
        public void Configure(IApplicationBuilder app) { }
    }
}
"""

WORKER = b"""\
namespace MyApp.Workers
{
    public class EmailWorker : BackgroundService
    {
        protected override Task ExecuteAsync(CancellationToken ct)
        {
            return Task.CompletedTask;
        }
    }

    public class CleanupService : IHostedService
    {
        public Task StartAsync(CancellationToken ct) { return Task.CompletedTask; }
        public Task StopAsync(CancellationToken ct) { return Task.CompletedTask; }
    }
}
"""

NO_ENTRY_POINTS = b"""\
namespace MyApp.Utils
{
    public static class StringHelper
    {
        public static string Trim(string input) { return input.Trim(); }
    }
}
"""


class TestControllerDetection:
    def test_detects_controller(self):
        graph = build_graph([parse_file(CONTROLLER, "Controllers/UsersController.cs")])
        entries = detect_entry_points(graph)
        controllers = [e for e in entries if e.kind == "controller"]
        assert len(controllers) == 1
        assert controllers[0].symbol_fq_name == "MyApp.Controllers.UsersController"

    def test_controller_route(self):
        graph = build_graph([parse_file(CONTROLLER, "Controllers/UsersController.cs")])
        entries = detect_entry_points(graph)
        ctrl = next(e for e in entries if e.kind == "controller")
        assert ctrl.route == "/users"

    def test_detects_action_methods(self):
        graph = build_graph([parse_file(CONTROLLER, "Controllers/UsersController.cs")])
        entries = detect_entry_points(graph)
        actions = [e for e in entries if e.kind == "controller_action"]
        action_names = {e.symbol_fq_name.split(".")[-1] for e in actions}
        assert "Index" in action_names
        assert "Details" in action_names
        # Private helper should NOT be an action
        assert "HelperMethod" not in action_names

    def test_action_routes(self):
        graph = build_graph([parse_file(CONTROLLER, "Controllers/UsersController.cs")])
        entries = detect_entry_points(graph)
        actions = [e for e in entries if e.kind == "controller_action"]
        routes = {e.route for e in actions}
        assert "/users/Index" in routes
        assert "/users/Details" in routes


class TestMainDetection:
    def test_detects_main_method(self):
        graph = build_graph([parse_file(PROGRAM_WITH_MAIN, "Program.cs")])
        entries = detect_entry_points(graph)
        mains = [e for e in entries if e.kind == "main"]
        assert len(mains) == 1
        assert "Main" in mains[0].symbol_fq_name

    def test_detects_program_as_startup(self):
        graph = build_graph([parse_file(PROGRAM_WITH_MAIN, "Program.cs")])
        entries = detect_entry_points(graph)
        startups = [e for e in entries if e.kind == "startup"]
        assert len(startups) == 1
        assert "Program" in startups[0].symbol_fq_name


class TestStartupDetection:
    def test_detects_startup_class(self):
        graph = build_graph([parse_file(STARTUP, "Startup.cs")])
        entries = detect_entry_points(graph)
        startups = [e for e in entries if e.kind == "startup"]
        assert len(startups) == 1
        assert "Startup" in startups[0].symbol_fq_name


class TestWorkerDetection:
    def test_detects_background_service(self):
        graph = build_graph([parse_file(WORKER, "Workers/Workers.cs")])
        entries = detect_entry_points(graph)
        workers = [e for e in entries if e.kind == "worker"]
        names = {e.symbol_fq_name for e in workers}
        assert "MyApp.Workers.EmailWorker" in names

    def test_detects_hosted_service(self):
        graph = build_graph([parse_file(WORKER, "Workers/Workers.cs")])
        entries = detect_entry_points(graph)
        workers = [e for e in entries if e.kind == "worker"]
        names = {e.symbol_fq_name for e in workers}
        assert "MyApp.Workers.CleanupService" in names


class TestNoEntryPoints:
    def test_no_entry_points_in_utility(self):
        graph = build_graph([parse_file(NO_ENTRY_POINTS, "Utils/StringHelper.cs")])
        entries = detect_entry_points(graph)
        assert len(entries) == 0


class TestMultipleFileEntryPoints:
    def test_combined_entry_points(self):
        analyses = [
            parse_file(CONTROLLER, "Controllers/UsersController.cs"),
            parse_file(PROGRAM_WITH_MAIN, "Program.cs"),
            parse_file(STARTUP, "Startup.cs"),
            parse_file(WORKER, "Workers/Workers.cs"),
        ]
        graph = build_graph(analyses)
        entries = detect_entry_points(graph)
        kinds = {e.kind for e in entries}
        assert "controller" in kinds
        assert "main" in kinds
        assert "startup" in kinds
        assert "worker" in kinds

    def test_entry_points_sorted(self):
        analyses = [
            parse_file(CONTROLLER, "Controllers/UsersController.cs"),
            parse_file(PROGRAM_WITH_MAIN, "Program.cs"),
            parse_file(WORKER, "Workers/Workers.cs"),
        ]
        graph = build_graph(analyses)
        entries = detect_entry_points(graph)
        # Should be sorted by (kind, fq_name)
        kinds = [e.kind for e in entries]
        assert kinds == sorted(kinds)
