#!/usr/bin/env python3
"""Basic tests for FusionScheduler.

Verifies that the unified fusion scheduler produces correct results
for each flow type (ST, ATS+E, C+E, C+P, NC+E, NC+P) on a single
resource with all mechanisms active.
"""
from __future__ import print_function, division
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pycpa import model, analysis
from pycpa.schedulers_fusion import FusionScheduler


def make_fusion_resource(name="FusionPort"):
    """Create a TSN_Resource with TAS+ATS+CQF+FP configured.

    Priority layout (thesis recommended):
        7: TAS (ST, Express)
        6: ATS (Express)
        5,4: CQF pair (Express)
        3: NC (Express)
        2: NC (Preemptable)
        1,0: CQF pair (Preemptable)
    """
    r = model.TSN_Resource(name, scheduler=FusionScheduler(),
                           linkspeed=1e9)
    r.priority_mechanism_map = {
        7: 'TAS',
        6: 'ATS',
        (5, 4): 'CQF',
        3: None,  # NC (no special mechanism)
        2: None,  # NC
        (1, 0): 'CQF',
    }
    r.tas_cycle_time = 500  # 500 us
    r.tas_window_time_by_priority = {7: 100}  # 100 us window
    r.cqf_cycle_time_by_pair = {(5, 4): 500, (1, 0): 1000}
    r.is_express_by_priority = {
        7: True, 6: True, 5: True, 4: True,
        3: True,
        2: False, 1: False, 0: False,
    }
    return r


def test_st_flow():
    """Test ST (TAS) flow analysis."""
    s = model.System()
    r = make_fusion_resource()
    s.bind_resource(r)

    t1 = model.Task("ST_1", wcet=10, bcet=10, scheduling_parameter=7)
    t1.in_event_model = model.PJdEventModel(P=1000, J=0)
    r.bind_task(t1)

    t2 = model.Task("ST_2", wcet=8, bcet=8, scheduling_parameter=7)
    t2.in_event_model = model.PJdEventModel(P=1000, J=0)
    r.bind_task(t2)

    results = analysis.analyze_system(s)
    wcrt = results[t1].wcrt
    print(f"  ST flow WCRT: {wcrt:.3f} us")
    assert wcrt > 0, "ST WCRT should be positive"
    return True


def test_ats_flow():
    """Test ATS+E flow analysis."""
    s = model.System()
    r = make_fusion_resource()
    s.bind_resource(r)

    # ATS flow at prio 6
    t1 = model.Task("ATS_1", wcet=12, bcet=12, scheduling_parameter=6,
                     CIR=100e6, CBS=12000)
    t1.in_event_model = model.PJdEventModel(P=500, J=0)
    r.bind_task(t1)

    # ST flow at prio 7 (HP interferer)
    t_st = model.Task("ST_hp", wcet=10, bcet=10, scheduling_parameter=7)
    t_st.in_event_model = model.PJdEventModel(P=1000, J=0)
    r.bind_task(t_st)

    results = analysis.analyze_system(s)
    wcrt = results[t1].wcrt
    print(f"  ATS+E flow WCRT: {wcrt:.3f} us")
    assert wcrt > 0, "ATS WCRT should be positive"
    return True


def test_cqf_express_flow():
    """Test C+E flow analysis."""
    s = model.System()
    r = make_fusion_resource()
    s.bind_resource(r)

    # C+E flow at prio 5
    t1 = model.Task("CE_1", wcet=12, bcet=12, scheduling_parameter=5)
    t1.in_event_model = model.PJdEventModel(P=500, J=0)
    r.bind_task(t1)

    # ST flow at prio 7
    t_st = model.Task("ST_hp", wcet=10, bcet=10, scheduling_parameter=7)
    t_st.in_event_model = model.PJdEventModel(P=1000, J=0)
    r.bind_task(t_st)

    results = analysis.analyze_system(s)
    wcrt = results[t1].wcrt
    print(f"  C+E flow WCRT: {wcrt:.3f} us")
    assert wcrt > 0, "C+E WCRT should be positive"
    return True


