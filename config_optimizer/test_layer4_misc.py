"""Tests: Layer 4 (TAS shrink), snapshot/restore, result fields."""
from test_helpers import *
from config_optimizer import FusionConfigOptimizer

def test_shrink_rollback():
    """Layer 4 shrinks too far -> rollback to last good config."""
    print('\n--- test_shrink_rollback ---')
    s = model.System('t')
    sched = FusionSchedulerE2E()
    r = make_res('R1', sched, tas_w=50, tas_c=500)
    s.bind_resource(r)
    p, _ = make_chain(s, [r], 'ST', 7, 45, 500, tas_aligned=True)
    dl = {p: 200}
    res = FusionConfigOptimizer(s, dl, tas_step=10).optimize()
    check('feasible', res.feasible)
    tw = r.tas_window_time_by_priority[7]
    check('window >= 45', tw >= 45, 'tw=%s' % tw)

def test_snapshot_restore_ats():
    """Snapshot/restore preserves ATS CIR/CBS."""
    print('\n--- test_snapshot_restore_ats ---')
    s = model.System('t')
    sched = FusionSchedulerE2E()
    r = make_res('R1', sched, tas_w=100, tas_c=500, has_ats=True)
    s.bind_resource(r)
    p_st, _ = make_chain(s, [r], 'ST', 7, 20, 500, tas_aligned=True)
    p_ats, t_ats = make_chain(s, [r], 'ATS', 6, 12, 500, cir=42e6, cbs=9999)
    dl = {p_st: 500, p_ats: 5000}
    opt = FusionConfigOptimizer(s, dl, tas_step=10)
    snap = opt._snapshot()
    t_ats[0].CIR = 999; t_ats[0].CBS = 1
    r.tas_window_time_by_priority[7] = 999
    opt._restore(snap)
    check('CIR restored', t_ats[0].CIR == 42e6, 'got %s' % t_ats[0].CIR)
    check('CBS restored', t_ats[0].CBS == 9999, 'got %s' % t_ats[0].CBS)
    check('TAS_w restored', r.tas_window_time_by_priority[7] == 100)

def test_result_fields():
    """ConfigResult has all expected fields populated."""
    print('\n--- test_result_fields ---')
    s = model.System('t')
    sched = FusionSchedulerE2E()
    r = make_res('R1', sched, tas_w=100, tas_c=500)
    s.bind_resource(r)
    p, _ = make_chain(s, [r], 'ST', 7, 20, 500, tas_aligned=True)
    dl = {p: 500}
    res = FusionConfigOptimizer(s, dl, tas_step=10).optimize()
    check('feasible is bool', isinstance(res.feasible, bool))
    check('iterations > 0', res.iterations > 0)
    check('params has R1', 'R1' in res.params)
    check('e2e has path_ST', 'path_ST' in res.e2e)
    check('history len == iterations', len(res.history) == res.iterations)
    check('params keys', all(k in res.params['R1'] for k in
          ['tas_cycle_time', 'tas_window_time_by_priority', 'cqf_cycle_time_by_pair']))

def test_history_recording():
    """History records E2E at each iteration."""
    print('\n--- test_history_recording ---')
    s = model.System('t')
    sched = FusionSchedulerE2E()
    r = make_res('R1', sched, tas_w=20, tas_c=500)
    s.bind_resource(r)
    p, _ = make_chain(s, [r], 'ST', 7, 40, 500, tas_aligned=True)
    dl = {p: 200}
    res = FusionConfigOptimizer(s, dl, tas_step=10).optimize()
    check('feasible', res.feasible)
    check('history non-empty', len(res.history) > 1)
    for h in res.history:
        check('entry has path_ST', 'path_ST' in h)
        break

def test_cqf_not_clearable():
    """CQF not clearable detected."""
    print('\n--- test_cqf_not_clearable ---')
    s = model.System('t')
    sched = FusionSchedulerE2E()
    r = make_res('R1', sched, tas_w=450, tas_c=500, cqf_c=500)
    s.bind_resource(r)
    p_st, _ = make_chain(s, [r], 'ST', 7, 20, 500, tas_aligned=True)
    p_cqf, _ = make_chain(s, [r], 'CQF', 5, 60, 500)
    dl = {p_st: 500, p_cqf: 2000}
    opt = FusionConfigOptimizer(s, dl, tas_step=10)
    unsched, reason = opt._check_unschedulable()
    check('detected unschedulable', unsched, reason)
    check('reason mentions CQF', 'CQF' in reason, reason)

if __name__ == '__main__':
    test_shrink_rollback()
    test_snapshot_restore_ats()
    test_result_fields()
    test_history_recording()
    test_cqf_not_clearable()
    exit(0 if summary() else 1)
