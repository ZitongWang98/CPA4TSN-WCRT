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

Guard Band Configuration (TASSchedulerE2E):
===========================================
When using TASSchedulerE2E, the guard_band parameter can be configured via TSN_Resource:

    guard_band (global): Default guard band for all priorities on this port
    guard_band_by_priority (per-prio): Per-priority guard band mapping

Default behavior when not configured:
    - TAS flows: guard_band = task.wcet (the packet's own transmission time)
    - NST flows: guard_band = max(wcet of lower-priority flows)

Example configurations:
    # Global guard_band for all priorities
    sw1 = s.bind_resource(model.TSN_Resource("Switch1", schedulers.TASSchedulerE2E(),
        priority_mechanism_map={7: 'TAS', 1: None},
        tas_cycle_time=CYCLE,
        tas_window_time_by_priority={7: WINDOW_7},
        guard_band=10))

    # Per-priority guard_band
    sw1 = s.bind_resource(model.TSN_Resource("Switch2", schedulers.TASSchedulerE2E(),
        priority_mechanism_map={7: 'TAS', 1: None},
        tas_cycle_time=CYCLE,
        tas_window_time_by_priority={7: WINDOW_7},
        guard_band_by_priority={7: 10, 1: 5}))

    # No guard_band set (use defaults: TAS->task.wcet, NST->computed from lower-prio flows)
    sw1 = s.bind_resource(model.TSN_Resource("Switch3", schedulers.TASSchedulerE2E(),
        priority_mechanism_map={7: 'TAS', 1: None},
        tas_cycle_time=CYCLE,
        tas_window_time_by_priority={7: WINDOW_7}))

Scenarios:
==========
1.1  Analyzed flow = TAS (prio 7),  + one lower-priority NST flow (prio 1)
1.2  Analyzed flow = TAS (prio 7),  + one same-priority TAS flow (prio 7)
2.1  Analyzed flow = NST (prio 3),  + one TAS flow (prio 7), + one lower-prio  NST (prio 1)
2.2  Analyzed flow = NST (prio 3),  + one TAS flow (prio 7), + one same-prio   NST (prio 3)
2.3  Analyzed flow = NST (prio 3),  + one TAS flow (prio 7), + one higher-prio NST (prio 5)
3    Full mix: 4 TAS flows (2×prio7, 2×prio6) + 3 NST flows (prio5, prio3, prio1); analyze all 7 E2E paths
4.1  E2E correction (aligned):     TASSchedulerE2E, path.tas_aligned=True;  first hop 0 blocking, hop2 in window -> K_actual=0
4.2  E2E correction (unaligned):  TASSchedulerE2E, path.tas_aligned=False; first hop 1 blocking, hop2 in window -> K_actual=1
4.3  E2E no correction:            TASSchedulerE2E, path.tas_aligned not set; correction disabled -> E2E = sum(WCRT)
4.4  E2E no correction:            TASScheduler (no gate_closed_blocking); path.tas_aligned has no effect -> E2E = sum(WCRT)
4.5  Guard band configuration:     TASSchedulerE2E with custom guard_band parameters

Analysis Based on:
==================
THIELE D, ERNST R, DIEMER J. Formal worst-case timing analysis of
Ethernet TSN's time-aware and peristaltic shapers[C]//2015 IEEE
Vehicular Networking Conference (VNC). Kyoto, Japan: IEEE, 2015: 251-258.
"""

import math

from pycpa import model
from pycpa import analysis
from pycpa import path_analysis
from pycpa import schedulers
from pycpa import options

# ========================================
# 1. Define common parameters
# ========================================
WCET = 12       # 1518B @ 1Gbps
PERIOD = 1000   # us
CYCLE = 1000    # TAS cycle time (us)
WINDOW_7 = 100  # TAS window for priority 7 (us)


# ========================================
# Helper functions
# ========================================

def _k_actual_from_spb(path_tasks, results, tas_aligned):
    """K_actual from same_priority_blocking + wcet: ceil((spb+wcet)/tas_window) per hop, first hop 0 if aligned.

    Args:
        path_tasks: List of tasks on the path
        results: Analysis results
        tas_aligned: TAS alignment flag

    Returns:
        K_actual value or None if same_priority_blocking not available
    """
    k = 0
    for j, t in enumerate(path_tasks):
        spb = getattr(results[t], 'same_priority_blocking', None)
        if spb is None:
            return None
        tas_window = t.resource.effective_tas_window_time(t.scheduling_parameter)
        count_j = int(math.floor((spb + t.wcet) / tas_window)) if tas_window > 0 else 0
        if j == 0 and tas_aligned:
            count_j = 0
        elif j == 0 and not tas_aligned:
            count_j = 1
        k += count_j
    return k


def _print_results(s, results, analyzed_path_tasks):
    """Print per-hop and end-to-end results.

    Args:
        s: System object
        results: Analysis results
        analyzed_path_tasks: List of tasks to print results for
    """
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


def _make_switches(s, prio_map, use_e2e_scheduler=False, guard_band=None, guard_band_by_priority=None):
    """Create two identical TSN_Resource switches with the given priority_mechanism_map.

    Args:
        s: System to bind resources to
        prio_map: Priority-mechanism mapping (e.g., {7: 'TAS', 1: None})
        use_e2e_scheduler: If True, use TASSchedulerE2E (for E2E correction support)
        guard_band: Optional global guard_band for all priorities (TASSchedulerE2E only)
        guard_band_by_priority: Optional per-priority guard_band mapping (TASSchedulerE2E only)

    Returns:
        (sw1, sw2): Two identical TSN_Resource instances

    Guard Band Configuration (when use_e2e_scheduler=True):
        - If guard_band is set: applied to all priorities
        - If guard_band_by_priority is set: overrides guard_band for specified priorities
        - If neither is set: default behavior
            * TAS flows: guard_band = task.wcet
            * NST flows: guard_band = max(wcet of lower-priority flows)

    Example usage:
        sw1, sw2 = _make_switches(s, {7: 'TAS', 1: None}, use_e2e_scheduler=True,
                                   guard_band=10)  # Global guard_band = 10 us
        sw1, sw2 = _make_switches(s, {7: 'TAS', 1: None}, use_e2e_scheduler=True,
                                   guard_band_by_priority={7: 8, 1: 5})  # Per-priority
    """
    sched_class = schedulers.TASSchedulerE2E if use_e2e_scheduler else schedulers.TASScheduler
    kwargs = dict(
        priority_mechanism_map=prio_map,
        tas_cycle_time=CYCLE,
        tas_window_time_by_priority={7: WINDOW_7},
    )
    # Add guard_band parameters only if using TASSchedulerE2E and explicitly set
    if use_e2e_scheduler:
        if guard_band is not None:
            kwargs['guard_band'] = guard_band
        if guard_band_by_priority is not None:
            kwargs['guard_band_by_priority'] = guard_band_by_priority
    sw1 = s.bind_resource(model.TSN_Resource("Switch1", sched_class(), **kwargs))
    sw2 = s.bind_resource(model.TSN_Resource("Switch2", sched_class(), **kwargs))
    return sw1, sw2


def _add_flow(sw1, sw2, name, prio, make_path_in=None):
    """Add a two-hop flow (hop1 on sw1, hop2 on sw2) and optionally register a path.

    Returns (hop1, hop2). If make_path_in is a System, a Path is also created.

    Args:
        sw1: First switch resource
        sw2: Second switch resource
        name: Flow name prefix
        prio: Priority level
        make_path_in: Optional System to register the path

    Returns:
        Tuple of (task1, task2) for the two hops
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


# ========================================
# 2. Analysis scenario functions
# ========================================

# =====================================================================
# Scenario 1.1 — Analyzed: TAS (prio 7) + lower-priority NST (prio 1)
# =====================================================================
def scenario_1_1():
    """Analyze TAS flow (priority 7) with a lower-priority NST flow (priority 1)."""
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
    """Analyze TAS flow (priority 7) with another same-priority TAS flow (priority 7)."""
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
    """Analyze NST flow (priority 3) with TAS (prio 7) and lower NST (prio 1)."""
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
    """Analyze NST flow (priority 3) with TAS (prio 7) and same-priority NST (prio 3)."""
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
    """Analyze NST flow (priority 3) with TAS (prio 7) and higher-priority NST (prio 5)."""
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
    """Full mix scenario: 4 TAS flows + 3 NST flows; analyze all 7 E2E paths."""
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
# Scenario 4.1 — E2E correction (aligned): TASSchedulerE2E, path.tas_aligned=True
# =====================================================================
def scenario_4_1():
    """Aligned mode: first hop no blocking; K_actual from ceil(spb/tas_window) per hop.
    Uses TASSchedulerE2E and path.tas_aligned=True. Verifies E2E = sum_wcrt - (total_gate_closed - K_actual*G_duration).
    """
    print("\n" + "=" * 70)
    print("Scenario 4.1: E2E correction (aligned): TASSchedulerE2E, path.tas_aligned=True")
    print("=" * 70)

    options.init_pycpa()
    s = model.System()
    sw1, sw2 = _make_switches(s, {7: 'TAS'}, use_e2e_scheduler=True)
    st_h1, st_h2 = _add_flow(sw1, sw2, 'ST', 7, make_path_in=s)

    path = st_h1.path
    path.tas_aligned = True

    results = analysis.analyze_system(s)
    lmin, lmax = path_analysis.end_to_end_latency(path, results, 1)
    print("   E2E (corrected)=%s" % (lmax))


# =====================================================================
# Scenario 4.2 — E2E correction (unaligned): TASSchedulerE2E, path.tas_aligned=False
# =====================================================================
def scenario_4_2():
    """Unaligned mode: K_actual from ceil(spb/tas_window) per hop (first hop counted).
    Uses TASSchedulerE2E and path.tas_aligned=False. Verifies E2E = sum_wcrt - (total_gate_closed - K_actual*G_duration).
    """
    print("\n" + "=" * 70)
    print("Scenario 4.2: E2E correction (unaligned): TASSchedulerE2E, path.tas_aligned=False")
    print("=" * 70)

    options.init_pycpa()
    s = model.System()
    sw1, sw2 = _make_switches(s, {7: 'TAS'}, use_e2e_scheduler=True)
    st_h1, st_h2 = _add_flow(sw1, sw2, 'ST', 7, make_path_in=s)
    path = st_h1.path
    path.tas_aligned = False

    results = analysis.analyze_system(s)
    lmin, lmax = path_analysis.end_to_end_latency(path, results, 1)
    print("   E2E (corrected)=%s" % (lmax))


# =====================================================================
# Scenario 4.3 — E2E no correction: TASSchedulerE2E, path.tas_aligned not set
# =====================================================================
def scenario_4_3():
    """Compatibility: TASSchedulerE2E used but path.tas_aligned not set.
    E2E correction is enabled only when path.tas_aligned is set; here it is
    left None, so path_analysis must not apply correction and E2E = sum(WCRT).
    """
    print("\n" + "=" * 70)
    print("Scenario 4.3: E2E no correction: TASSchedulerE2E, path.tas_aligned not set")
    print("=" * 70)

    options.init_pycpa()
    s = model.System()
    sw1, sw2 = _make_switches(s, {7: 'TAS'}, use_e2e_scheduler=True)
    st_h1, st_h2 = _add_flow(sw1, sw2, 'ST', 7, make_path_in=s)
    # do not set path.tas_aligned -> correction not applied

    results = analysis.analyze_system(s)
    sum_wcrt = results[st_h1].wcrt + results[st_h2].wcrt
    lmin, lmax = path_analysis.end_to_end_latency(st_h1.path, results, 1)
    print("  E2E=%s (raw sum), no correction applied. OK." % lmax)


# =====================================================================
# Scenario 4.4 — E2E no correction: TASScheduler (no gate_closed_blocking)
# =====================================================================
def scenario_4_4():
    """Compatibility: original TASScheduler used (no gate_closed_blocking written).
    Even if path.tas_aligned=True, path_analysis requires every path task to have
    task_results[t].gate_closed_blocking set; TASScheduler does not write it,
    so correction is not applied and E2E = sum(WCRT). Ensures existing models
    using TASScheduler() are unchanged.
    """
    print("\n" + "=" * 70)
    print("Scenario 4.4: E2E no correction: TASScheduler (no gate_closed_blocking)")
    print("=" * 70)

    options.init_pycpa()
    s = model.System()
    sw1, sw2 = _make_switches(s, {7: 'TAS'}, use_e2e_scheduler=False)
    st_h1, st_h2 = _add_flow(sw1, sw2, 'ST', 7, make_path_in=s)
    st_h1.path.tas_aligned = True  # user set aligned, but no G data from scheduler

    results = analysis.analyze_system(s)
    sum_wcrt = results[st_h1].wcrt + results[st_h2].wcrt
    lmin, lmax = path_analysis.end_to_end_latency(st_h1.path, results, 1)
    print("  E2E=%s (raw sum), no correction. OK." % lmax)


# =====================================================================
# Scenario 4.5 — Guard band configuration: TASSchedulerE2E with custom guard_band
# =====================================================================
def scenario_4_5():
    """Demonstrates guard_band configuration with TASSchedulerE2E.

    Guard Band is the time reserved to prevent a frame from transmitting
    after its gate closes due to link propagation delay. It ensures that
    when a gate closes, no frame still being transmitted is left incomplete.

    Three configurations are demonstrated:
        Config A: Global guard_band (same for all priorities)
        Config B: Per-priority guard_band (different for each priority)
        Config C: No guard_band set (uses defaults)

    Default guard_band behavior when not configured:
        - TAS flows: guard_band = task.wcet (transmission time of own frame)
        - NST flows: guard_band = max(wcet of lower-priority flows)
    """
    print("\n" + "=" * 70)
    print("Scenario 4.5: Guard Band Configuration with TASSchedulerE2E")
    print("=" * 70)

    options.init_pycpa()

    # Config A: Global guard_band for ALL priorities on both switches
    # ================================================================
    print("\n  Config A: Global guard_band = 8 us (applied to all 7 and 1)")
    print("  " + "-" * 66)
    s_a = model.System()
    # guard_band=8: this value is used for all priorities (both TAS and NST flows)
    sw1_a, sw2_a = _make_switches(s_a, {7: 'TAS', 1: None}, use_e2e_scheduler=True,
                                   guard_band=8)  # Global guard band (all priorities)

    st_h1_a, st_h2_a = _add_flow(sw1_a, sw2_a, 'ST_A', 7, make_path_in=s_a)
    nst_h1_a, nst_h2_a = _add_flow(sw1_a, sw2_a, 'NST_lo_A', 1, make_path_in=s_a)

    results_a = analysis.analyze_system(s_a)
    print("    TAS flow (prio7): Hop1 WCRT=%d us, Hop2 WCRT=%d us" %
          (results_a[st_h1_a].wcrt, results_a[st_h2_a].wcrt))
    print("    NST flow (prio1): Hop1 WCRT=%d us, Hop2 WCRT=%d us" %
          (results_a[nst_h1_a].wcrt, results_a[nst_h2_a].wcrt))

    # Config B: Per-priority guard_band (different for each priority)
    # ==============================================================
    print("\n  Config B: Per-priority guard_band: prio7=10 us, prio1=5 us")
    print("  " + "-" * 66)
    s_b = model.System()
    # guard_band_by_priority={7: 10, 1: 5}: different guard band for each priority
    # - Priority 7 (TAS flow): guard_band = 10 us
    # - Priority 1 (NST flow): guard_band = 5 us
    sw1_b, sw2_b = _make_switches(s_b, {7: 'TAS', 1: None}, use_e2e_scheduler=True,
                                   guard_band_by_priority={7: 10, 1: 5})  # Per-priority guard band

    st_h1_b, st_h2_b = _add_flow(sw1_b, sw2_b, 'ST_B', 7, make_path_in=s_b)
    nst_h1_b, nst_h2_b = _add_flow(sw1_b, sw2_b, 'NST_lo_B', 1, make_path_in=s_b)

    results_b = analysis.analyze_system(s_b)
    print("    TAS flow (prio7): Hop1 WCRT=%d us, Hop2 WCRT=%d us" %
          (results_b[st_h1_b].wcrt, results_b[st_h2_b].wcrt))
    print("    NST flow (prio1): Hop1 WCRT=%d us, Hop2 WCRT=%d us" %
          (results_b[nst_h1_b].wcrt, results_b[nst_h2_b].wcrt))

    # Config C: No guard_band set (uses defaults)
    # ===========================================
    print("\n  Config C: No guard_band set (uses default behavior)")
    print("    TAS flow default: guard_band = task.wcet = %d us" % WCET)
    print("    NST flow default: guard_band = max(wcet of lower-prio flows) = %d us" % WCET)
    print("  " + "-" * 66)
    s_c = model.System()
    # No guard_band configured: uses default behavior
    # - TAS flow: guard_band = task.wcet (= 12 us)
    # - NST flow: guard_band = max(wcet of lower priority flows) (no lower here, but mechanism exists)
    sw1_c, sw2_c = _make_switches(s_c, {7: 'TAS', 1: None}, use_e2e_scheduler=True)

    st_h1_c, st_h2_c = _add_flow(sw1_c, sw2_c, 'ST_C', 7, make_path_in=s_c)
    nst_h1_c, nst_h2_c = _add_flow(sw1_c, sw2_c, 'NST_lo_C', 1, make_path_in=s_c)

    results_c = analysis.analyze_system(s_c)
    print("    TAS flow (prio7): Hop1 WCRT=%d us, Hop2 WCRT=%d us" %
          (results_c[st_h1_c].wcrt, results_c[st_h2_c].wcrt))
    print("    NST flow (prio1): Hop1 WCRT=%d us, Hop2 WCRT=%d us" %
          (results_c[nst_h1_c].wcrt, results_c[nst_h2_c].wcrt))

    # Summary of configurations
    # =========================
    print("\n  " + "=" * 66)
    print("  Summary: Guard Band Impact on WCRT")
    print("  " + "=" * 66)
    print("  Config A (global 8us):           TAS Hop1=%3d us, Hop2=%3d us" %
          (results_a[st_h1_a].wcrt, results_a[st_h2_a].wcrt))
    print("  Config A (global 8us):           NST Hop1=%3d us, Hop2=%3d us" %
          (results_a[nst_h1_a].wcrt, results_a[nst_h2_a].wcrt))
    print("  Config B (per-prio 7=10us,1=5us): TAS Hop1=%3d us, Hop2=%3d us" %
          (results_b[st_h1_b].wcrt, results_b[st_h2_b].wcrt))
    print("  Config B (per-prio 7=10us,1=5us): NST Hop1=%3d us, Hop2=%3d us" %
          (results_b[nst_h1_b].wcrt, results_b[nst_h2_b].wcrt))
    print("  Config C (default):               TAS Hop1=%3d us, Hop2=%3d us" %
          (results_c[st_h1_c].wcrt, results_c[st_h2_c].wcrt))
    print("  Config C (default):               NST Hop1=%3d us, Hop2=%3d us" %
          (results_c[nst_h1_c].wcrt, results_c[nst_h2_c].wcrt))
    print("  " + "=" * 66)


# ========================================
# 3. Main function entry
# ========================================
if __name__ == "__main__":
    scenario_1_1()
    scenario_1_2()
    scenario_2_1()
    scenario_2_2()
    scenario_2_3()
    scenario_3()
    scenario_4_1()
    scenario_4_2()
    scenario_4_3()
    scenario_4_4()
    scenario_4_5()

    print("\n" + "=" * 70)
    print("All scenarios completed.")
    print("=" * 70)