def test_cqf_preemptable_flow():
    """Test C+P flow analysis."""
    s = model.System()
    r = make_fusion_resource()
    s.bind_resource(r)

    # C+P flow at prio 1
    t1 = model.Task("CP_1", wcet=100, bcet=100, scheduling_parameter=1,
                     payload=500)
    t1.in_event_model = model.PJdEventModel(P=2000, J=0)
    r.bind_task(t1)

    # NC+E flow at prio 3 (HP express interferer)
    t_hp = model.Task("NCE_hp", wcet=12, bcet=12, scheduling_parameter=3)
    t_hp.in_event_model = model.PJdEventModel(P=500, J=0)
    r.bind_task(t_hp)

    results = analysis.analyze_system(s)
    wcrt = results[t1].wcrt
    print(f"  C+P flow WCRT: {wcrt:.3f} us")
    assert wcrt > 0, "C+P WCRT should be positive"
    return True


def test_nc_express_flow():
    """Test NC+E flow analysis."""
    s = model.System()
    r = make_fusion_resource()
    s.bind_resource(r)

    # NC+E flow at prio 3
    t1 = model.Task("NCE_1", wcet=12, bcet=12, scheduling_parameter=3)
    t1.in_event_model = model.PJdEventModel(P=500, J=0)
    r.bind_task(t1)

    # ST flow at prio 7
    t_st = model.Task("ST_hp", wcet=10, bcet=10, scheduling_parameter=7)
    t_st.in_event_model = model.PJdEventModel(P=1000, J=0)
    r.bind_task(t_st)

    # NC+P flow at prio 2 (LP preemptable)
    t_lp = model.Task("NCP_lp", wcet=100, bcet=100, scheduling_parameter=2,
                       payload=500)
    t_lp.in_event_model = model.PJdEventModel(P=2000, J=0)
    r.bind_task(t_lp)

    results = analysis.analyze_system(s)
    wcrt = results[t1].wcrt
    print(f"  NC+E flow WCRT: {wcrt:.3f} us")
    assert wcrt > 0, "NC+E WCRT should be positive"
    return True


def test_nc_preemptable_flow():
    """Test NC+P flow analysis."""
    s = model.System()
    r = make_fusion_resource()
    s.bind_resource(r)

    # NC+P flow at prio 2
    t1 = model.Task("NCP_1", wcet=80, bcet=80, scheduling_parameter=2,
                     payload=400)
    t1.in_event_model = model.PJdEventModel(P=2000, J=0)
    r.bind_task(t1)

    # NC+E flow at prio 3 (HP express)
    t_hp = model.Task("NCE_hp", wcet=12, bcet=12, scheduling_parameter=3)
    t_hp.in_event_model = model.PJdEventModel(P=500, J=0)
    r.bind_task(t_hp)

    results = analysis.analyze_system(s)
    wcrt = results[t1].wcrt
    print(f"  NC+P flow WCRT: {wcrt:.3f} us")
    assert wcrt > 0, "NC+P WCRT should be positive"
    return True


def test_full_fusion():
    """Test with all 6 flow types on one resource."""
    s = model.System()
    r = make_fusion_resource()
    s.bind_resource(r)

    # ST (prio 7)
    t_st = model.Task("ST", wcet=10, bcet=10, scheduling_parameter=7)
    t_st.in_event_model = model.PJdEventModel(P=1000, J=0)
    r.bind_task(t_st)

    # ATS+E (prio 6)
    t_ats = model.Task("ATS_E", wcet=12, bcet=12, scheduling_parameter=6,
                        CIR=100e6, CBS=12000)
    t_ats.in_event_model = model.PJdEventModel(P=500, J=0)
    r.bind_task(t_ats)

    # C+E (prio 5)
    t_ce = model.Task("C_E", wcet=12, bcet=12, scheduling_parameter=5)
    t_ce.in_event_model = model.PJdEventModel(P=500, J=0)
    r.bind_task(t_ce)

    # NC+E (prio 3)
    t_nce = model.Task("NC_E", wcet=12, bcet=12, scheduling_parameter=3)
    t_nce.in_event_model = model.PJdEventModel(P=500, J=0)
    r.bind_task(t_nce)

    # NC+P (prio 2)
    t_ncp = model.Task("NC_P", wcet=80, bcet=80, scheduling_parameter=2,
                        payload=400)
    t_ncp.in_event_model = model.PJdEventModel(P=2000, J=0)
    r.bind_task(t_ncp)

    # C+P (prio 1)
    t_cp = model.Task("C_P", wcet=100, bcet=100, scheduling_parameter=1,
                       payload=500)
    t_cp.in_event_model = model.PJdEventModel(P=2000, J=0)
    r.bind_task(t_cp)

    results = analysis.analyze_system(s)

    print("  Full fusion results:")
    for t in [t_st, t_ats, t_ce, t_nce, t_ncp, t_cp]:
        mech = {7: 'ST', 6: 'ATS+E', 5: 'C+E', 3: 'NC+E', 2: 'NC+P', 1: 'C+P'}
        label = mech.get(t.scheduling_parameter, '?')
        print(f"    {t.name:8s} ({label:5s}): WCRT = {results[t].wcrt:.3f} us")

    # Basic sanity: all WCRTs should be positive
    for t in [t_st, t_ats, t_ce, t_nce, t_ncp, t_cp]:
        assert results[t].wcrt > 0, f"{t.name} WCRT should be positive"
    return True


