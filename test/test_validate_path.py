"""Unit tests for FPFIFOForwardAnalyzer._validate_path method."""
import pytest
from pycpa import model
from forward_analysis.fa_fpfifo import FPFIFOForwardAnalyzer  # noqa: direct import, analyzer.py not yet created


def _make_analyzer():
    """Create an analyzer instance without __init__ (not yet implemented)."""
    return object.__new__(FPFIFOForwardAnalyzer)


def _make_bound_task(name, wcet=10, bcet=5, scheduling_parameter=1, resource=None):
    """Create a Task bound to a Resource with valid defaults."""
    t = model.Task(name, bcet, wcet, scheduling_parameter)
    if resource is None:
        resource = model.Resource("R_default")
    resource.bind_task(t)
    return t


class TestValidatePath:
    """Tests for _validate_path input validation."""

    def test_valid_path(self):
        analyzer = _make_analyzer()
        r = model.Resource("R1")
        t1 = _make_bound_task("T1", resource=r)
        t1.in_event_model = model.PJdEventModel(P=100, J=0)
        t2 = _make_bound_task("T2", resource=r)
        path = model.Path("P1", [t1, t2])
        # Should not raise
        analyzer._validate_path(path)

    def test_task_not_bound_to_resource(self):
        analyzer = _make_analyzer()
        t1 = model.Task("T_unbound")
        t1.wcet = 10
        t1.bcet = 5
        t1.scheduling_parameter = 1
        t1.in_event_model = model.PJdEventModel(P=100, J=0)
        path = model.Path("P1", [t1])
        with pytest.raises(ValueError, match="Task 'T_unbound' is not bound to any Resource"):
            analyzer._validate_path(path)

    def test_first_task_missing_event_model(self):
        analyzer = _make_analyzer()
        r = model.Resource("R1")
        t1 = _make_bound_task("T_no_em", resource=r)
        # in_event_model is None by default
        path = model.Path("P1", [t1])
        with pytest.raises(ValueError, match="First task 'T_no_em' in path 'P1' has no in_event_model"):
            analyzer._validate_path(path)

    def test_task_wcet_zero(self):
        analyzer = _make_analyzer()
        r = model.Resource("R1")
        t1 = model.Task("T_zero_wcet")
        t1.scheduling_parameter = 1
        r.bind_task(t1)
        t1.in_event_model = model.PJdEventModel(P=100, J=0)
        # wcet defaults to 0
        path = model.Path("P1", [t1])
        with pytest.raises(ValueError, match=r"Task 'T_zero_wcet' has invalid wcet=0 \(must be > 0\)"):
            analyzer._validate_path(path)

    def test_task_missing_scheduling_parameter(self):
        analyzer = _make_analyzer()
        r = model.Resource("R1")
        t1 = model.Task("T_no_sp")
        t1.wcet = 10
        t1.bcet = 5
        r.bind_task(t1)
        t1.in_event_model = model.PJdEventModel(P=100, J=0)
        # No scheduling_parameter set
        path = model.Path("P1", [t1])
        with pytest.raises(ValueError, match="Task 'T_no_sp' has no scheduling_parameter"):
            analyzer._validate_path(path)

    def test_path_only_forwarding_tasks(self):
        analyzer = _make_analyzer()
        r = model.Resource("R1")
        ft = model.ForwardingTask("FT1", bcet=1, wcet=1)
        r.bind_task(ft)
        path = model.Path("P_fwd_only", [ft])
        with pytest.raises(ValueError, match="Path 'P_fwd_only' has no analyzable tasks"):
            analyzer._validate_path(path)

    def test_forwarding_task_skipped_for_wcet_and_sp_checks(self):
        """ForwardingTasks should be skipped for wcet/scheduling_parameter checks
        but NOT for Resource binding check."""
        analyzer = _make_analyzer()
        r = model.Resource("R1")
        ft = model.ForwardingTask("FT1", bcet=1, wcet=1)
        r.bind_task(ft)
        t1 = _make_bound_task("T1", resource=r)
        t1.in_event_model = model.PJdEventModel(P=100, J=0)
        path = model.Path("P1", [ft, t1])
        # Should not raise - ForwardingTask is skipped for validation
        analyzer._validate_path(path)

    def test_forwarding_task_not_skipped_for_resource_check(self):
        """ForwardingTask without Resource should still fail the Resource check."""
        analyzer = _make_analyzer()
        ft = model.ForwardingTask("FT_unbound", bcet=1, wcet=1)
        # Don't bind to resource
        ft.resource = None
        r = model.Resource("R1")
        t1 = _make_bound_task("T1", resource=r)
        t1.in_event_model = model.PJdEventModel(P=100, J=0)
        path = model.Path("P1", [ft, t1])
        with pytest.raises(ValueError, match="Task 'FT_unbound' is not bound to any Resource"):
            analyzer._validate_path(path)


