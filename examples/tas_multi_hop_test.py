"""
TAS Multi-Hop E2E Validation — Flow End-to-End Latency

This example validates the E2E latency experienced by a TAS flow over multiple hops:
  - TAS E2E correction (TASSchedulerE2E + path.tas_aligned) tightens E2E vs raw sum(WCRT)
  - When TAS window is large enough, gate-closed blockings stay small
  - Uses classic path analysis (e2e_improved=False) so that TAS correction applies

Topology (N hops):
    Terminal  --->  [Switch1]  --->  [Switch2]  --->  ...  --->  [SwitchN]  --->  Terminal

Common parameters:
    Link speed     : 1 Gbps
    Frame size     : 1518 bytes  =>  wcet = bcet = 12 us
    TAS cycle time : 1000 us
    Period         : 1000 us, jitter = 0

Analysis based on:
    THIELE D, ERNST R, DIEMER J. Formal worst-case timing analysis of
    Ethernet TSN's time-aware and peristaltic shapers[C]//2015 IEEE
    Vehicular Networking Conference (VNC). Kyoto, Japan: IEEE, 2015: 251-258.

Scenarios:
==========
A   Increasing hops (2, 3, 4); TAS window = 100 us; tas_aligned = True
A2  Large TAS window (500 us): 2, 3, 4 hops; tas_aligned = True
B   Decreasing window: 2 hops; TAS window = 100, 80, 60, 40, 30 us; tas_aligned = False
B2  Decreasing window (2 hops) with aligned: TAS window = 100, 80, 60, 40, 30 us; tas_aligned = True
C   Increasing hops, unaligned: 2, 3, 4 hops; window = 100 us; tas_aligned = False
"""

import math
import logging

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


# ========================================
# Helper functions
# ========================================

def _ensure_classic_e2e():
    """Ensure classic E2E analysis method is used so TAS correction applies."""
    options.set_opt('e2e_improved', False)


def _make_switches_n(s, n_switches, prio_map, use_e2e_scheduler, tas_window_by_priority):
    """Create n_switches TSN_Resource with given priority map and TAS window(s).

    Args:
        s: System to bind resources to
        n_switches: Number of switches to create
        prio_map: Priority-mechanism mapping
        use_e2e_scheduler: If True, use TASSchedulerE2E (for E2E correction support)
        tas_window_by_priority: Per-priority TAS window time mapping

    Returns:
        List of TSN_Resource instances
    """
    sched_class = schedulers.TASSchedulerE2E if use_e2e_scheduler else schedulers.TASScheduler
    kwargs = dict(
        priority_mechanism_map=prio_map,
        tas_cycle_time=CYCLE,
        tas_window_time_by_priority=tas_window_by_priority,
    )
    switches = []
    for i in range(1, n_switches + 1):
        r = s.bind_resource(model.TSN_Resource("Switch%d" % i, sched_class(), **kwargs))
        switches.append(r)
    return switches


def _add_flow_n(switches, name, prio, make_path_in=None):
    """Add one flow over len(switches) hops; optionally register a Path. Returns list of tasks.

    Args:
        switches: List of switch resources
        name: Flow name prefix
        prio: Priority level
        make_path_in: Optional System to register the path

    Returns:
        List of task objects (one per hop)
    """
    tasks = []
    for i, res in enumerate(switches):
        t = model.Task("%s_h%d" % (name, i + 1), bcet=WCET, wcet=WCET, scheduling_parameter=prio)
        res.bind_task(t)
        if i == 0:
            t.in_event_model = model.PJdEventModel(P=PERIOD, J=0)
        tasks.append(t)
    for i in range(len(tasks) - 1):
        tasks[i].link_dependent_task(tasks[i + 1])
    if make_path_in is not None:
        make_path_in.bind_path(model.Path("%s_path" % name, tasks))
    return tasks


