"""Test for FusionConfigOptimizer.

Scenario: 2-hop network with ST, CQF, and NC flows.
Initial TAS window is too small → ST violates deadline.
Optimizer should increase TAS window, then shrink it back.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pycpa import model, analysis, path_analysis, options
from pycpa.schedulers_fusion import FusionSchedulerE2E
from config_optimizer import FusionConfigOptimizer


def build_system():
    """Build a 2-hop TSN system with ST, CQF+E, and NC+E flows."""
    s = model.System('test_config')
    sched = FusionSchedulerE2E()

    # --- Resource 1 (switch port 1) ---
    r1 = model.TSN_Resource('R1', sched,
        priority_mechanism_map={
            7: 'TAS',
            (5, 4): 'CQF',
            1: None,   # NC
        },
        tas_cycle_time=500,
        tas_window_time_by_priority={7: 30},  # initially small
        cqf_cycle_time_by_pair={(5, 4): 500},
        is_express_by_priority={7: True, 5: True, 4: True, 1: True},
    )
    s.bind_resource(r1)

    # --- Resource 2 (switch port 2) ---
    r2 = model.TSN_Resource('R2', sched,
        priority_mechanism_map={
            7: 'TAS',
            (5, 4): 'CQF',
            1: None,
        },
        tas_cycle_time=500,
        tas_window_time_by_priority={7: 30},
        cqf_cycle_time_by_pair={(5, 4): 500},
        is_express_by_priority={7: True, 5: True, 4: True, 1: True},
    )
    s.bind_resource(r2)

    # --- ST flow (prio 7, TAS) ---
    t_st1 = model.Task('ST_h1', wcet=40, scheduling_parameter=7)
    t_st1.in_event_model = model.PJdEventModel(P=500, J=0)
    r1.bind_task(t_st1)

    t_st2 = model.Task('ST_h2', wcet=40, scheduling_parameter=7)
    r2.bind_task(t_st2)
    t_st1.link_dependent_task(t_st2)

    p_st = model.Path('path_ST', [t_st1, t_st2])
    p_st.tas_aligned = True
    s.bind_path(p_st)

    # --- CQF+E flow (prio 5) ---
    t_cqf1 = model.Task('CQF_h1', wcet=20, scheduling_parameter=5)
    t_cqf1.in_event_model = model.PJdEventModel(P=500, J=0)
    r1.bind_task(t_cqf1)

    t_cqf2 = model.Task('CQF_h2', wcet=20, scheduling_parameter=5)
    r2.bind_task(t_cqf2)
    t_cqf1.link_dependent_task(t_cqf2)

    p_cqf = model.Path('path_CQF', [t_cqf1, t_cqf2])
    s.bind_path(p_cqf)

    # --- NC+E flow (prio 1) ---
    t_nc1 = model.Task('NC_h1', wcet=15, scheduling_parameter=1)
    t_nc1.in_event_model = model.PJdEventModel(P=2000, J=0)
    r1.bind_task(t_nc1)

    t_nc2 = model.Task('NC_h2', wcet=15, scheduling_parameter=1)
    r2.bind_task(t_nc2)
    t_nc1.link_dependent_task(t_nc2)

    p_nc = model.Path('path_NC', [t_nc1, t_nc2])
    p_nc.tas_aligned = True
    s.bind_path(p_nc)

    return s, {p_st: 200, p_cqf: 1500, p_nc: 3000}


def test_optimizer():
    s, deadlines = build_system()

    print('='*60)
    print('Initial config:')
    for r in s.resources:
        if getattr(r, 'is_tsn_resource', False):
            print('  %s: TAS_window=%s, CQF_cycle=%s' % (
                r.name, r.tas_window_time_by_priority,
                r.cqf_cycle_time_by_pair))

    # Run initial analysis to show violations
    print('\nInitial E2E:')
    try:
        tr = analysis.analyze_system(s)
        for p, dl in deadlines.items():
            lmin, lmax = path_analysis.end_to_end_latency(p, tr)
            status = 'OK' if lmax <= dl else 'VIOLATED'
            print('  %s: E2E=%.1f, deadline=%.1f [%s]' % (
                p.name, lmax, dl, status))
    except Exception as e:
        print('  Analysis failed: %s' % e)

    # Run optimizer
    print('\n' + '='*60)
    print('Running optimizer...')
    opt = FusionConfigOptimizer(
        s, deadlines,
        bw_min=100,     # minimum 100 time units open per cycle
        tas_step=10,
    )
    result = opt.optimize()

    print('\nResult:')
    print('  Feasible: %s' % result.feasible)
    print('  Reason: %s' % result.reason)
    print('  Iterations: %d' % result.iterations)

    print('\nFinal params:')
    for rname, params in result.params.items():
        print('  %s: TAS_window=%s, TAS_cycle=%s, CQF_cycle=%s' % (
            rname, params['tas_window_time_by_priority'],
            params['tas_cycle_time'],
            params['cqf_cycle_time_by_pair']))

    print('\nFinal E2E:')
    for pname, e2e in result.e2e.items():
        dl = None
        for p, d in deadlines.items():
            if p.name == pname:
                dl = d
                break
        status = 'OK' if dl and e2e <= dl else 'VIOLATED'
        print('  %s: E2E=%.1f, deadline=%s [%s]' % (pname, e2e, dl, status))

    # Verify feasibility
    if result.feasible:
        print('\n✓ All deadlines satisfied!')
    else:
        print('\n✗ Some deadlines not met: %s' % result.reason)

    return result


if __name__ == '__main__':
    options.set_opt('e2e_improved', False)
    result = test_optimizer()
