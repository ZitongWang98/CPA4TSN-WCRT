"""Tests: Layer 1 (TAS window) edge cases."""
from test_helpers import *
from config_optimizer import FusionConfigOptimizer

def test_multi_tas_priority():
    """Two TAS priorities on same resource, both need window growth."""
    print('\n--- test_multi_tas_priority ---')
    s = model.System('t')
    sched = FusionSchedulerE2E()
    r = make_res('R1', sched, tas_w=20, tas_c=500, extra_pmap={6: 'TAS'},
                 extra_tas_w={6: 20})
    s.bind_resource(r)
    p7, _ = make_chain(s, [r], 'ST7', 7, 40, 500, tas_aligned=True)
    p6, _ = make_chain(s, [r], 'ST6', 6, 40, 500, tas_aligned=True)
    dl = {p7: 200, p6: 200}
    res = FusionConfigOptimizer(s, dl, tas_step=10).optimize()
    check('feasible', res.feasible)
    tw7 = r.tas_window_time_by_priority[7]
    tw6 = r.tas_window_time_by_priority[6]
    check('prio7 grew', tw7 > 20, 'tw7=%s' % tw7)
    check('prio6 grew', tw6 > 20, 'tw6=%s' % tw6)

def test_layer1_max_iter():
    """Layer 1 hits max_iterations → infeasible."""
    print('\n--- test_layer1_max_iter ---')
    s = model.System('t')
    sched = FusionSchedulerE2E()
    r = make_res('R1', sched, tas_w=10, tas_c=500)
    s.bind_resource(r)
    p, _ = make_chain(s, [r], 'ST', 7, 40, 500, tas_aligned=True)
    # deadline=1 is impossible, max_iter=3 so it gives up fast
    dl = {p: 1}
    res = FusionConfigOptimizer(s, dl, tas_step=1, max_iterations=3).optimize()
    check('infeasible', not res.feasible)
    check('reason mentions Layer 1', 'Layer 1' in res.reason, res.reason)

def test_single_hop():
    """Single-hop path works correctly."""
    print('\n--- test_single_hop ---')
    s = model.System('t')
    sched = FusionSchedulerE2E()
    r = make_res('R1', sched, tas_w=10, tas_c=500)
    s.bind_resource(r)
    p, _ = make_chain(s, [r], 'ST', 7, 20, 500, tas_aligned=True)
    dl = {p: 200}
    res = FusionConfigOptimizer(s, dl, tas_step=5).optimize()
    check('feasible', res.feasible)
    check('e2e recorded', 'path_ST' in res.e2e)

def test_no_bw_constraint():
    """bw_min=None allows unlimited TAS expansion."""
    print('\n--- test_no_bw_constraint ---')
    s = model.System('t')
    sched = FusionSchedulerE2E()
    r = make_res('R1', sched, tas_w=10, tas_c=500)
    s.bind_resource(r)
    p, _ = make_chain(s, [r], 'ST', 7, 40, 500, tas_aligned=True)
    dl = {p: 200}
    res = FusionConfigOptimizer(s, dl, bw_min=None, tas_step=10).optimize()
    check('feasible', res.feasible)

if __name__ == '__main__':
    test_multi_tas_priority()
    test_layer1_max_iter()
    test_single_hop()
    test_no_bw_constraint()
    exit(0 if summary() else 1)
