"""Tests: Layer 2 (CQF cycle) and GCL linkage edge cases."""
from test_helpers import *
from config_optimizer import FusionConfigOptimizer

def test_gcl_linkage_shrink():
    """CQF shrinks below TAS cycle → TAS cycle must follow."""
    print('\n--- test_gcl_linkage_shrink ---')
    s = model.System('t')
    sched = FusionSchedulerE2E()
    # tas_cycle=500, cqf=500. CQF will shrink to 250 → TAS must follow
    r1 = make_res('R1', sched, tas_w=50, tas_c=500, cqf_c=500)
    r2 = make_res('R2', sched, tas_w=50, tas_c=500, cqf_c=500)
    s.bind_resource(r1); s.bind_resource(r2)
    p_st, _ = make_chain(s, [r1, r2], 'ST', 7, 20, 500, tas_aligned=True)
    p_cqf, _ = make_chain(s, [r1, r2], 'CQF', 5, 15, 500)
    dl = {p_st: 500, p_cqf: 600}
    res = FusionConfigOptimizer(s, dl, tas_step=10,
                                cqf_candidates=[500, 250, 125]).optimize()
    check('feasible', res.feasible)
    for rn, p in res.params.items():
        cqf_ct = list(p['cqf_cycle_time_by_pair'].values())[0]
        tas_ct = p['tas_cycle_time']
        ratio = cqf_ct / tas_ct if tas_ct else 0
        check('%s: cqf/tas ratio valid' % rn,
              ratio >= 1 and (ratio == 1 or int(ratio) % 2 == 0),
              'cqf=%s tas=%s ratio=%s' % (cqf_ct, tas_ct, ratio))

def test_gcl_linkage_already_valid():
    """CQF/TAS ratio already valid → TAS cycle unchanged."""
    print('\n--- test_gcl_linkage_already_valid ---')
    s = model.System('t')
    sched = FusionSchedulerE2E()
    # tas_cycle=250, cqf=500 → ratio=2 (valid even), no change needed
    r = make_res('R1', sched, tas_w=50, tas_c=250, cqf_c=500)
    s.bind_resource(r)
    p_st, _ = make_chain(s, [r], 'ST', 7, 20, 250, tas_aligned=True)
    p_cqf, _ = make_chain(s, [r], 'CQF', 5, 15, 500)
    dl = {p_st: 500, p_cqf: 2000}  # generous deadlines
    res = FusionConfigOptimizer(s, dl, tas_step=10).optimize()
    check('feasible', res.feasible)
    # TAS cycle should stay at 250 (or shrink, but not grow)
    tas_ct = res.params['R1']['tas_cycle_time']
    check('tas_cycle <= 250', tas_ct <= 250, 'got %s' % tas_ct)

def test_default_cqf_candidates():
    """No explicit cqf_candidates → uses halving strategy."""
    print('\n--- test_default_cqf_candidates ---')
    s = model.System('t')
    sched = FusionSchedulerE2E()
    r1 = make_res('R1', sched, tas_w=50, tas_c=500, cqf_c=500)
    r2 = make_res('R2', sched, tas_w=50, tas_c=500, cqf_c=500)
    s.bind_resource(r1); s.bind_resource(r2)
    p_st, _ = make_chain(s, [r1, r2], 'ST', 7, 20, 500, tas_aligned=True)
    p_cqf, _ = make_chain(s, [r1, r2], 'CQF', 5, 15, 500)
    dl = {p_st: 500, p_cqf: 600}
    # No cqf_candidates → default halving
    res = FusionConfigOptimizer(s, dl, tas_step=10).optimize()
    check('feasible', res.feasible)
    cqf_ct = list(res.params['R1']['cqf_cycle_time_by_pair'].values())[0]
    check('cqf reduced', cqf_ct < 500, 'got %s' % cqf_ct)
    # Should be a power-of-2 divisor of 500
    check('cqf is 250 or 125', cqf_ct in [250, 125, 62.5], 'got %s' % cqf_ct)

def test_cqf_no_improvement():
    """All CQF candidates tried but still violating → returns best effort."""
    print('\n--- test_cqf_no_improvement ---')
    s = model.System('t')
    sched = FusionSchedulerE2E()
    r1 = make_res('R1', sched, tas_w=50, tas_c=500, cqf_c=500)
    r2 = make_res('R2', sched, tas_w=50, tas_c=500, cqf_c=500)
    r3 = make_res('R3', sched, tas_w=50, tas_c=500, cqf_c=500)
    s.bind_resource(r1); s.bind_resource(r2); s.bind_resource(r3)
    p_st, _ = make_chain(s, [r1, r2, r3], 'ST', 7, 20, 500, tas_aligned=True)
    p_cqf, _ = make_chain(s, [r1, r2, r3], 'CQF', 5, 15, 500)
    # Impossibly tight CQF deadline for 3 hops
    dl = {p_st: 500, p_cqf: 50}
    res = FusionConfigOptimizer(s, dl, tas_step=10,
                                cqf_candidates=[500, 250, 125]).optimize()
    check('infeasible', not res.feasible)

if __name__ == '__main__':
    test_gcl_linkage_shrink()
    test_gcl_linkage_already_valid()
    test_default_cqf_candidates()
    test_cqf_no_improvement()
    exit(0 if summary() else 1)
