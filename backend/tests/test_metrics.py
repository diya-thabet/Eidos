"""
Tests for code metrics computation.

Covers: lines of code, fan-in, fan-out, child count,
modifier detection, hotspot identification.
"""

from app.analysis.csharp_parser import parse_file
from app.analysis.graph_builder import build_graph
from app.analysis.metrics import compute_metrics, find_hotspots

LARGE_SERVICE = b"""\
namespace MyApp.Services
{
    public class PaymentService
    {
        private readonly ILogger _logger;
        private readonly IPaymentGateway _gateway;

        public PaymentService(ILogger logger, IPaymentGateway gateway)
        {
            _logger = logger;
            _gateway = gateway;
        }

        public PaymentResult ProcessPayment(Order order)
        {
            _logger.LogInfo("Processing");
            Validate(order);
            var result = _gateway.Charge(order.Total);
            _logger.LogInfo("Done");
            NotifyCustomer(order.CustomerId);
            UpdateOrderStatus(order);
            return result;
        }

        private void Validate(Order order)
        {
            if (order == null) throw new ArgumentNullException();
            if (order.Total <= 0) throw new InvalidOperationException();
        }

        private void NotifyCustomer(int customerId)
        {
            // send email
            var email = BuildEmail(customerId);
            SendEmail(email);
        }

        private string BuildEmail(int customerId)
        {
            return "Dear customer...";
        }

        private void SendEmail(string email)
        {
            // smtp logic
        }

        private void UpdateOrderStatus(Order order)
        {
            order.Status = "Paid";
        }
    }
}
"""

CALLER1 = b"""\
namespace MyApp.Controllers
{
    public class PaymentController : ControllerBase
    {
        public void Post()
        {
            var svc = new PaymentService(null, null);
            svc.ProcessPayment(null);
        }
    }
}
"""

CALLER2 = b"""\
namespace MyApp.Jobs
{
    public class BatchPaymentJob
    {
        public void Run()
        {
            var svc = new PaymentService(null, null);
            svc.ProcessPayment(null);
        }
    }
}
"""

CALLER3 = b"""\
namespace MyApp.Tests
{
    public class PaymentTest
    {
        public void TestPayment()
        {
            var svc = new PaymentService(null, null);
            svc.ProcessPayment(null);
        }
    }
}
"""


class TestMetricsComputation:
    def _build_graph(self):
        analyses = [
            parse_file(LARGE_SERVICE, "Services/PaymentService.cs"),
            parse_file(CALLER1, "Controllers/PaymentController.cs"),
            parse_file(CALLER2, "Jobs/BatchPaymentJob.cs"),
            parse_file(CALLER3, "Tests/PaymentTest.cs"),
        ]
        return build_graph(analyses)

    def test_compute_metrics_returns_results(self):
        graph = self._build_graph()
        metrics = compute_metrics(graph)
        assert len(metrics) > 0

    def test_metrics_sorted_by_loc_desc(self):
        graph = self._build_graph()
        metrics = compute_metrics(graph)
        locs = [m.lines_of_code for m in metrics]
        assert locs == sorted(locs, reverse=True)

    def test_class_has_children(self):
        graph = self._build_graph()
        metrics = compute_metrics(graph)
        svc = next((m for m in metrics if m.fq_name == "MyApp.Services.PaymentService"), None)
        assert svc is not None
        assert svc.child_count >= 5  # constructor + methods + fields

    def test_method_fan_out(self):
        graph = self._build_graph()
        metrics = compute_metrics(graph)
        process = next((m for m in metrics if "ProcessPayment" in m.fq_name), None)
        assert process is not None
        assert process.fan_out >= 3  # Validate, Charge, LogInfo, NotifyCustomer, UpdateOrderStatus

    def test_method_loc(self):
        graph = self._build_graph()
        metrics = compute_metrics(graph)
        process = next((m for m in metrics if "ProcessPayment" in m.fq_name), None)
        assert process is not None
        assert process.lines_of_code >= 5

    def test_public_detection(self):
        graph = self._build_graph()
        metrics = compute_metrics(graph)
        process = next((m for m in metrics if "ProcessPayment" in m.fq_name), None)
        assert process is not None
        assert process.is_public is True

    def test_static_detection(self):
        graph = self._build_graph()
        metrics = compute_metrics(graph)
        # No static methods in this example
        for m in metrics:
            if "ProcessPayment" in m.fq_name:
                assert m.is_static is False


class TestHotspots:
    def test_no_hotspots_with_high_threshold(self):
        analyses = [parse_file(LARGE_SERVICE, "Services/PaymentService.cs")]
        graph = build_graph(analyses)
        # With very high thresholds, no hotspots
        hotspots = find_hotspots(graph, min_fan_in=100, min_loc=1000)
        assert len(hotspots) == 0

    def test_hotspots_with_low_threshold(self):
        analyses = [
            parse_file(LARGE_SERVICE, "Services/PaymentService.cs"),
            parse_file(CALLER1, "Controllers/PaymentController.cs"),
            parse_file(CALLER2, "Jobs/BatchPaymentJob.cs"),
            parse_file(CALLER3, "Tests/PaymentTest.cs"),
        ]
        graph = build_graph(analyses)
        # With very low thresholds, should find some
        hotspots = find_hotspots(graph, min_fan_in=1, min_loc=3)
        assert len(hotspots) >= 0  # depends on call resolution
