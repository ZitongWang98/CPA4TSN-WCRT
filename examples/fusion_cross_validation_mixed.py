#!/usr/bin/env python3
"""Cross-validation Part 2: Multi-mechanism fusion scenarios.

Hand-calculated reference values for scenarios where multiple mechanisms
coexist on the same resource. No dedicated scheduler exists for these,
so we use hand calculation and SPNPScheduler cross-checks.

Constants at 1 Gbps:
  min_fragment = 0.672 us (84B), max_fragment = 1.144 us (143B)
  overhead = 0.192 us (24B)
"""
import sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from pycpa import model, analysis
from pycpa.schedulers_fusion import FusionSchedulerE2E as FusionScheduler

PASS = 0
FAIL = 0

def check(name, val, ref, tol=1e-3):
    global PASS, FAIL
    if abs(val - ref) < tol:
        PASS += 1; return True
    FAIL += 1
    print(f"  FAIL {name}: got={val:.6f} expected={ref:.6f} diff={val-ref:.6f}")
    return False


def test_mix1():
    """TAS + NC+E: guard band + gate-closed blocking on express flow.

    Prio 7: TAS ST, wcet=10, P=1000. Prio 3: NC+E, wcet=20, P=500.
    tas_cycle=500, tas_window={7:100}.

    NCE hand calc:
      gb = max_frag = 1.144 (only interferer is ST/TAS, skipped)
      open = 500 - 100 - 1.144 = 398.856
      tas_gb = ceil(20/398.856)*(100+1.144) = 101.144
      w = 0 + 0 + 0 + 0 + 101.144 = 101.144
      b_plus = 101.144 + 20 = 121.144
    """
    print("[MIX-1: TAS + NC+E]")
    s = model.System()
    r = model.TSN_Resource('R', scheduler=FusionScheduler(), linkspeed=1e9)
    r.priority_mechanism_map = {7: 'TAS', 3: None}
    r.tas_cycle_time = 500; r.tas_window_time_by_priority = {7: 100}
    r.is_express_by_priority = {7: True, 3: True}
    t_st = model.Task('ST', wcet=10, bcet=10, scheduling_parameter=7)
    t_st.in_event_model = model.PJdEventModel(P=1000, J=0); r.bind_task(t_st)
    t = model.Task('NCE', wcet=20, bcet=20, scheduling_parameter=3)
    t.in_event_model = model.PJdEventModel(P=500, J=0); r.bind_task(t)
    s.bind_resource(r)
    res = analysis.analyze_system(s)
    ok = check('NCE', res[t].wcrt, 121.144)
    if ok: print("  PASSED")
    return ok


def test_mix2():
    """TAS + NC+P: gate blocking on preemptable flow, no preemption overhead.

    Prio 7: TAS ST, wcet=10, P=1000. Prio 2: NC+P, wcet=80, P=2000.
    tas_cycle=500, tas_window={7:100}.

    NCP hand calc:
      gb = max_frag = 1.144, open = 398.856
      base = 80 - 0.672 = 79.328
      tas_gb = ceil(80/398.856)*(100+1.144) = 101.144
      No HP non-TAS, no LP express -> w = 79.328 + 101.144 = 180.472
      b_plus = 180.472 + 0.672 = 181.144
    """
    print("[MIX-2: TAS + NC+P]")
    s = model.System()
    r = model.TSN_Resource('R', scheduler=FusionScheduler(), linkspeed=1e9)
    r.priority_mechanism_map = {7: 'TAS', 2: None}
    r.tas_cycle_time = 500; r.tas_window_time_by_priority = {7: 100}
    r.is_express_by_priority = {7: True, 2: False}
    t_st = model.Task('ST', wcet=10, bcet=10, scheduling_parameter=7)
    t_st.in_event_model = model.PJdEventModel(P=1000, J=0); r.bind_task(t_st)
    t = model.Task('NCP', wcet=80, bcet=80, scheduling_parameter=2, payload=400)
    t.in_event_model = model.PJdEventModel(P=2000, J=0); r.bind_task(t)
    s.bind_resource(r)
    res = analysis.analyze_system(s)
    ok = check('NCP', res[t].wcrt, 181.144)
    if ok: print("  PASSED")
    return ok