def _k_actual_from_spb(path_tasks, results, tas_aligned):
    """K_actual = sum over hops of ceil((spb+wcet)/tas_window), first hop 0 if aligned."""
    k = 0
    for j, t in enumerate(path_tasks):
        spb = getattr(results[t], 'same_priority_blocking', None)
        if spb is None:
            return None
        tas_window = t.resource.effective_tas_window_time(t.scheduling_parameter)
        count_j = int(math.floor((spb + t.wcet) / tas_window)) if tas_window > 0 else 0
        if j == 0 and tas_aligned:
            count_j = 0
        k += count_j
    return k


def _run_path_and_print(path_tasks, path, results, tas_aligned, scenario_label):
    """Compute and print E2E latency (corrected and raw); return for summary/assertions.

    Uses path from path_tasks[0].path so tas_aligned is the one we set.

    Args:
        path_tasks: List of tasks on the path
        path: Path object for E2E analysis
        results: Analysis results
        tas_aligned: TAS alignment flag
        scenario_label: Label for output

    Returns:
        Tuple of (e2e_corrected, e2e_raw, sum_wcrt)
    """
    sum_wcrt = sum(results[t].wcrt for t in path_tasks)
    delta_min = path_tasks[0].in_event_model.delta_min(1)
    # Use path from task so correction sees path.tas_aligned
    p = path_tasks[0].path
    lmin, lmax = path_analysis.end_to_end_latency(p, results, 1)
    e2e_corrected = lmax
    e2e_raw = sum_wcrt + delta_min
    print("  %s: hops=%d  E2E (corrected)=%d us  E2E (raw)=%d us  (sum_wcrt=%d us)"
          % (scenario_label, len(path_tasks), e2e_corrected, e2e_raw, sum_wcrt))
    return e2e_corrected, e2e_raw, sum_wcrt


# ========================================
# 2. Analysis scenario functions
# ========================================

# =====================================================================
# Scenario A: Increasing number of hops (2, 3, 4); window = 100 us; aligned
# =====================================================================
def scenario_a_increasing_hops():
    """Multi-hop: 2, 3, 4 hops; same TAS window 100 us. Focus: E2E latency grows with hops."""
    print("\n" + "=" * 70)
    print("Scenario A: Increasing hops (2, 3, 4); TAS window = 100 us; tas_aligned=True")
    print("=" * 70)

    tas_window = 100
    prio_map = {7: 'TAS'}
    window_by_prio = {7: tas_window}

    rows = []
    for n_hops in (2, 3, 4):
        options.init_pycpa()
        _ensure_classic_e2e()
        s = model.System()
        switches = _make_switches_n(s, n_hops, prio_map, use_e2e_scheduler=True, tas_window_by_priority=window_by_prio)
        path_tasks = _add_flow_n(switches, "ST", 7, make_path_in=s)
        path_tasks[0].path.tas_aligned = True

        results = analysis.analyze_system(s)
        assert all(getattr(results[t], 'gate_closed_duration', None) is not None for t in path_tasks), \
            "TASSchedulerE2E should set gate_closed_duration"
        label = "N=%d" % n_hops
        row = _run_path_and_print(path_tasks, path_tasks[0].path, results, True, label)
        rows.append((n_hops, row))

    # 2-hop aligned: correction applied so E2E (corrected) < E2E (raw)
    e2e_2_corrected, e2e_2_raw = rows[0][1][0], rows[0][1][1]
    assert e2e_2_corrected < e2e_2_raw, "2-hop aligned: E2E (corrected)=%d should be < E2E (raw)=%d" % (e2e_2_corrected, e2e_2_raw)
    print("\n  Summary — E2E latency (flow experiences):")
    for n_hops, (e2e_corrected, e2e_raw, sum_wcrt) in rows:
        print("    %d hops -> E2E (corrected)=%d us, E2E (raw)=%d us" % (n_hops, e2e_corrected, e2e_raw))
    for i in range(1, len(rows)):
        assert rows[i][1][0] >= rows[i - 1][1][0], "E2E (corrected) should increase with more hops"
        assert rows[i][1][1] >= rows[i - 1][1][1], "E2E (raw) should increase with more hops"
    print("  OK: Scenario A completed.")