class TestGetAnalysisTasks:
    """Tests for _get_analysis_tasks helper method."""

    def test_filters_out_forwarding_tasks(self):
        analyzer = _make_analyzer()
        r = model.Resource("R1")
        t1 = _make_bound_task("T1", resource=r)
        ft = model.ForwardingTask("FT1", bcet=1, wcet=1)
        r.bind_task(ft)
        t2 = _make_bound_task("T2", resource=r)
        path = model.Path("P1", [t1, ft, t2])
        result = analyzer._get_analysis_tasks(path)
        assert len(result) == 2
        assert result[0].name == "T1"
        assert result[1].name == "T2"

    def test_no_forwarding_tasks(self):
        analyzer = _make_analyzer()
        r = model.Resource("R1")
        t1 = _make_bound_task("T1", resource=r)
        t2 = _make_bound_task("T2", resource=r)
        path = model.Path("P1", [t1, t2])
        result = analyzer._get_analysis_tasks(path)
        assert len(result) == 2

    def test_all_forwarding_tasks(self):
        analyzer = _make_analyzer()
        r = model.Resource("R1")
        ft1 = model.ForwardingTask("FT1", bcet=1, wcet=1)
        r.bind_task(ft1)
        ft2 = model.ForwardingTask("FT2", bcet=1, wcet=1)
        r.bind_task(ft2)
        path = model.Path("P1", [ft1, ft2])
        result = analyzer._get_analysis_tasks(path)
        assert result == []

    def test_preserves_task_order(self):
        analyzer = _make_analyzer()
        r = model.Resource("R1")
        t1 = _make_bound_task("T_A", resource=r)
        ft = model.ForwardingTask("FT1", bcet=1, wcet=1)
        r.bind_task(ft)
        t2 = _make_bound_task("T_B", resource=r)
        t3 = _make_bound_task("T_C", resource=r)
        path = model.Path("P1", [t1, ft, t2, t3])
        result = analyzer._get_analysis_tasks(path)
        assert [t.name for t in result] == ["T_A", "T_B", "T_C"]


class TestGetTechnologicalLatency:
    """Tests for _get_technological_latency helper method."""

    def test_resource_with_forwarding_delay(self):
        analyzer = _make_analyzer()
        r = model.Resource("R1")
        r.forwarding_delay = 16
        assert analyzer._get_technological_latency(r) == 16

    def test_resource_without_forwarding_delay(self):
        analyzer = _make_analyzer()
        r = model.Resource("R1")
        # Standard Resource may not have forwarding_delay; remove if present
        if hasattr(r, 'forwarding_delay'):
            delattr(r, 'forwarding_delay')
        assert analyzer._get_technological_latency(r) == 0

    def test_forwarding_delay_zero(self):
        analyzer = _make_analyzer()
        r = model.Resource("R1")
        r.forwarding_delay = 0
        assert analyzer._get_technological_latency(r) == 0

    def test_forwarding_delay_float(self):
        analyzer = _make_analyzer()
        r = model.Resource("R1")
        r.forwarding_delay = 3.5
        assert analyzer._get_technological_latency(r) == 3.5
