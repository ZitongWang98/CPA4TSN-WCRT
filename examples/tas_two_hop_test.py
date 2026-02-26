"""
TAS Two-Hop Analysis Scenarios

All scenarios share the same two-hop topology:

    Terminal  --->  [Switch1]  --->  [Switch2]  --->  Terminal

Common parameters:
    Link speed          : 1 Gbps
    Frame size          : 1518 bytes  =>  wcet = bcet = 12 us
    TAS cycle time      : 1000 us     (same on both switches)
    TAS window (prio 7) : 100 us      (same on both switches)
    All flows period    : 1000 us, jitter = 0

Scenarios:
==========
1.1  Analyzed flow = TAS (prio 7),  + one lower-priority NST flow (prio 1)
1.2  Analyzed flow = TAS (prio 7),  + one same-priority TAS flow (prio 7)
2.1  Analyzed flow = NST (prio 3),  + one TAS flow (prio 7), + one lower-prio  NST (prio 1)
2.2  Analyzed flow = NST (prio 3),  + one TAS flow (prio 7), + one same-prio   NST (prio 3)
2.3  Analyzed flow = NST (prio 3),  + one TAS flow (prio 7), + one higher-prio NST (prio 5)

Analysis Based on:
==================
THIELE D, ERNST R, DIEMER J. Formal worst-case timing analysis of
Ethernet TSN's time-aware and peristaltic shapers[C]//2015 IEEE
Vehicular Networking Conference (VNC). Kyoto, Japan: IEEE, 2015: 251-258.
"""

from pycpa import model
from pycpa import analysis
from pycpa import path_analysis
from pycpa import schedulers
from pycpa import options

WCET = 12       # 1518B @ 1Gbps
PERIOD = 1000   # us
CYCLE = 1000    # TAS cycle time (us)
WINDOW_7 = 100  # TAS window for priority 7 (us)


def _print_results(s, results, analyzed_path_tasks):
    """Print per-hop and end-to-end results."""
    print("\n  Per-Hop Results:")
    for t in analyzed_path_tasks:
        r = t.resource
        mech = r.get_mechanism_for_priority(t.scheduling_parameter) if getattr(r, 'is_tsn_resource', False) else None
        print(f"    {t.name} on {r.name}  (prio={t.scheduling_parameter}, mech={mech}):")
        print(f"      WCRT = {results[t].wcrt} us,  BCRT = {results[t].bcrt} us")

    print("\n  End-to-End Path Results:")
    for p in s.paths:
        e2e = path_analysis.end_to_end_latency(p, results, 1)
        print(f"    Path '{p.name}':  E2E = {e2e} us  (BCRT, WCRT)")


def _make_switches(s, prio_map):
    """Create two identical TSN_Resource switches with the given priority_mechanism_map."""
    kwargs = dict(
        priority_mechanism_map=prio_map,
        tas_cycle_time=CYCLE,
        tas_window_time_by_priority={7: WINDOW_7},
    )
    sw1 = s.bind_resource(model.TSN_Resource("Switch1", schedulers.TASScheduler(), **kwargs))
    sw2 = s.bind_resource(model.TSN_Resource("Switch2", schedulers.TASScheduler(), **kwargs))
    return sw1, sw2


def _add_flow(sw1, sw2, name, prio, make_path_in=None):
    """Add a two-hop flow (hop1 on sw1, hop2 on sw2) and optionally register a path.

    Returns (hop1, hop2).  If make_path_in is a System, a Path is also created.
    """
    hop1 = model.Task(f'{name}_h1', bcet=WCET, wcet=WCET, scheduling_parameter=prio)
    sw1.bind_task(hop1)
    hop1.in_event_model = model.PJdEventModel(P=PERIOD, J=0)

    hop2 = model.Task(f'{name}_h2', bcet=WCET, wcet=WCET, scheduling_parameter=prio)
    sw2.bind_task(hop2)

    hop1.link_dependent_task(hop2)

    if make_path_in is not None:
        make_path_in.bind_path(model.Path(f'{name}_path', [hop1, hop2]))

    return hop1, hop2