def test_st_guard_band_max_wcet():
    """ST guard band must use max(C+_j) across all flows in the same TAS window.

    Two ST flows with different wcet in the same window.  The guard band
    (and thus gate_closed_duration) must be based on the larger wcet.
    """
    s = model.System()
    r = model.TSN_Resource("R", scheduler=FusionScheduler(), linkspeed=1e9)
    r.priority_mechanism_map = {7: 'TAS'}
    r.tas_cycle_time = 500
    r.tas_window_time_by_priority = {7: 100}
    r.cqf_cycle_time_by_pair = {}
    r.is_express_by_priority = {7: True}
    s.bind_resource(r)

    t_small = model.Task("ST_small", wcet=5, bcet=5, scheduling_parameter=7)
    t_small.in_event_model = model.PJdEventModel(P=2000, J=0)
    r.bind_task(t_small)

    t_big = model.Task("ST_big", wcet=40, bcet=40, scheduling_parameter=7)
    t_big.in_event_model = model.PJdEventModel(P=2000, J=0)
    r.bind_task(t_big)

    results = analysis.analyze_system(s)
    wcrt = results[t_small].wcrt
    print(f"  ST_small WCRT: {wcrt:.3f} us")
    # max_st_wcet=40, gate_closed=440, eff_window=60
    # spb=40, schb=ceil(45/60)*440=440, w=480, WCRT=480+5=485
    assert abs(wcrt - 485.0) < 0.01, f"Expected 485.0, got {wcrt}"
    return True


def test_ats_express_hpb_cqf_interferer():
    """HPB for ATS+E must apply cqf_eta_window to CQF HP interferers.

    Non-recommended config: CQF at prio 6 > ATS at prio 4.
    Without cqf_eta_window, CQF interferer count is underestimated → unsafe.
    """
    s = model.System()
    r = model.TSN_Resource("R", scheduler=FusionScheduler(), linkspeed=1e9)
    r.priority_mechanism_map = {7: 'TAS', (6, 5): 'CQF', 4: 'ATS', 3: None}
    r.tas_cycle_time = 500
    r.tas_window_time_by_priority = {7: 50}
    r.cqf_cycle_time_by_pair = {(6, 5): 500}
    r.is_express_by_priority = {7: True, 6: True, 5: True, 4: True, 3: True}
    s.bind_resource(r)

    t_st = model.Task("ST", wcet=10, bcet=10, scheduling_parameter=7)
    t_st.in_event_model = model.PJdEventModel(P=2000, J=0)
    r.bind_task(t_st)

    t_cqf = model.Task("CQF_E", wcet=8, bcet=8, scheduling_parameter=6)
    t_cqf.in_event_model = model.PJdEventModel(P=200, J=0)
    r.bind_task(t_cqf)

    t_ats = model.Task("ATS_E", wcet=12, bcet=12, scheduling_parameter=4,
                        CIR=100e6, CBS=12000, src_port='A')
    t_ats.in_event_model = model.PJdEventModel(P=1000, J=0)
    r.bind_task(t_ats)

    results = analysis.analyze_system(s)
    wcrt = results[t_ats].wcrt
    print(f"  ATS_E WCRT: {wcrt:.3f} us")
    # Before fix: 78 (unsafe). After fix: 94 (correct).
    assert abs(wcrt - 94.0) < 0.01, f"Expected 94.0, got {wcrt}"
    return True