# =====================================================================
# Scenario B: Decreasing TAS window (100, 80, 60, 40, 30 us); 2 hops; unaligned
# =====================================================================
def scenario_b_decreasing_window():
    """Two hops; TAS window 100, 80, 60, 40, 30 us. Focus: E2E latency as window shortens."""
    print("\n" + "=" * 70)
    print("Scenario B: Decreasing TAS window (100, 80, 60, 40, 30 us); 2 hops; tas_aligned=False")
    print("=" * 70)

    prio_map = {7: 'TAS'}
    n_hops = 2
    windows = (100, 80, 60, 40, 30)

    rows = []
    for tas_window in windows:
        options.init_pycpa()
        _ensure_classic_e2e()
        s = model.System()
        switches = _make_switches_n(s, n_hops, prio_map, use_e2e_scheduler=True,
                                    tas_window_by_priority={7: tas_window})
        path_tasks = _add_flow_n(switches, "ST", 7, make_path_in=s)
        path = path_tasks[0].path
        path.tas_aligned = False

        results = analysis.analyze_system(s)
        label = "W=%d" % tas_window
        row = _run_path_and_print(path_tasks, path, results, False, label)
        rows.append((tas_window, row))

    print("\n  Summary — E2E latency (flow experiences):")
    for tas_window, (e2e_corrected, e2e_raw, sum_wcrt) in rows:
        print("    window=%d us -> E2E (corrected)=%d us, E2E (raw)=%d us" % (tas_window, e2e_corrected, e2e_raw))
    for i in range(1, len(rows)):
        assert rows[i][1][0] >= rows[i - 1][1][0], "E2E (corrected) should increase as window shortens"
        assert rows[i][1][1] >= rows[i - 1][1][1], "E2E (raw) should increase as window shortens"
    print("  OK: Scenario B completed.")


# =====================================================================
# Scenario B2: Decreasing TAS window (100, 80, 60, 40, 30 us); 2 hops; aligned
# =====================================================================
def scenario_b2_decreasing_window_aligned():
    """Two hops; TAS window 100, 80, 60, 40, 30 us; tas_aligned=True. Focus: E2E with aligned schedule."""
    print("\n" + "=" * 70)
    print("Scenario B2: Decreasing TAS window (100, 80, 60, 40, 30 us); 2 hops; tas_aligned=True")
    print("=" * 70)

    prio_map = {7: 'TAS'}
    n_hops = 2
    windows = (100, 80, 60, 40, 30)

    rows = []
    for tas_window in windows:
        options.init_pycpa()
        _ensure_classic_e2e()
        s = model.System()
        switches = _make_switches_n(s, n_hops, prio_map, use_e2e_scheduler=True,
                                    tas_window_by_priority={7: tas_window})
        path_tasks = _add_flow_n(switches, "ST", 7, make_path_in=s)
        path = path_tasks[0].path
        path.tas_aligned = True

        results = analysis.analyze_system(s)
        label = "W=%d" % tas_window
        row = _run_path_and_print(path_tasks, path, results, True, label)
        rows.append((tas_window, row))

    print("\n  Summary — E2E latency (flow experiences, aligned):")
    for tas_window, (e2e_corrected, e2e_raw, sum_wcrt) in rows:
        print("    window=%d us -> E2E (corrected)=%d us, E2E (raw)=%d us" % (tas_window, e2e_corrected, e2e_raw))
    # Aligned: corrected E2E should be smaller than raw (correction effective)
    for tas_window, (e2e_corrected, e2e_raw, sum_wcrt) in rows:
        assert e2e_corrected < e2e_raw, "Aligned at window=%d: E2E (corrected)=%d should be < E2E (raw)=%d" % (
            tas_window, e2e_corrected, e2e_raw)
    print("  OK: Scenario B2 completed.")