def test_mix3():
    """TAS + CQF+E: gate blocking on CQF express flow.

    Prio 7: TAS ST, wcet=10, P=500. Prio (5,4): CQF+E, wcet=12, P=500.
    tas_cycle=500, tas_window={7:100}, cqf_cycle=500.

    CE hand calc:
      gb = 1.144, open = 398.856, phi = 500
      tas_gb = ceil(12/398.856)*(100+1.144) = 101.144
      w = 0 + 0 + 500 + 0 + 101.144 = 601.144
      b_plus = 601.144 + 12 = 613.144
    """
    print("[MIX-3: TAS + CQF+E]")
    s = model.System()
    r = model.TSN_Resource('R', scheduler=FusionScheduler(), linkspeed=1e9)
    r.priority_mechanism_map = {7: 'TAS', (5, 4): 'CQF'}
    r.tas_cycle_time = 500; r.tas_window_time_by_priority = {7: 100}
    r.cqf_cycle_time_by_pair = {(5, 4): 500}
    r.is_express_by_priority = {7: True, 5: True, 4: True}
    t_st = model.Task('ST', wcet=10, bcet=10, scheduling_parameter=7)
    t_st.in_event_model = model.PJdEventModel(P=500, J=0); r.bind_task(t_st)
    t = model.Task('CE', wcet=12, bcet=12, scheduling_parameter=5)
    t.in_event_model = model.PJdEventModel(P=500, J=0); r.bind_task(t)
    s.bind_resource(r)
    res = analysis.analyze_system(s)
    ok = check('CE', res[t].wcrt, 613.144)
    if ok: print("  PASSED")
    return ok


def test_mix4():
    """TAS + ATS+E: gate blocking on ATS express flow.

    Prio 7: TAS ST, wcet=10, P=500. Prio 6: ATS+E, wcet=12, P=500.
    CIR=100Mbps, CBS=12000bits. L+=12000bits -> eT=0.
    tas_cycle=500, tas_window={7:100}.

    ATSE hand calc:
      gb = 1.144, open = 398.856
      eT = max(0,(12000-12000)/100e6) = 0
      LPB=0, SPB=0, HPB=0 (ST is TAS, skipped)
      tas_gb = ceil(12/398.856)*(100+1.144) = 101.144
      w = 0 + 0 + 101.144 = 101.144
      b_plus = 101.144 + 12 = 113.144
    """
    print("[MIX-4: TAS + ATS+E]")
    s = model.System()
    r = model.TSN_Resource('R', scheduler=FusionScheduler(), linkspeed=1e9)
    r.priority_mechanism_map = {7: 'TAS', 6: 'ATS'}
    r.tas_cycle_time = 500; r.tas_window_time_by_priority = {7: 100}
    r.is_express_by_priority = {7: True, 6: True}
    t_st = model.Task('ST', wcet=10, bcet=10, scheduling_parameter=7)
    t_st.in_event_model = model.PJdEventModel(P=500, J=0); r.bind_task(t_st)
    t = model.Task('ATSE', wcet=12, bcet=12, scheduling_parameter=6,
                    CIR=100e6, CBS=12000)
    t.in_event_model = model.PJdEventModel(P=500, J=0); r.bind_task(t)
    s.bind_resource(r)
    res = analysis.analyze_system(s)
    ok = check('ATSE', res[t].wcrt, 113.144)
    if ok: print("  PASSED")
    return ok


def test_mix5():
    """CQF+E + ATS+E: two shaping mechanisms, no TAS.

    Prio 6: ATS+E, wcet=12, P=500, CIR=100M, CBS=12000.
    Prio (5,4): CQF+E, wcet=10, P=500, cqf_cycle=500.

    ATSE: LPB=10(CE), SPB=0, HPB=0, eT=0 -> b_plus=10+12=22
    CE: phi=500, HPB=min(eta_closed(0),n_token(0))*12=1*12=12
        w=500+12=512, b_plus=522
    """
    print("[MIX-5: CQF+E + ATS+E]")
    s = model.System()
    r = model.TSN_Resource('R', scheduler=FusionScheduler(), linkspeed=1e9)
    r.priority_mechanism_map = {6: 'ATS', (5, 4): 'CQF'}
    r.cqf_cycle_time_by_pair = {(5, 4): 500}
    r.is_express_by_priority = {6: True, 5: True, 4: True}
    t_ats = model.Task('ATSE', wcet=12, bcet=12, scheduling_parameter=6,
                        CIR=100e6, CBS=12000)
    t_ats.in_event_model = model.PJdEventModel(P=500, J=0); r.bind_task(t_ats)
    t_ce = model.Task('CE', wcet=10, bcet=10, scheduling_parameter=5)
    t_ce.in_event_model = model.PJdEventModel(P=500, J=0); r.bind_task(t_ce)
    s.bind_resource(r)
    res = analysis.analyze_system(s)
    ok = check('ATSE', res[t_ats].wcrt, 22) & check('CE', res[t_ce].wcrt, 522)
    if ok: print("  PASSED")
    return ok


