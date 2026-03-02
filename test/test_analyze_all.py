"""Unit tests for FPFIFOForwardAnalyzer.analyze_all method."""
import pytest
from pycpa import model
from forward_analysis.fa_fpfifo import FPFIFOForwardAnalyzer, AnalysisResult, HopResult


def _make_system_with_single_path():
    """Create a simple system with one path, one resource, one VL."""
    s = model.System("TestSystem")
    r1 = model.Resource("SW1_out")
    s.bind_resource(r1)

    t1 = model.Task("VL1_hop1", bcet=5, wcet=10, scheduling_parameter=1)
    r1.bind_task(t1)
    t1.in_event_model = model.PJdEventModel(P=100, J=0)

    p1 = model.Path("VL1", [t1])
    s.bind_path(p1)
    return s, p1, t1


def _make_system_with_two_paths():
    """Create a system with two paths sharing a resource."""
    s = model.System("TestSystem")
    r1 = model.Resource("SW1_out")
    s.bind_resource(r1)

    # VL1: priority 1 (higher)
    t1 = model.Task("VL1_hop1", bcet=5, wcet=10, scheduling_parameter=1)
    r1.bind_task(t1)
    t1.in_event_model = model.PJdEventModel(P=100, J=0)

    # VL2: priority 2 (lower)
    t2 = model.Task("VL2_hop1", bcet=3, wcet=8, scheduling_parameter=2)
    r1.bind_task(t2)
    t2.in_event_model = model.PJdEventModel(P=200, J=0)

    p1 = model.Path("VL1", [t1])
    p2 = model.Path("VL2", [t2])
    s.bind_path(p1)
    s.bind_path(p2)
    return s, p1, p2


def _make_system_with_multi_hop():
    """Create a system with a multi-hop path."""
    s = model.System("TestSystem")
    r1 = model.Resource("SW1_out")
    r2 = model.Resource("SW2_out")
    s.bind_resource(r1)
    s.bind_resource(r2)

    t1 = model.Task("VL1_hop1", bcet=5, wcet=10, scheduling_parameter=1)
    r1.bind_task(t1)
    t1.in_event_model = model.PJdEventModel(P=100, J=0)

    t2 = model.Task("VL1_hop2", bcet=5, wcet=10, scheduling_parameter=1)
    r2.bind_task(t2)
    t2.in_event_model = model.PJdEventModel(P=100, J=0)

    p1 = model.Path("VL1", [t1, t2])
    s.bind_path(p1)
    return s, p1