# =====================================================================
# Scenario C: Increasing hops, unaligned (first hop sees gate-closed blocking)
# =====================================================================
def scenario_c_increasing_hops_unaligned():
    """Multi-hop 2, 3, 4 with window 100 us; tas_aligned=False. Focus: E2E latency with more hops."""
    print("\n" + "=" * 70)
    print("Scenario C: Increasing hops (2, 3, 4); window = 100 us; tas_aligned=False")
    print("=" * 70)

    tas_window = 100
    prio_map = {7: 'TAS'}
    window_by_prio = {7: tas_window}

    rows = []
    for n_hops in (2, 3, 4):
        options.init_pycpa()
        _ensure_classic_e2e()
        s = model.System()
        switches = _make_switches_n(s, n_hops, prio_map, use_e2e_scheduler=True, tas_window_by_priority=window_by_prio)
        path_tasks = _add_flow_n(switches, "ST", 7, make_path_in=s)
        path_tasks[0].path.tas_aligned = False

        results = analysis.analyze_system(s)
        row = _run_path_and_print(path_tasks, path_tasks[0].path, results, False, "N=%d" % n_hops)
        rows.append((n_hops, row))
    print("\n  Summary — E2E latency (flow experiences):")
    for n_hops, (e2e_corrected, e2e_raw, sum_wcrt) in rows:
        print("    %d hops -> E2E (corrected)=%d us, E2E (raw)=%d us" % (n_hops, e2e_corrected, e2e_raw))
    for i in range(1, len(rows)):
        assert rows[i][1][0] >= rows[i - 1][1][0], "E2E (corrected) should increase with more hops"
    print("  OK: Scenario C completed.")


# =====================================================================
# Scenario A2: Large TAS window (500 us) — E2E should not grow excessively with hops
# =====================================================================
def scenario_a2_large_window():
    """Large TAS window (500 us): 2, 3, 4 hops; tas_aligned=True.
    With large window, gate-closed blockings stay small, so E2E (corrected) stays moderate.
    """
    print("\n" + "=" * 70)
    print("Scenario A2: Large TAS window (500 us); 2, 3, 4 hops; tas_aligned=True")
    print("=" * 70)

    tas_window = 500
    prio_map = {7: 'TAS'}
    window_by_prio = {7: tas_window}

    rows = []
    for n_hops in (2, 3, 4):
        options.init_pycpa()
        _ensure_classic_e2e()
        s = model.System()
        switches = _make_switches_n(s, n_hops, prio_map, use_e2e_scheduler=True, tas_window_by_priority=window_by_prio)
        path_tasks = _add_flow_n(switches, "ST", 7, make_path_in=s)
        path_tasks[0].path.tas_aligned = True

        results = analysis.analyze_system(s)
        row = _run_path_and_print(path_tasks, path_tasks[0].path, results, True, "N=%d" % n_hops)
        rows.append((n_hops, row))

    print("\n  Summary — with large window, E2E (corrected) should stay moderate as hops increase:")
    for n_hops, (e2e_corrected, e2e_raw, sum_wcrt) in rows:
        print("    %d hops -> E2E (corrected)=%d us, E2E (raw)=%d us" % (n_hops, e2e_corrected, e2e_raw))
    # With large window, corrected E2E should be much smaller than raw (correction effective)
    assert rows[0][1][0] < rows[0][1][1], "2-hop: E2E (corrected) should be < E2E (raw)"
    print("  OK: Scenario A2 completed.")


# ========================================
# 3. Main function entry
# ========================================
if __name__ == "__main__":
    scenario_a_increasing_hops()
    scenario_a2_large_window()
    scenario_b_decreasing_window()
    scenario_b2_decreasing_window_aligned()
    scenario_c_increasing_hops_unaligned()
    print("\n" + "=" * 70)
    print("All multi-hop scenarios completed.")
    print("=" * 70)