def test_mix6():
    """TAS + NC+E + NC+P: express blocks preemptable, TAS blocks both.

    Prio 7: TAS ST, wcet=10, P=1000. Prio 4: NC+E, wcet=20, P=500.
    Prio 2: NC+P, wcet=80, P=2000. tas_cycle=1000, tas_window={7:200}.

    NCE: gb=1.144, open=798.856, LPB=L+(80)=1.144
      tas_gb=ceil(20/798.856)*201.144=201.144
      w=1.144+201.144=202.288, b_plus=222.288

    NCP: gb=max(1.144,20)=20, open=780
      base=79.328, tas_gb=ceil(80/780)*220=220
      hpb=1*20=20, skd_case1=0.192*1=0.192
      w=79.328+20+220+0.192=319.520, b_plus=320.192
    """
    print("[MIX-6: TAS + NC+E + NC+P]")
    s = model.System()
    r = model.TSN_Resource('R', scheduler=FusionScheduler(), linkspeed=1e9)
    r.priority_mechanism_map = {7: 'TAS', 4: None, 2: None}
    r.tas_cycle_time = 1000; r.tas_window_time_by_priority = {7: 200}
    r.is_express_by_priority = {7: True, 4: True, 2: False}
    t_st = model.Task('ST', wcet=10, bcet=10, scheduling_parameter=7)
    t_st.in_event_model = model.PJdEventModel(P=1000, J=0); r.bind_task(t_st)
    t_nce = model.Task('NCE', wcet=20, bcet=20, scheduling_parameter=4)
    t_nce.in_event_model = model.PJdEventModel(P=500, J=0); r.bind_task(t_nce)
    t_ncp = model.Task('NCP', wcet=80, bcet=80, scheduling_parameter=2, payload=400)
    t_ncp.in_event_model = model.PJdEventModel(P=2000, J=0); r.bind_task(t_ncp)
    s.bind_resource(r)
    res = analysis.analyze_system(s)
    ok = check('NCE', res[t_nce].wcrt, 222.288) & check('NCP', res[t_ncp].wcrt, 320.192)
    if ok: print("  PASSED")
    return ok


def test_mix7():
    """Full 4-mechanism: TAS + ATS+E + CQF+E + NC+P.

    Structural sanity: all WCRTs positive, NCP highest.
    """
    print("[MIX-7: Full 4-mechanism fusion]")
    s = model.System()
    r = model.TSN_Resource('R', scheduler=FusionScheduler(), linkspeed=1e9)
    r.priority_mechanism_map = {7: 'TAS', 6: 'ATS', (5, 4): 'CQF', 2: None}
    r.tas_cycle_time = 500; r.tas_window_time_by_priority = {7: 200}
    r.cqf_cycle_time_by_pair = {(5, 4): 500}
    r.is_express_by_priority = {7: True, 6: True, 5: True, 4: True, 2: False}
    tasks = {}
    for name, p, w, kw in [('ST',7,10,{}), ('ATSE',6,12,dict(CIR=100e6,CBS=12000)),
                            ('CE',5,10,{}), ('NCP',2,80,dict(payload=400))]:
        t = model.Task(name, wcet=w, bcet=w, scheduling_parameter=p, **kw)
        per = {7:1000, 6:500, 5:500, 2:2000}[p]
        t.in_event_model = model.PJdEventModel(P=per, J=0)
        r.bind_task(t); tasks[name] = t
    s.bind_resource(r)
    res = analysis.analyze_system(s)
    for n, t in tasks.items():
        print(f"  {n:5s}: WCRT = {res[t].wcrt:.3f}")
    ok = all(res[t].wcrt > 0 for t in tasks.values())
    # NCP has lowest prio but CE has CQF cycle delay, so CE may be higher
    # Just verify NCP > ATSE (both non-CQF, NCP is lower prio)
    if res[tasks['NCP']].wcrt <= res[tasks['ATSE']].wcrt:
        ok = False; print("  FAIL: NCP should have higher WCRT than ATSE")
    if ok: print("  PASSED (structural)")
    return ok


