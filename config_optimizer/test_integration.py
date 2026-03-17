"""Tests: Integration / end-to-end scenarios."""
from test_helpers import *
from config_optimizer import FusionConfigOptimizer

def test_all_layers_fire():
    """Scenario requiring all 4 layers: TAS grow + CQF shrink + ATS derive + TAS shrink."""
    print('\n--- test_all_layers_fire ---')
    s = model.System('t')
    sched = FusionSchedulerE2E()
    rs = []
    for i in range(2):
        r = make_res('R%d' % i, sched, tas_w=30, tas_c=500, cqf_c=500, has_ats=True)
        s.bind_resource(r); rs.append(r)
    p_st, _ = make_chain(s, rs, 'ST', 7, 35, 500, tas_aligned=True)
    p_cqf, _ = make_chain(s, rs, 'CQF', 5, 15, 500)
    p_ats, t_ats = make_chain(s, rs, 'ATS', 6, 12, 500, cir=100e6, cbs=12000)
    dl = {p_st: 300, p_cqf: 800, p_ats: 2000}
    res = FusionConfigOptimizer(s, dl, tas_step=5,
                                cqf_candidates=[500, 250, 125]).optimize()
    check('feasible', res.feasible)
    for pn, e in res.e2e.items():
        for p, d in dl.items():
            if p.name == pn:
                check('%s <= deadline' % pn, e <= d, 'e2e=%.1f dl=%s' % (e, d))

def test_already_feasible_no_change():
    """All deadlines met initially → only Layer 4 shrinks, no other changes."""
    print('\n--- test_already_feasible_no_change ---')
    s = model.System('t')
    sched = FusionSchedulerE2E()
    r = make_res('R1', sched, tas_w=200, tas_c=500)
    s.bind_resource(r)
    p, _ = make_chain(s, [r], 'ST', 7, 20, 500, tas_aligned=True)
    dl = {p: 5000}
    res = FusionConfigOptimizer(s, dl, tas_step=10).optimize()
    check('feasible', res.feasible)
    tw = res.params['R1']['tas_window_time_by_priority'][7]
    check('TAS shrunk from 200', tw < 200, 'tw=%s' % tw)

def test_idempotent():
    """Running optimizer twice gives same result."""
    print('\n--- test_idempotent ---')
    s = model.System('t')
    sched = FusionSchedulerE2E()
    r = make_res('R1', sched, tas_w=30, tas_c=500)
    s.bind_resource(r)
    p, _ = make_chain(s, [r], 'ST', 7, 40, 500, tas_aligned=True)
    dl = {p: 200}
    opt = FusionConfigOptimizer(s, dl, tas_step=10)
    r1 = opt.optimize()
    tw1 = r.tas_window_time_by_priority[7]
    e1 = r1.e2e.get('path_ST')
    # Run again on same (now-configured) system
    opt2 = FusionConfigOptimizer(s, dl, tas_step=10)
    r2 = opt2.optimize()
    tw2 = r.tas_window_time_by_priority[7]
    e2 = r2.e2e.get('path_ST')
    check('both feasible', r1.feasible and r2.feasible)
    check('same TAS window', tw1 == tw2, 'tw1=%s tw2=%s' % (tw1, tw2))
    check('same E2E', e1 == e2, 'e1=%s e2=%s' % (e1, e2))

def test_5hop_stress():
    """5-hop chain with tight deadlines."""
    print('\n--- test_5hop_stress ---')
    s = model.System('t')
    sched = FusionSchedulerE2E()
    rs = []
    for i in range(5):
        r = make_res('R%d' % i, sched, tas_w=30, tas_c=500, cqf_c=500)
        s.bind_resource(r); rs.append(r)
    p_st, _ = make_chain(s, rs, 'ST', 7, 20, 500, tas_aligned=True)
    p_cqf, _ = make_chain(s, rs, 'CQF', 5, 10, 500)
    dl = {p_st: 500, p_cqf: 2000}
    res = FusionConfigOptimizer(s, dl, tas_step=5,
                                cqf_candidates=[500, 250, 125]).optimize()
    check('feasible', res.feasible)
    check('5 resources in params', len(res.params) == 5)

if __name__ == '__main__':
    test_all_layers_fire()
    test_already_feasible_no_change()
    test_idempotent()
    test_5hop_stress()
    exit(0 if summary() else 1)