# =====================================================================
# Scenario 1.1 — Analyzed: TAS (prio 7) + lower-priority NST (prio 1)
# =====================================================================
def scenario_1_1():
    print("\n" + "=" * 70)
    print("Scenario 1.1: Analyzed=TAS(prio7) + lower-prio NST(prio1)")
    print("=" * 70)

    options.init_pycpa()
    s = model.System()
    sw1, sw2 = _make_switches(s, {7: 'TAS', 1: None})

    st_h1, st_h2 = _add_flow(sw1, sw2, 'ST', 7, make_path_in=s)
    _add_flow(sw1, sw2, 'NST_lo', 1)

    results = analysis.analyze_system(s)
    _print_results(s, results, [st_h1, st_h2])


# =====================================================================
# Scenario 1.2 — Analyzed: TAS (prio 7) + same-priority TAS (prio 7)
# =====================================================================
def scenario_1_2():
    print("\n" + "=" * 70)
    print("Scenario 1.2: Analyzed=TAS(prio7) + same-prio TAS(prio7)")
    print("=" * 70)

    options.init_pycpa()
    s = model.System()
    sw1, sw2 = _make_switches(s, {7: 'TAS'})

    st_h1, st_h2 = _add_flow(sw1, sw2, 'ST_a', 7, make_path_in=s)
    _add_flow(sw1, sw2, 'ST_b', 7)

    results = analysis.analyze_system(s)
    _print_results(s, results, [st_h1, st_h2])


# =====================================================================
# Scenario 2.1 — Analyzed: NST (prio 3) + TAS (prio 7) + lower NST (prio 1)
# =====================================================================
def scenario_2_1():
    print("\n" + "=" * 70)
    print("Scenario 2.1: Analyzed=NST(prio3) + TAS(prio7) + lower NST(prio1)")
    print("=" * 70)

    options.init_pycpa()
    s = model.System()
    sw1, sw2 = _make_switches(s, {7: 'TAS', 3: None, 1: None})

    nst_h1, nst_h2 = _add_flow(sw1, sw2, 'NST_mid', 3, make_path_in=s)
    _add_flow(sw1, sw2, 'ST', 7)
    _add_flow(sw1, sw2, 'NST_lo', 1)

    results = analysis.analyze_system(s)
    _print_results(s, results, [nst_h1, nst_h2])


# =====================================================================
# Scenario 2.2 — Analyzed: NST (prio 3) + TAS (prio 7) + same NST (prio 3)
# =====================================================================
def scenario_2_2():
    print("\n" + "=" * 70)
    print("Scenario 2.2: Analyzed=NST(prio3) + TAS(prio7) + same NST(prio3)")
    print("=" * 70)

    options.init_pycpa()
    s = model.System()
    sw1, sw2 = _make_switches(s, {7: 'TAS', 3: None})

    nst_h1, nst_h2 = _add_flow(sw1, sw2, 'NST_a', 3, make_path_in=s)
    _add_flow(sw1, sw2, 'ST', 7)
    _add_flow(sw1, sw2, 'NST_b', 3)

    results = analysis.analyze_system(s)
    _print_results(s, results, [nst_h1, nst_h2])


# =====================================================================
# Scenario 2.3 — Analyzed: NST (prio 3) + TAS (prio 7) + higher NST (prio 5)
# =====================================================================
def scenario_2_3():
    print("\n" + "=" * 70)
    print("Scenario 2.3: Analyzed=NST(prio3) + TAS(prio7) + higher NST(prio5)")
    print("=" * 70)

    options.init_pycpa()
    s = model.System()
    sw1, sw2 = _make_switches(s, {7: 'TAS', 5: None, 3: None})

    nst_h1, nst_h2 = _add_flow(sw1, sw2, 'NST_mid', 3, make_path_in=s)
    _add_flow(sw1, sw2, 'ST', 7)
    _add_flow(sw1, sw2, 'NST_hi', 5)

    results = analysis.analyze_system(s)
    _print_results(s, results, [nst_h1, nst_h2])


