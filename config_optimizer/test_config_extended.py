"""Extended tests for FusionConfigOptimizer.

Test scenarios:
  1. test_layer2_cqf_cycle    — CQF flow violates deadline, trigger CQF cycle reduction
  2. test_layer3_ats          — ATS flow with auto-derived CIR/CBS
  3. test_unschedulable       — BW constraint makes config infeasible
  4. test_3hop_mixed          — 3-hop with ST+CQF+ATS+NC, multiple violations
  5. test_already_feasible    — Initial config already OK, only Layer 4 shrinks
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pycpa import model, analysis, path_analysis, options
from pycpa.schedulers_fusion import FusionSchedulerE2E
from config_optimizer import FusionConfigOptimizer

options.set_opt('e2e_improved', False)


def _make_resource(name, sched, tas_window=100, tas_cycle=500,
                   cqf_cycle=500, has_ats=False):
    """Helper: build a TSN_Resource with standard fusion layout."""
    pmap = {7: 'TAS', (5, 4): 'CQF', 1: None}
    if has_ats:
        pmap[6] = 'ATS'
    r = model.TSN_Resource(name, sched,
        priority_mechanism_map=pmap,
        tas_cycle_time=tas_cycle,
        tas_window_time_by_priority={7: tas_window},
        cqf_cycle_time_by_pair={(5, 4): cqf_cycle},
        is_express_by_priority={7: True, 6: True, 5: True, 4: True, 1: True},
    )
    return r


# ======================================================================
# Test 1: Layer 2 — CQF cycle adjustment
# ======================================================================

def test_layer2_cqf_cycle():
    """CQF flow violates tight deadline → optimizer reduces CQF cycle."""
    print('='*60)
    print('Test 1: Layer 2 — CQF cycle adjustment')
    print('='*60)

    s = model.System('test_cqf')
    sched = FusionSchedulerE2E()

    # CQF cycle = 500, which makes CQF E2E large
    r1 = _make_resource('R1', sched, tas_window=100, cqf_cycle=500)
    r2 = _make_resource('R2', sched, tas_window=100, cqf_cycle=500)
    s.bind_resource(r1)
    s.bind_resource(r2)

    # ST flow (should be fine)
    t_st1 = model.Task('ST_h1', wcet=20, scheduling_parameter=7)
    t_st1.in_event_model = model.PJdEventModel(P=500, J=0)
    r1.bind_task(t_st1)
    t_st2 = model.Task('ST_h2', wcet=20, scheduling_parameter=7)
    r2.bind_task(t_st2)
    t_st1.link_dependent_task(t_st2)
    p_st = model.Path('path_ST', [t_st1, t_st2])
    p_st.tas_aligned = True
    s.bind_path(p_st)

    # CQF flow with tight deadline
    t_cqf1 = model.Task('CQF_h1', wcet=15, scheduling_parameter=5)
    t_cqf1.in_event_model = model.PJdEventModel(P=500, J=0)
    r1.bind_task(t_cqf1)
    t_cqf2 = model.Task('CQF_h2', wcet=15, scheduling_parameter=5)
    r2.bind_task(t_cqf2)
    t_cqf1.link_dependent_task(t_cqf2)
    p_cqf = model.Path('path_CQF', [t_cqf1, t_cqf2])
    s.bind_path(p_cqf)

    # Tight CQF deadline: with T_CQF=500, E2E ≈ 500+WCRT > 600
    deadlines = {p_st: 500, p_cqf: 600}

    opt = FusionConfigOptimizer(s, deadlines, tas_step=10,
                                cqf_candidates=[500, 250, 125])
    result = opt.optimize()

    print('  Feasible: %s' % result.feasible)
    print('  Iterations: %d' % result.iterations)
    for rn, p in result.params.items():
        print('  %s: TAS_w=%s CQF=%s' % (rn, p['tas_window_time_by_priority'],
                                           p['cqf_cycle_time_by_pair']))
    for pn, e in result.e2e.items():
        print('  %s: E2E=%.1f' % (pn, e))

    assert result.feasible, 'Should be feasible'
    # CQF cycle should have been reduced
    for rn, p in result.params.items():
        cqf_ct = list(p['cqf_cycle_time_by_pair'].values())[0]
        assert cqf_ct < 500, 'CQF cycle should be reduced from 500, got %s' % cqf_ct
    print('  ✓ PASSED\n')


# ======================================================================
# Test 2: Layer 3 — ATS parameter derivation
# ======================================================================

def test_layer3_ats():
    """System with ATS flow — optimizer derives CIR/CBS."""
    print('='*60)
    print('Test 2: Layer 3 — ATS parameter derivation')
    print('='*60)

    s = model.System('test_ats')
    sched = FusionSchedulerE2E()

    r1 = _make_resource('R1', sched, tas_window=100, has_ats=True)
    r2 = _make_resource('R2', sched, tas_window=100, has_ats=True)
    s.bind_resource(r1)
    s.bind_resource(r2)

    # ST flow
    t_st1 = model.Task('ST_h1', wcet=20, scheduling_parameter=7)
    t_st1.in_event_model = model.PJdEventModel(P=500, J=0)
    r1.bind_task(t_st1)
    t_st2 = model.Task('ST_h2', wcet=20, scheduling_parameter=7)
    r2.bind_task(t_st2)
    t_st1.link_dependent_task(t_st2)
    p_st = model.Path('path_ST', [t_st1, t_st2])
    p_st.tas_aligned = True
    s.bind_path(p_st)

    # ATS flow (prio 6) — initial CIR/CBS set, optimizer will re-derive
    t_ats1 = model.Task('ATS_h1', wcet=12, scheduling_parameter=6,
                         CIR=100e6, CBS=12000)
    t_ats1.in_event_model = model.PJdEventModel(P=500, J=0)
    r1.bind_task(t_ats1)
    t_ats2 = model.Task('ATS_h2', wcet=12, scheduling_parameter=6,
                         CIR=100e6, CBS=12000)
    r2.bind_task(t_ats2)
    t_ats1.link_dependent_task(t_ats2)
    p_ats = model.Path('path_ATS', [t_ats1, t_ats2])
    p_ats.tas_aligned = True
    s.bind_path(p_ats)

    deadlines = {p_st: 500, p_ats: 1000}

    opt = FusionConfigOptimizer(s, deadlines, tas_step=10)
    result = opt.optimize()

    print('  Feasible: %s' % result.feasible)
    print('  Iterations: %d' % result.iterations)
    for pn, e in result.e2e.items():
        print('  %s: E2E=%.1f' % (pn, e))
    # Check ATS params were set
    print('  ATS_h1 CIR=%.0f CBS=%.0f' % (t_ats1.CIR, t_ats1.CBS))
    print('  ATS_h2 CIR=%.0f CBS=%.0f' % (t_ats2.CIR, t_ats2.CBS))

    assert result.feasible, 'Should be feasible'
    print('  ✓ PASSED\n')


# ======================================================================
# Test 3: Unschedulable — BW constraint too tight
# ======================================================================

def test_unschedulable():
    """BW constraint so tight that increasing TAS window is blocked."""
    print('='*60)
    print('Test 3: Unschedulable — BW constraint too tight')
    print('='*60)

    s = model.System('test_unsched')
    sched = FusionSchedulerE2E()

    # TAS window starts small, ST needs more, but bw_min blocks expansion
    r1 = _make_resource('R1', sched, tas_window=30, tas_cycle=500)
    s.bind_resource(r1)

    t_st = model.Task('ST_1', wcet=80, scheduling_parameter=7)
    t_st.in_event_model = model.PJdEventModel(P=500, J=0)
    r1.bind_task(t_st)

    p_st = model.Path('path_ST', [t_st])
    p_st.tas_aligned = True
    s.bind_path(p_st)

    # ST needs wcet=80 but window=30, needs ~100+ window
    # bw_min=450 means open_time must be ≥ 450
    # open_time = 500 - TAS_window - guard_band
    # If TAS_window grows to 100, open_time = 400 < 450 → blocked
    deadlines = {p_st: 100}

    opt = FusionConfigOptimizer(s, deadlines, bw_min=450, tas_step=10)
    result = opt.optimize()

    print('  Feasible: %s' % result.feasible)
    print('  Reason: %s' % result.reason)

    # Should detect unschedulable (BW constraint blocks TAS expansion)
    # or ST still violates after hitting BW limit
    assert not result.feasible, 'Should be infeasible'
    print('  ✓ PASSED\n')


# ======================================================================
# Test 4: 3-hop mixed — ST+CQF+ATS+NC, multiple violations
# ======================================================================

def test_3hop_mixed():
    """3-hop network with all flow types, ST and CQF initially violate."""
    print('='*60)
    print('Test 4: 3-hop mixed — ST+CQF+ATS+NC')
    print('='*60)

    s = model.System('test_3hop')
    sched = FusionSchedulerE2E()

    resources = []
    for i in range(3):
        r = _make_resource('R%d' % i, sched, tas_window=40,
                           tas_cycle=500, cqf_cycle=500, has_ats=True)
        s.bind_resource(r)
        resources.append(r)

    # ST flow: 3 hops, wcet=35, small window → violates
    st_tasks = []
    for i, r in enumerate(resources):
        t = model.Task('ST_h%d' % i, wcet=35, scheduling_parameter=7)
        if i == 0:
            t.in_event_model = model.PJdEventModel(P=500, J=0)
        r.bind_task(t)
        if i > 0:
            st_tasks[-1].link_dependent_task(t)
        st_tasks.append(t)
    p_st = model.Path('path_ST', st_tasks)
    p_st.tas_aligned = True
    s.bind_path(p_st)

    # CQF flow: 3 hops
    cqf_tasks = []
    for i, r in enumerate(resources):
        t = model.Task('CQF_h%d' % i, wcet=15, scheduling_parameter=5)
        if i == 0:
            t.in_event_model = model.PJdEventModel(P=500, J=0)
        r.bind_task(t)
        if i > 0:
            cqf_tasks[-1].link_dependent_task(t)
        cqf_tasks.append(t)
    p_cqf = model.Path('path_CQF', cqf_tasks)
    s.bind_path(p_cqf)

    # ATS flow: 3 hops
    ats_tasks = []
    for i, r in enumerate(resources):
        t = model.Task('ATS_h%d' % i, wcet=12, scheduling_parameter=6,
                        CIR=100e6, CBS=12000)
        if i == 0:
            t.in_event_model = model.PJdEventModel(P=500, J=0)
        r.bind_task(t)
        if i > 0:
            ats_tasks[-1].link_dependent_task(t)
        ats_tasks.append(t)
    p_ats = model.Path('path_ATS', ats_tasks)
    p_ats.tas_aligned = True
    s.bind_path(p_ats)

    # NC flow: 3 hops
    nc_tasks = []
    for i, r in enumerate(resources):
        t = model.Task('NC_h%d' % i, wcet=10, scheduling_parameter=1)
        if i == 0:
            t.in_event_model = model.PJdEventModel(P=2000, J=0)
        r.bind_task(t)
        if i > 0:
            nc_tasks[-1].link_dependent_task(t)
        nc_tasks.append(t)
    p_nc = model.Path('path_NC', nc_tasks)
    p_nc.tas_aligned = True
    s.bind_path(p_nc)

    deadlines = {p_st: 300, p_cqf: 1200, p_ats: 1500, p_nc: 5000}

    opt = FusionConfigOptimizer(s, deadlines, bw_min=50, tas_step=5,
                                cqf_candidates=[500, 250, 125])
    result = opt.optimize()

    print('  Feasible: %s' % result.feasible)
    print('  Iterations: %d' % result.iterations)
    for rn, p in result.params.items():
        print('  %s: TAS_w=%s TAS_c=%s CQF=%s' % (
            rn, p['tas_window_time_by_priority'],
            p['tas_cycle_time'], p['cqf_cycle_time_by_pair']))
    for pn, e in result.e2e.items():
        dl = None
        for p, d in deadlines.items():
            if p.name == pn:
                dl = d
        status = 'OK' if dl and e <= dl else 'VIOLATED'
        print('  %s: E2E=%.1f dl=%s [%s]' % (pn, e, dl, status))

    assert result.feasible, 'Should be feasible'
    print('  ✓ PASSED\n')


# ======================================================================
# Test 5: Already feasible — only Layer 4 shrinks
# ======================================================================

def test_already_feasible():
    """Initial config already meets all deadlines. Only TAS shrink runs."""
    print('='*60)
    print('Test 5: Already feasible — TAS shrink only')
    print('='*60)

    s = model.System('test_ok')
    sched = FusionSchedulerE2E()

    # Generous TAS window
    r1 = _make_resource('R1', sched, tas_window=200, tas_cycle=500)
    s.bind_resource(r1)

    t_st = model.Task('ST_1', wcet=20, scheduling_parameter=7)
    t_st.in_event_model = model.PJdEventModel(P=500, J=0)
    r1.bind_task(t_st)

    p_st = model.Path('path_ST', [t_st])
    p_st.tas_aligned = True
    s.bind_path(p_st)

    deadlines = {p_st: 500}

    opt = FusionConfigOptimizer(s, deadlines, tas_step=10)
    result = opt.optimize()

    print('  Feasible: %s' % result.feasible)
    print('  Iterations: %d' % result.iterations)
    final_tw = list(result.params['R1']['tas_window_time_by_priority'].values())[0]
    print('  TAS window: 200 → %d (shrunk)' % final_tw)
    for pn, e in result.e2e.items():
        print('  %s: E2E=%.1f' % (pn, e))

    assert result.feasible
    assert final_tw < 200, 'TAS window should be shrunk from 200, got %d' % final_tw
    print('  ✓ PASSED\n')


# ======================================================================
# Main
# ======================================================================

if __name__ == '__main__':
    test_layer2_cqf_cycle()
    test_layer3_ats()
    test_unschedulable()
    test_3hop_mixed()
    test_already_feasible()
    print('='*60)
    print('All 5 tests PASSED')
    print('='*60)