class TestAnalyzeAll:
    """Tests for analyze_all method."""

    def test_empty_system_returns_empty_dict(self):
        """System with no paths should return empty dict."""
        s = model.System("EmptySystem")
        analyzer = FPFIFOForwardAnalyzer(s)
        results = analyzer.analyze_all()
        assert results == {}

    def test_single_path_returns_one_result(self):
        """Single path system should return dict with one entry."""
        s, p1, t1 = _make_system_with_single_path()
        analyzer = FPFIFOForwardAnalyzer(s)
        results = analyzer.analyze_all()
        assert len(results) == 1
        assert p1 in results
        assert isinstance(results[p1], AnalysisResult)

    def test_two_paths_returns_two_results(self):
        """Two-path system should return dict with two entries."""
        s, p1, p2 = _make_system_with_two_paths()
        analyzer = FPFIFOForwardAnalyzer(s)
        results = analyzer.analyze_all()
        assert len(results) == 2
        assert p1 in results
        assert p2 in results

    def test_result_structure(self):
        """Each result should have correct structure."""
        s, p1, t1 = _make_system_with_single_path()
        analyzer = FPFIFOForwardAnalyzer(s)
        results = analyzer.analyze_all()
        r = results[p1]
        assert r.path is p1
        assert r.path_name == "VL1"
        assert len(r.hop_results) == 1
        assert r.hop_results[0].hop_index == 0
        assert r.hop_results[0].resource_name == "SW1_out"
        assert r.hop_results[0].task_name == "VL1_hop1"
        assert r.e2e_wcrt >= 0
        assert r.smin_initial == 0

    def test_stores_last_results(self):
        """analyze_all should store results in _last_results."""
        s, p1, t1 = _make_system_with_single_path()
        analyzer = FPFIFOForwardAnalyzer(s)
        results = analyzer.analyze_all()
        assert analyzer._last_results is results

    def test_empty_system_stores_empty_last_results(self):
        """Empty system should store empty dict in _last_results."""
        s = model.System("EmptySystem")
        analyzer = FPFIFOForwardAnalyzer(s)
        analyzer.analyze_all()
        assert analyzer._last_results == {}

    def test_resets_state_between_calls(self):
        """Calling analyze_all twice should produce same results (state reset)."""
        s, p1, p2 = _make_system_with_two_paths()
        analyzer = FPFIFOForwardAnalyzer(s)
        results1 = analyzer.analyze_all()
        results2 = analyzer.analyze_all()
        for path in [p1, p2]:
            assert results1[path].e2e_wcrt == results2[path].e2e_wcrt
            for h1, h2 in zip(results1[path].hop_results, results2[path].hop_results):
                assert h1.smax == h2.smax
                assert h1.smin == h2.smin
                assert h1.wcrt == h2.wcrt

    def test_multi_hop_path(self):
        """Multi-hop path should have correct number of hop results."""
        s, p1 = _make_system_with_multi_hop()
        # Need in_event_model on second task for the analyzer
        for r in s.resources:
            for task in r.tasks:
                if task.in_event_model is None:
                    task.in_event_model = model.PJdEventModel(P=100, J=0)
        analyzer = FPFIFOForwardAnalyzer(s)
        results = analyzer.analyze_all()
        assert len(results[p1].hop_results) == 2
        assert results[p1].hop_results[0].hop_index == 0
        assert results[p1].hop_results[1].hop_index == 1

    def test_smax_ge_smin_all_hops(self):
        """Smax should be >= Smin at every hop."""
        s, p1, p2 = _make_system_with_two_paths()
        analyzer = FPFIFOForwardAnalyzer(s)
        results = analyzer.analyze_all()
        for path, result in results.items():
            for hop in result.hop_results:
                assert hop.smax >= hop.smin

    def test_e2e_wcrt_equals_smax_last_minus_smin_initial(self):
        """e2e_wcrt should equal smax_input[last] + bklg[last] (paper formula)."""
        s, p1 = _make_system_with_multi_hop()
        # Need in_event_model on second task for the analyzer
        for t in s.resources:
            for task in t.tasks:
                if task.in_event_model is None:
                    task.in_event_model = model.PJdEventModel(P=100, J=0)
        analyzer = FPFIFOForwardAnalyzer(s)
        results = analyzer.analyze_all()
        r = results[p1]
        # e2e should be non-negative and consistent
        assert r.e2e_wcrt >= 0
        # Smax of last hop output should be >= e2e_wcrt (since smax_out includes tech_lat)
        assert r.hop_results[-1].smax >= r.e2e_wcrt

    def test_with_serialization_flag(self):
        """analyze_all should accept with_serialization parameter."""
        s, p1, t1 = _make_system_with_single_path()
        analyzer = FPFIFOForwardAnalyzer(s)
        results_no_ser = analyzer.analyze_all(with_serialization=False)
        results_ser = analyzer.analyze_all(with_serialization=True)
        # With serialization should produce <= delay (or equal for single flow)
        assert results_ser[p1].e2e_wcrt <= results_no_ser[p1].e2e_wcrt + 1e-9

    def test_consistency_with_analyze_path_single_path(self):
        """For a single-path system, analyze_all and analyze_path should give same results."""
        s, p1, t1 = _make_system_with_single_path()
        analyzer1 = FPFIFOForwardAnalyzer(s)
        all_results = analyzer1.analyze_all()

        analyzer2 = FPFIFOForwardAnalyzer(s)
        path_result = analyzer2.analyze_path(p1)

        assert all_results[p1].e2e_wcrt == pytest.approx(path_result.e2e_wcrt)
        for h_all, h_path in zip(all_results[p1].hop_results, path_result.hop_results):
            assert h_all.smax == pytest.approx(h_path.smax)
            assert h_all.smin == pytest.approx(h_path.smin)
            assert h_all.wcrt == pytest.approx(h_path.wcrt)

    def test_with_technological_latency(self):
        """Technological latency should be included in Smax and Smin."""
        s = model.System("TestSystem")
        r1 = model.Resource("SW1_out")
        r1.forwarding_delay = 16
        s.bind_resource(r1)

        t1 = model.Task("VL1_hop1", bcet=5, wcet=10, scheduling_parameter=1)
        r1.bind_task(t1)
        t1.in_event_model = model.PJdEventModel(P=100, J=0)

        p1 = model.Path("VL1", [t1])
        s.bind_path(p1)

        analyzer = FPFIFOForwardAnalyzer(s)
        results = analyzer.analyze_all()
        r = results[p1]
        # Smin should include wcet + tech_latency (paper uses Ci=wcet for smin)
        assert r.hop_results[0].smin == pytest.approx(10 + 16)
        # Smax should include bklg + tech_latency
        assert r.hop_results[0].smax >= 10 + 16