def test_mix8():
    """High load q>1: NC+E only, cross-check with SPNPScheduler.

    Prio 6: NC+E, wcet=50, P=200. Prio 4: NC+E, wcet=40, P=200.
    """
    print("[MIX-8: High load q>1]")
    from pycpa.schedulers import SPNPScheduler, prio_high_wins_equal_domination
    results = {}
    for label, sched in [('Fusion', FusionScheduler()),
                          ('SPNP', SPNPScheduler(priority_cmp=prio_high_wins_equal_domination))]:
        s = model.System()
        r = model.TSN_Resource('R', scheduler=sched, linkspeed=1e9)
        r.priority_mechanism_map = {6: None, 4: None}
        r.is_express_by_priority = {6: True, 4: True}
        ts = []
        for p, w in [(6, 50), (4, 40)]:
            t = model.Task(f'p{p}', wcet=w, bcet=w, scheduling_parameter=p)
            t.in_event_model = model.PJdEventModel(P=200, J=0)
            r.bind_task(t); ts.append(t)
        s.bind_resource(r)
        results[label] = (analysis.analyze_system(s), ts)
    f_res, f_ts = results['Fusion']; r_res, r_ts = results['SPNP']
    ok = check('HP', f_res[f_ts[0]].wcrt, r_res[r_ts[0]].wcrt)
    ok &= check('LP', f_res[f_ts[1]].wcrt, r_res[r_ts[1]].wcrt)
    print(f"  LP WCRT={f_res[f_ts[1]].wcrt:.3f} (q>1 expected)")
    if ok: print("  PASSED (matches SPNPScheduler)")
    return ok


def test_mix9():
    """Jitter > 0: NC+E with J=50, cross-check with SPNPScheduler."""
    print("[MIX-9: Jitter > 0]")
    from pycpa.schedulers import SPNPScheduler, prio_high_wins_equal_domination
    results = {}
    for label, sched in [('Fusion', FusionScheduler()),
                          ('SPNP', SPNPScheduler(priority_cmp=prio_high_wins_equal_domination))]:
        s = model.System()
        r = model.TSN_Resource('R', scheduler=sched, linkspeed=1e9)
        r.priority_mechanism_map = {6: None, 4: None}
        r.is_express_by_priority = {6: True, 4: True}
        ts = []
        for p, w, J in [(6, 10, 50), (4, 30, 0)]:
            t = model.Task(f'p{p}', wcet=w, bcet=w, scheduling_parameter=p)
            t.in_event_model = model.PJdEventModel(P=200, J=J)
            r.bind_task(t); ts.append(t)
        s.bind_resource(r)
        results[label] = (analysis.analyze_system(s), ts)
    f_res, f_ts = results['Fusion']; r_res, r_ts = results['SPNP']
    ok = check('HP', f_res[f_ts[0]].wcrt, r_res[r_ts[0]].wcrt)
    ok &= check('LP', f_res[f_ts[1]].wcrt, r_res[r_ts[1]].wcrt)
    if ok: print("  PASSED (matches SPNPScheduler, J>0)")
    return ok


if __name__ == '__main__':
    print("=" * 60)
    print("Multi-Mechanism Fusion Cross-Validation")
    print("=" * 60)
    for t in [test_mix1, test_mix2, test_mix3, test_mix4,
              test_mix5, test_mix6, test_mix7, test_mix8, test_mix9]:
        t()
    print()
    total = PASS + FAIL
    print("=" * 60)
    print(f"Results: {PASS}/{total} PASSED, {FAIL}/{total} FAILED")
    print("=" * 60)
    sys.exit(1 if FAIL > 0 else 0)