# =====================================================================
# Scenario 3 — Full mix: 4 TAS flows (2×prio7, 2×prio6) +
#              3 NST flows (prio5, prio3, prio1).  Analyze all 7 E2E.
# =====================================================================
def scenario_3():
    print("\n" + "=" * 70)
    print("Scenario 3: 4 TAS (2×prio7 + 2×prio6) + 3 NST (prio5, prio3, prio1)")
    print("=" * 70)

    options.init_pycpa()
    s = model.System()

    prio_map = {7: 'TAS', 6: 'TAS', 5: None, 3: None, 1: None}
    res_kwargs = dict(
        priority_mechanism_map=prio_map,
        tas_cycle_time=CYCLE,
        tas_window_time_by_priority={7: WINDOW_7, 6: 80},
    )
    sw1 = s.bind_resource(model.TSN_Resource("Switch1", schedulers.TASScheduler(), **res_kwargs))
    sw2 = s.bind_resource(model.TSN_Resource("Switch2", schedulers.TASScheduler(), **res_kwargs))

    # TAS flows
    st7a_h1, st7a_h2 = _add_flow(sw1, sw2, 'ST7a', 7, make_path_in=s)
    st7b_h1, st7b_h2 = _add_flow(sw1, sw2, 'ST7b', 7, make_path_in=s)
    st6a_h1, st6a_h2 = _add_flow(sw1, sw2, 'ST6a', 6, make_path_in=s)
    st6b_h1, st6b_h2 = _add_flow(sw1, sw2, 'ST6b', 6, make_path_in=s)

    # NST flows
    nst5_h1, nst5_h2 = _add_flow(sw1, sw2, 'NST5', 5, make_path_in=s)
    nst3_h1, nst3_h2 = _add_flow(sw1, sw2, 'NST3', 3, make_path_in=s)
    nst1_h1, nst1_h2 = _add_flow(sw1, sw2, 'NST1', 1, make_path_in=s)

    results = analysis.analyze_system(s)

    all_hops = [
        (st7a_h1, st7a_h2),
        (st7b_h1, st7b_h2),
        (st6a_h1, st6a_h2),
        (st6b_h1, st6b_h2),
        (nst5_h1, nst5_h2),
        (nst3_h1, nst3_h2),
        (nst1_h1, nst1_h2),
    ]

    print(f"\n  Resource config: cycle={CYCLE}, window_7={WINDOW_7}, window_6=80")
    print(f"  All flows: wcet={WCET}, period={PERIOD}, jitter=0\n")

    print("  Per-Hop Results:")
    print("  " + "-" * 66)
    print(f"  {'Flow':<10} {'Prio':>4} {'Mech':<5} {'Hop1 WCRT':>10} {'Hop2 WCRT':>10}")
    print("  " + "-" * 66)
    for h1, h2 in all_hops:
        r = h1.resource
        mech = r.get_mechanism_for_priority(h1.scheduling_parameter) or '-'
        name = h1.name.replace('_h1', '')
        print(f"  {name:<10} {h1.scheduling_parameter:>4} {mech:<5} {results[h1].wcrt:>10} {results[h2].wcrt:>10}")
    print("  " + "-" * 66)

    print("\n  End-to-End Path Results:")
    print("  " + "-" * 66)
    print(f"  {'Path':<16} {'BCRT':>10} {'WCRT':>10}")
    print("  " + "-" * 66)
    for p in s.paths:
        bcrt, wcrt = path_analysis.end_to_end_latency(p, results, 1)
        print(f"  {p.name:<16} {bcrt:>10} {wcrt:>10}")
    print("  " + "-" * 66)


# =====================================================================
if __name__ == "__main__":
    scenario_1_1()
    scenario_1_2()
    scenario_2_1()
    scenario_2_2()
    scenario_2_3()
    scenario_3()

    print("\n" + "=" * 70)
    print("All scenarios completed.")
    print("=" * 70)
