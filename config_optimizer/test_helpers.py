"""Shared helpers for config optimizer tests."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pycpa import model, options
from pycpa.schedulers_fusion import FusionSchedulerE2E

options.set_opt('e2e_improved', False)

PASS = 0
FAIL = 0

def make_res(name, sched, tas_w=100, tas_c=500, cqf_c=500,
             has_ats=False, gb=None, linkspeed=1e9,
             extra_pmap=None, extra_tas_w=None):
    pmap = {7: 'TAS', (5, 4): 'CQF', 1: None}
    if has_ats:
        pmap[6] = 'ATS'
    if extra_pmap:
        pmap.update(extra_pmap)
    tw = {7: tas_w}
    if extra_tas_w:
        tw.update(extra_tas_w)
    kw = dict(
        priority_mechanism_map=pmap,
        tas_cycle_time=tas_c,
        tas_window_time_by_priority=tw,
        cqf_cycle_time_by_pair={(5, 4): cqf_c},
        is_express_by_priority={7: True, 6: True, 5: True, 4: True, 1: True},
        linkspeed=linkspeed,
    )
    if gb is not None:
        kw['guard_band'] = gb
    return model.TSN_Resource(name, sched, **kw)


def make_chain(s, resources, name, prio, wcet, period, tas_aligned=False,
               cir=None, cbs=None):
    """Create a multi-hop flow chain and path."""
    tasks = []
    for i, r in enumerate(resources):
        kw = dict(wcet=wcet, scheduling_parameter=prio)
        if cir is not None:
            kw['CIR'] = cir
            kw['CBS'] = cbs or 12000
        t = model.Task('%s_h%d' % (name, i), **kw)
        if i == 0:
            t.in_event_model = model.PJdEventModel(P=period, J=0)
        r.bind_task(t)
        if i > 0:
            tasks[-1].link_dependent_task(t)
        tasks.append(t)
    p = model.Path('path_%s' % name, tasks)
    if tas_aligned:
        p.tas_aligned = True
    s.bind_path(p)
    return p, tasks


def check(name, cond, msg=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print('  ✓ %s' % name)
    else:
        FAIL += 1
        print('  ✗ %s — %s' % (name, msg))


def summary():
    total = PASS + FAIL
    print('\n' + '=' * 60)
    print('%d/%d passed, %d failed' % (PASS, total, FAIL))
    print('=' * 60)
    return FAIL == 0