def test_ats_preemptable_spb_eq341():
    """ATS+P SPB must use Eq.(3.41): same-port max, not eta*C+.

    Two same-port ATS+P flows.  Eq.(3.41) takes max(C+) for same-port
    instead of eta*C+, giving a tighter (less conservative) SPB.
    """
    s = model.System()
    r = model.TSN_Resource("R", scheduler=FusionScheduler(), linkspeed=1e9)
    r.priority_mechanism_map = {7: 'TAS', 4: 'ATS'}
    r.tas_cycle_time = 500
    r.tas_window_time_by_priority = {7: 50}
    r.cqf_cycle_time_by_pair = {}
    r.is_express_by_priority = {7: True, 4: False}
    s.bind_resource(r)

    t_st = model.Task("ST", wcet=10, bcet=10, scheduling_parameter=7)
    t_st.in_event_model = model.PJdEventModel(P=500, J=0)
    r.bind_task(t_st)

    t1 = model.Task("ATS_P1", wcet=20, bcet=20, scheduling_parameter=4,
                     CIR=100e6, CBS=20000, src_port='A', payload=400)
    t1.in_event_model = model.PJdEventModel(P=500, J=0)
    r.bind_task(t1)

    t2 = model.Task("ATS_P2", wcet=30, bcet=30, scheduling_parameter=4,
                     CIR=100e6, CBS=30000, src_port='A', payload=600)
    t2.in_event_model = model.PJdEventModel(P=500, J=0)
    r.bind_task(t2)

    results = analysis.analyze_system(s)
    wcrt = results[t1].wcrt
    print(f"  ATS_P1 WCRT: {wcrt:.3f} us")
    assert abs(wcrt - 101.144) < 0.01, f"Expected 101.144, got {wcrt}"
    return True


def test_skd_case1_ats_token():
    """SKD Case1 must apply ATS token limit for express interferers.

    Without the token limit, Case1 overestimates express frame count,
    making Case1 > Case2 so min() picks Case2.  With the fix, Case1
    is tighter and min() picks Case1, yielding a smaller (more precise) WCRT.
    """
    s = model.System()
    r = model.TSN_Resource("R", scheduler=FusionScheduler(), linkspeed=1e9)
    r.priority_mechanism_map = {7: 'TAS', 6: 'ATS', 2: None}
    r.tas_cycle_time = 500
    r.tas_window_time_by_priority = {7: 50}
    r.cqf_cycle_time_by_pair = {}
    r.is_express_by_priority = {7: True, 6: True, 2: False}
    s.bind_resource(r)

    t_st = model.Task("ST", wcet=10, bcet=10, scheduling_parameter=7)
    t_st.in_event_model = model.PJdEventModel(P=500, J=0)
    r.bind_task(t_st)

    # ATS+E: high arrival rate but tight token bucket → n_token << eta
    t_ats = model.Task("ATS_E", wcet=12, bcet=12, scheduling_parameter=6,
                        CIR=50e6, CBS=6000, src_port='A')
    t_ats.in_event_model = model.PJdEventModel(P=100, J=0)
    r.bind_task(t_ats)

    t_ncp = model.Task("NC_P", wcet=100, bcet=100, scheduling_parameter=2,
                        payload=800)
    t_ncp.in_event_model = model.PJdEventModel(P=5000, J=0)
    r.bind_task(t_ncp)

    results = analysis.analyze_system(s)
    wcrt = results[t_ncp].wcrt
    print(f"  NC_P WCRT: {wcrt:.3f} us")
    assert abs(wcrt - 174.192) < 0.01, f"Expected 174.192, got {wcrt}"
    return True


if __name__ == '__main__':
    tests = [
        ("ST flow", test_st_flow),
        ("ATS+E flow", test_ats_flow),
        ("C+E flow", test_cqf_express_flow),
        ("C+P flow", test_cqf_preemptable_flow),
        ("NC+E flow", test_nc_express_flow),
        ("NC+P flow", test_nc_preemptable_flow),
        ("Full fusion", test_full_fusion),
        ("ST guard band max wcet", test_st_guard_band_max_wcet),
        ("ATS+P SPB Eq.3.41", test_ats_preemptable_spb_eq341),
        ("ATS+E HPB CQF interferer", test_ats_express_hpb_cqf_interferer),
        ("SKD Case1 ATS token", test_skd_case1_ats_token),
    ]

    passed = 0
    failed = 0
    for name, test_fn in tests:
        try:
            print(f"[{name}]")
            test_fn()
            print(f"  PASSED\n")
            passed += 1
        except Exception as e:
            print(f"  FAILED: {e}\n")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"Results: {passed} PASSED, {failed} FAILED")
    sys.exit(1 if failed > 0 else 0)
