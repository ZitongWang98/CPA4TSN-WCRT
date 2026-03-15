#!/usr/bin/env python3
"""Cross-validation: FusionScheduler vs dedicated schedulers.

When configured with a single mechanism, FusionScheduler MUST produce
identical results to the corresponding dedicated scheduler.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pycpa import model, analysis
from pycpa.schedulers_fusion import FusionScheduler
from pycpa.schedulers_cqfp import CQFPScheduler
from pycpa.schedulers_ats import ATSScheduler
from pycpa.schedulers import TASScheduler

PASS = 0
FAIL = 0

def check(name, fusion_val, ref_val, tol=1e-6):
    global PASS, FAIL
    ok = abs(fusion_val - ref_val) < tol
    status = "OK" if ok else f"MISMATCH Fusion={fusion_val:.6f} Ref={ref_val:.6f}"
    if not ok:
        FAIL += 1
        print(f"  FAIL {name}: {status}")
    else:
        PASS += 1
    return ok


def run_pair(label, build_fn):
    """Run same scenario with FusionScheduler and reference scheduler."""
    print(f"[{label}]")
    f_results, r_results, f_tasks, r_tasks = build_fn()
    all_ok = True
    for (ft, rt) in zip(f_tasks, r_tasks):
        ok = check(ft.name, f_results[ft].wcrt, r_results[rt].wcrt)
        if not ok:
            all_ok = False
    if all_ok:
        print(f"  PASSED ({len(f_tasks)} flows)")
    return all_ok


# ======================================================================
# CQFP cross-validation
# ======================================================================

def cqfp_ne_only():
    """N+E only: two priorities, no CQF."""
    tasks_f, tasks_r = [], []
    for sched_cls in [FusionScheduler, CQFPScheduler]:
        s = model.System()
        r = model.TSN_Resource('R', scheduler=sched_cls(), linkspeed=1e9)
        r.priority_mechanism_map = {6: None, 4: None, 2: None}
        r.is_express_by_priority = {6: True, 4: True, 2: True}
        ts = []
        for p, w, per in [(6, 10, 200), (4, 20, 300), (2, 50, 500)]:
            t = model.Task(f'NE_p{p}', wcet=w, bcet=w, scheduling_parameter=p)
            t.in_event_model = model.PJdEventModel(P=per, J=0)
            r.bind_task(t)
            ts.append(t)
        s.bind_resource(r)
        res = analysis.analyze_system(s)
        if sched_cls == FusionScheduler:
            f_res, tasks_f = res, ts
        else:
            r_res, tasks_r = res, ts
    return f_res, r_res, tasks_f, tasks_r


def cqfp_ne_np():
    """N+E and N+P mixed."""
    tasks_f, tasks_r = [], []
    for sched_cls in [FusionScheduler, CQFPScheduler]:
        s = model.System()
        r = model.TSN_Resource('R', scheduler=sched_cls(), linkspeed=1e9)
        r.priority_mechanism_map = {6: None, 4: None, 2: None}
        r.is_express_by_priority = {6: True, 4: True, 2: False}
        ts = []
        for p, w, per, pay in [(6, 10, 200, None), (4, 20, 300, None), (2, 80, 1000, 400)]:
            kw = dict(wcet=w, bcet=w, scheduling_parameter=p)
            if pay: kw['payload'] = pay
            t = model.Task(f'p{p}', **kw)
            t.in_event_model = model.PJdEventModel(P=per, J=0)
            r.bind_task(t)
            ts.append(t)
        s.bind_resource(r)
        res = analysis.analyze_system(s)
        if sched_cls == FusionScheduler:
            f_res, tasks_f = res, ts
        else:
            r_res, tasks_r = res, ts
    return f_res, r_res, tasks_f, tasks_r


def cqfp_ce_only():
    """C+E only."""
    tasks_f, tasks_r = [], []
    for sched_cls in [FusionScheduler, CQFPScheduler]:
        s = model.System()
        r = model.TSN_Resource('R', scheduler=sched_cls(), linkspeed=1e9)
        r.priority_mechanism_map = {(5, 4): 'CQF'}
        r.cqf_cycle_time_by_pair = {(5, 4): 500}
        r.is_express_by_priority = {5: True, 4: True}
        ts = []
        for p, w, per in [(5, 12, 500), (5, 8, 500)]:
            t = model.Task(f'CE_{w}', wcet=w, bcet=w, scheduling_parameter=p)
            t.in_event_model = model.PJdEventModel(P=per, J=0)
            r.bind_task(t)
            ts.append(t)
        s.bind_resource(r)
        res = analysis.analyze_system(s)
        if sched_cls == FusionScheduler:
            f_res, tasks_f = res, ts
        else:
            r_res, tasks_r = res, ts
    return f_res, r_res, tasks_f, tasks_r


def cqfp_cp_only():
    """C+P only."""
    tasks_f, tasks_r = [], []
    for sched_cls in [FusionScheduler, CQFPScheduler]:
        s = model.System()
        r = model.TSN_Resource('R', scheduler=sched_cls(), linkspeed=1e9)
        r.priority_mechanism_map = {(1, 0): 'CQF'}
        r.cqf_cycle_time_by_pair = {(1, 0): 1000}
        r.is_express_by_priority = {1: False, 0: False}
        ts = []
        t = model.Task('CP1', wcet=100, bcet=100, scheduling_parameter=1, payload=500)
        t.in_event_model = model.PJdEventModel(P=2000, J=0)
        r.bind_task(t)
        ts.append(t)
        s.bind_resource(r)
        res = analysis.analyze_system(s)
        if sched_cls == FusionScheduler:
            f_res, tasks_f = res, ts
        else:
            r_res, tasks_r = res, ts
    return f_res, r_res, tasks_f, tasks_r


def cqfp_full_4class():
    """All 4 CQFP classes: N+E, C+E, C+P, N+P."""
    tasks_f, tasks_r = [], []
    for sched_cls in [FusionScheduler, CQFPScheduler]:
        s = model.System()
        r = model.TSN_Resource('R', scheduler=sched_cls(), linkspeed=1e9)
        r.priority_mechanism_map = {6: None, (5, 4): 'CQF', 2: None, (1, 0): 'CQF'}
        r.cqf_cycle_time_by_pair = {(5, 4): 500, (1, 0): 500}
        r.is_express_by_priority = {6: True, 5: True, 4: True, 2: False, 1: False, 0: False}
        ts = []
        configs = [
            (6, 10, 200, None),   # N+E
            (5, 12, 500, None),   # C+E
            (2, 80, 1000, 400),   # N+P
            (1, 60, 1000, 300),   # C+P
        ]
        for p, w, per, pay in configs:
            kw = dict(wcet=w, bcet=w, scheduling_parameter=p)
            if pay: kw['payload'] = pay
            t = model.Task(f'p{p}_w{w}', **kw)
            t.in_event_model = model.PJdEventModel(P=per, J=0)
            r.bind_task(t)
            ts.append(t)
        s.bind_resource(r)
        res = analysis.analyze_system(s)
        if sched_cls == FusionScheduler:
            f_res, tasks_f = res, ts
        else:
            r_res, tasks_r = res, ts
    return f_res, r_res, tasks_f, tasks_r


def cqfp_ne_with_hp_ce():
    """N+E with higher-priority C+E interferer."""
    tasks_f, tasks_r = [], []
    for sched_cls in [FusionScheduler, CQFPScheduler]:
        s = model.System()
        r = model.TSN_Resource('R', scheduler=sched_cls(), linkspeed=1e9)
        r.priority_mechanism_map = {(7, 6): 'CQF', 4: None}
        r.cqf_cycle_time_by_pair = {(7, 6): 500}
        r.is_express_by_priority = {7: True, 6: True, 4: True}
        ts = []
        t_hp = model.Task('CE_hp', wcet=15, bcet=15, scheduling_parameter=7)
        t_hp.in_event_model = model.PJdEventModel(P=500, J=0)
        r.bind_task(t_hp)
        ts.append(t_hp)
        t = model.Task('NE_lp', wcet=30, bcet=30, scheduling_parameter=4)
        t.in_event_model = model.PJdEventModel(P=400, J=0)
        r.bind_task(t)
        ts.append(t)
        s.bind_resource(r)
        res = analysis.analyze_system(s)
        if sched_cls == FusionScheduler:
            f_res, tasks_f = res, ts
        else:
            r_res, tasks_r = res, ts
    return f_res, r_res, tasks_f, tasks_r


def cqfp_np_with_hp_ne_and_lp_cp():
    """N+P with HP N+E and LP C+P."""
    tasks_f, tasks_r = [], []
    for sched_cls in [FusionScheduler, CQFPScheduler]:
        s = model.System()
        r = model.TSN_Resource('R', scheduler=sched_cls(), linkspeed=1e9)
        r.priority_mechanism_map = {6: None, 3: None, (1, 0): 'CQF'}
        r.cqf_cycle_time_by_pair = {(1, 0): 1000}
        r.is_express_by_priority = {6: True, 3: False, 1: False, 0: False}
        ts = []
        t_hp = model.Task('NE_hp', wcet=15, bcet=15, scheduling_parameter=6)
        t_hp.in_event_model = model.PJdEventModel(P=200, J=0)
        r.bind_task(t_hp)
        ts.append(t_hp)
        t = model.Task('NP_mid', wcet=60, bcet=60, scheduling_parameter=3, payload=300)
        t.in_event_model = model.PJdEventModel(P=1000, J=0)
        r.bind_task(t)
        ts.append(t)
        t_lp = model.Task('CP_lp', wcet=80, bcet=80, scheduling_parameter=1, payload=400)
        t_lp.in_event_model = model.PJdEventModel(P=2000, J=0)
        r.bind_task(t_lp)
        ts.append(t_lp)
        s.bind_resource(r)
        res = analysis.analyze_system(s)
        if sched_cls == FusionScheduler:
            f_res, tasks_f = res, ts
        else:
            r_res, tasks_r = res, ts
    return f_res, r_res, tasks_f, tasks_r


# ======================================================================
# ATS cross-validation
# ======================================================================

def ats_single():
    """Single ATS flow."""
    tasks_f, tasks_r = [], []
    for sched_cls in [FusionScheduler, ATSScheduler]:
        s = model.System()
        r = model.TSN_Resource('R', scheduler=sched_cls(), linkspeed=1e9)
        r.priority_mechanism_map = {4: 'ATS'}
        r.is_express_by_priority = {4: True}
        ts = []
        t = model.Task('ATS1', wcet=12, bcet=12, scheduling_parameter=4,
                        CIR=100e6, CBS=12000)
        t.in_event_model = model.PJdEventModel(P=500, J=0)
        r.bind_task(t)
        ts.append(t)
        s.bind_resource(r)
        res = analysis.analyze_system(s)
        if sched_cls == FusionScheduler:
            f_res, tasks_f = res, ts
        else:
            r_res, tasks_r = res, ts
    return f_res, r_res, tasks_f, tasks_r


def ats_with_hp_nats():
    """ATS flow with HP NATS interferer."""
    tasks_f, tasks_r = [], []
    for sched_cls in [FusionScheduler, ATSScheduler]:
        s = model.System()
        r = model.TSN_Resource('R', scheduler=sched_cls(), linkspeed=1e9)
        r.priority_mechanism_map = {6: None, 4: 'ATS'}
        r.is_express_by_priority = {6: True, 4: True}
        ts = []
        t_hp = model.Task('NATS_hp', wcet=20, bcet=20, scheduling_parameter=6)
        t_hp.in_event_model = model.PJdEventModel(P=200, J=0)
        r.bind_task(t_hp)
        ts.append(t_hp)
        t = model.Task('ATS1', wcet=12, bcet=12, scheduling_parameter=4,
                        CIR=100e6, CBS=12000)
        t.in_event_model = model.PJdEventModel(P=500, J=0)
        r.bind_task(t)
        ts.append(t)
        s.bind_resource(r)
        res = analysis.analyze_system(s)
        if sched_cls == FusionScheduler:
            f_res, tasks_f = res, ts
        else:
            r_res, tasks_r = res, ts
    return f_res, r_res, tasks_f, tasks_r


def ats_with_lp_nats():
    """ATS flow with LP NATS interferer."""
    tasks_f, tasks_r = [], []
    for sched_cls in [FusionScheduler, ATSScheduler]:
        s = model.System()
        r = model.TSN_Resource('R', scheduler=sched_cls(), linkspeed=1e9)
        r.priority_mechanism_map = {6: 'ATS', 3: None}
        r.is_express_by_priority = {6: True, 3: True}
        ts = []
        t = model.Task('ATS1', wcet=12, bcet=12, scheduling_parameter=6,
                        CIR=100e6, CBS=12000)
        t.in_event_model = model.PJdEventModel(P=500, J=0)
        r.bind_task(t)
        ts.append(t)
        t_lp = model.Task('NATS_lp', wcet=50, bcet=50, scheduling_parameter=3)
        t_lp.in_event_model = model.PJdEventModel(P=1000, J=0)
        r.bind_task(t_lp)
        ts.append(t_lp)
        s.bind_resource(r)
        res = analysis.analyze_system(s)
        if sched_cls == FusionScheduler:
            f_res, tasks_f = res, ts
        else:
            r_res, tasks_r = res, ts
    return f_res, r_res, tasks_f, tasks_r


def ats_two_ats_same_prio():
    """Two ATS flows at same priority, different src_port."""
    tasks_f, tasks_r = [], []
    for sched_cls in [FusionScheduler, ATSScheduler]:
        s = model.System()
        r = model.TSN_Resource('R', scheduler=sched_cls(), linkspeed=1e9)
        r.priority_mechanism_map = {4: 'ATS'}
        r.is_express_by_priority = {4: True}
        ts = []
        t1 = model.Task('ATS_a', wcet=12, bcet=12, scheduling_parameter=4,
                         CIR=100e6, CBS=12000, src_port='portA')
        t1.in_event_model = model.PJdEventModel(P=500, J=0)
        r.bind_task(t1)
        ts.append(t1)
        t2 = model.Task('ATS_b', wcet=10, bcet=10, scheduling_parameter=4,
                         CIR=80e6, CBS=10000, src_port='portB')
        t2.in_event_model = model.PJdEventModel(P=400, J=0)
        r.bind_task(t2)
        ts.append(t2)
        s.bind_resource(r)
        res = analysis.analyze_system(s)
        if sched_cls == FusionScheduler:
            f_res, tasks_f = res, ts
        else:
            r_res, tasks_r = res, ts
    return f_res, r_res, tasks_f, tasks_r


def ats_mixed_ats_nats():
    """Mixed ATS and NATS at different priorities."""
    tasks_f, tasks_r = [], []
    for sched_cls in [FusionScheduler, ATSScheduler]:
        s = model.System()
        r = model.TSN_Resource('R', scheduler=sched_cls(), linkspeed=1e9)
        r.priority_mechanism_map = {6: None, 4: 'ATS', 2: None}
        r.is_express_by_priority = {6: True, 4: True, 2: True}
        ts = []
        t_hp = model.Task('NATS_hp', wcet=15, bcet=15, scheduling_parameter=6)
        t_hp.in_event_model = model.PJdEventModel(P=200, J=0)
        r.bind_task(t_hp)
        ts.append(t_hp)
        t = model.Task('ATS_mid', wcet=12, bcet=12, scheduling_parameter=4,
                        CIR=100e6, CBS=12000)
        t.in_event_model = model.PJdEventModel(P=500, J=0)
        r.bind_task(t)
        ts.append(t)
        t_lp = model.Task('NATS_lp', wcet=40, bcet=40, scheduling_parameter=2)
        t_lp.in_event_model = model.PJdEventModel(P=800, J=0)
        r.bind_task(t_lp)
        ts.append(t_lp)
        s.bind_resource(r)
        res = analysis.analyze_system(s)
        if sched_cls == FusionScheduler:
            f_res, tasks_f = res, ts
        else:
            r_res, tasks_r = res, ts
    return f_res, r_res, tasks_f, tasks_r


def ats_hp_ats_interferer():
    """NATS flow with HP ATS interferer (token-limited)."""
    tasks_f, tasks_r = [], []
    for sched_cls in [FusionScheduler, ATSScheduler]:
        s = model.System()
        r = model.TSN_Resource('R', scheduler=sched_cls(), linkspeed=1e9)
        r.priority_mechanism_map = {6: 'ATS', 3: None}
        r.is_express_by_priority = {6: True, 3: True}
        ts = []
        t_hp = model.Task('ATS_hp', wcet=12, bcet=12, scheduling_parameter=6,
                           CIR=50e6, CBS=12000)
        t_hp.in_event_model = model.PJdEventModel(P=100, J=0)
        r.bind_task(t_hp)
        ts.append(t_hp)
        t = model.Task('NATS_lp', wcet=40, bcet=40, scheduling_parameter=3)
        t.in_event_model = model.PJdEventModel(P=500, J=0)
        r.bind_task(t)
        ts.append(t)
        s.bind_resource(r)
        res = analysis.analyze_system(s)
        if sched_cls == FusionScheduler:
            f_res, tasks_f = res, ts
        else:
            r_res, tasks_r = res, ts
    return f_res, r_res, tasks_f, tasks_r


def ats_hpb_at_eligible():
    """ATS flow with HP NATS: w̃ starts at 0, HP must still contribute 1 frame.

    Tests the eta_plus_closed fix for ATS HPB iteration.
    ATS: prio=4, wcet=12, P=500, CIR=50M, CBS=6000 -> eT=120us
    HP:  prio=6, wcet=8, P=200 (NATS express)
    LPB=0, SPB=0 -> w̃ initial=0, but HP arrives at eligible time.
    Expected: w̃=8, w=120+8=128, b_plus=140
    """
    tasks_f, tasks_r = [], []
    for sched_cls in [FusionScheduler, ATSScheduler]:
        s = model.System()
        r = model.TSN_Resource('R', scheduler=sched_cls(), linkspeed=1e9)
        r.priority_mechanism_map = {6: None, 4: 'ATS'}
        r.is_express_by_priority = {6: True, 4: True}
        ts = []
        t_hp = model.Task('HP', wcet=8, bcet=8, scheduling_parameter=6)
        t_hp.in_event_model = model.PJdEventModel(P=200, J=0)
        r.bind_task(t_hp)
        ts.append(t_hp)
        t = model.Task('ATS1', wcet=12, bcet=12, scheduling_parameter=4,
                        CIR=50e6, CBS=6000)
        t.in_event_model = model.PJdEventModel(P=500, J=0)
        r.bind_task(t)
        ts.append(t)
        s.bind_resource(r)
        res = analysis.analyze_system(s)
        if sched_cls == FusionScheduler:
            f_res, tasks_f = res, ts
        else:
            r_res, tasks_r = res, ts
    return f_res, r_res, tasks_f, tasks_r


# ======================================================================
# TAS cross-validation
# ======================================================================

def tas_single_st():
    """Single ST flow."""
    tasks_f, tasks_r = [], []
    for sched_cls in [FusionScheduler, TASScheduler]:
        s = model.System()
        r = model.TSN_Resource('R', scheduler=sched_cls(), linkspeed=1e9)
        r.priority_mechanism_map = {7: 'TAS'}
        r.tas_cycle_time = 1000
        r.tas_window_time_by_priority = {7: 200}
        ts = []
        t = model.Task('ST1', wcet=10, bcet=10, scheduling_parameter=7)
        t.in_event_model = model.PJdEventModel(P=1000, J=0)
        r.bind_task(t)
        ts.append(t)
        s.bind_resource(r)
        res = analysis.analyze_system(s)
        if sched_cls == FusionScheduler:
            f_res, tasks_f = res, ts
        else:
            r_res, tasks_r = res, ts
    return f_res, r_res, tasks_f, tasks_r


def tas_two_st_same_prio():
    """Two ST flows same priority."""
    tasks_f, tasks_r = [], []
    for sched_cls in [FusionScheduler, TASScheduler]:
        s = model.System()
        r = model.TSN_Resource('R', scheduler=sched_cls(), linkspeed=1e9)
        r.priority_mechanism_map = {7: 'TAS'}
        r.tas_cycle_time = 1000
        r.tas_window_time_by_priority = {7: 200}
        ts = []
        for w in [10, 15, 8]:
            t = model.Task(f'ST_{w}', wcet=w, bcet=w, scheduling_parameter=7)
            t.in_event_model = model.PJdEventModel(P=1000, J=0)
            r.bind_task(t)
            ts.append(t)
        s.bind_resource(r)
        res = analysis.analyze_system(s)
        if sched_cls == FusionScheduler:
            f_res, tasks_f = res, ts
        else:
            r_res, tasks_r = res, ts
    return f_res, r_res, tasks_f, tasks_r


def tas_st_only():
    """ST flow only (no NST) — must match TASScheduler exactly."""
    tasks_f, tasks_r = [], []
    for sched_cls in [FusionScheduler, TASScheduler]:
        s = model.System()
        r = model.TSN_Resource('R', scheduler=sched_cls(), linkspeed=1e9)
        r.priority_mechanism_map = {7: 'TAS'}
        r.tas_cycle_time = 500
        r.tas_window_time_by_priority = {7: 100}
        ts = []
        t1 = model.Task('ST1', wcet=10, bcet=10, scheduling_parameter=7)
        t1.in_event_model = model.PJdEventModel(P=500, J=0)
        r.bind_task(t1)
        ts.append(t1)
        t2 = model.Task('ST2', wcet=20, bcet=20, scheduling_parameter=7)
        t2.in_event_model = model.PJdEventModel(P=500, J=0)
        r.bind_task(t2)
        ts.append(t2)
        s.bind_resource(r)
        res = analysis.analyze_system(s)
        if sched_cls == FusionScheduler:
            f_res, tasks_f = res, ts
        else:
            r_res, tasks_r = res, ts
    return f_res, r_res, tasks_f, tasks_r


# ======================================================================
# Main
# ======================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("CQFP Cross-Validation")
    print("=" * 60)
    run_pair("CQFP-1: N+E only (3 prios)", cqfp_ne_only)
    run_pair("CQFP-2: N+E + N+P mixed", cqfp_ne_np)
    run_pair("CQFP-3: C+E only", cqfp_ce_only)
    run_pair("CQFP-4: C+P only", cqfp_cp_only)
    run_pair("CQFP-5: Full 4-class (N+E,C+E,N+P,C+P)", cqfp_full_4class)
    run_pair("CQFP-6: N+E with HP C+E", cqfp_ne_with_hp_ce)
    run_pair("CQFP-7: N+P with HP N+E and LP C+P", cqfp_np_with_hp_ne_and_lp_cp)

    print()
    print("=" * 60)
    print("ATS Cross-Validation")
    print("=" * 60)
    run_pair("ATS-1: Single ATS", ats_single)
    run_pair("ATS-2: ATS + HP NATS", ats_with_hp_nats)
    run_pair("ATS-3: ATS + LP NATS", ats_with_lp_nats)
    run_pair("ATS-4: Two ATS same prio diff port", ats_two_ats_same_prio)
    run_pair("ATS-5: Mixed ATS+NATS 3 prios", ats_mixed_ats_nats)
    run_pair("ATS-6: NATS with HP ATS (token-limited)", ats_hp_ats_interferer)
    run_pair("ATS-7: ATS HPB at eligible time (w̃=0 boundary)", ats_hpb_at_eligible)

    print()
    print("=" * 60)
    print("TAS Cross-Validation")
    print("=" * 60)
    run_pair("TAS-1: Single ST", tas_single_st)
    run_pair("TAS-2: Three ST same prio", tas_two_st_same_prio)
    run_pair("TAS-3: Two ST tight window", tas_st_only)

    print()
    print("=" * 60)
    total = PASS + FAIL
    print(f"Results: {PASS}/{total} PASSED, {FAIL}/{total} FAILED")
    print("=" * 60)
    sys.exit(1 if FAIL > 0 else 0)
