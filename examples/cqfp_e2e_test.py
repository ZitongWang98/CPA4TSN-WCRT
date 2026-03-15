"""
CQF E2E multi-hop correction test.

Verifies that CQFPSchedulerE2E + path_analysis produces:
    E2E = (N-1) * T_CQF + WCRT_last_hop

based on Thesis Eq.(3.31).

Topology (3-hop):
    Terminal --> [SW1] --> [SW2] --> [SW3] --> Terminal

All switches have identical CQF+Preemption configuration.
"""
import sys
sys.path.insert(0, '..')

from pycpa import model
from pycpa import analysis
from pycpa import path_analysis
from pycpa import schedulers_cqfp as cqfp
from pycpa import options

T_CQF = 500   # CQF cycle time (us)
PERIOD = 2000  # flow period (us)
N_HOPS = 3


def make_switch(system, name, scheduler_cls):
    """Create a TSN switch with CQF+Preemption config."""
    r = model.TSN_Resource(
        name, scheduler_cls(),
        priority_mechanism_map={
            7: None,        # N+E
            (5, 4): 'CQF',  # C+E
            (3, 2): 'CQF',  # C+P
        },
        cqf_cycle_time=T_CQF,
        cqf_cycle_time_by_pair={(5, 4): T_CQF, (3, 2): T_CQF},
        is_express_by_priority={7: True, 5: True, 4: True, 3: False, 2: False},
    )
    system.bind_resource(r)
    return r


def run_scenario(scheduler_cls, label):
    """Run 3-hop analysis for a C+E flow and return (per-hop WCRTs, E2E)."""
    options.init_pycpa()
    s = model.System(label)

    switches = [make_switch(s, f"SW{i+1}", scheduler_cls) for i in range(N_HOPS)]

    # C+E flow (prio 5) traversing all 3 hops
    tasks = []
    for i, sw in enumerate(switches):
        t = model.Task(f"CE_hop{i+1}", 0, 8, 5)
        sw.bind_task(t)
        tasks.append(t)

    # Add a same-priority interferer on each switch
    for i, sw in enumerate(switches):
        ti = model.Task(f"CE_intf_hop{i+1}", 0, 6, 5)
        ti.in_event_model = model.PJdEventModel(P=PERIOD, J=0)
        sw.bind_task(ti)

    # Add a higher-priority N+E interferer on each switch
    for i, sw in enumerate(switches):
        th = model.Task(f"NE_hp_hop{i+1}", 0, 10, 7)
        th.in_event_model = model.PJdEventModel(P=PERIOD, J=0)
        sw.bind_task(th)

    # Link tasks into a chain
    tasks[0].in_event_model = model.PJdEventModel(P=PERIOD, J=0)
    for i in range(len(tasks) - 1):
        tasks[i].link_dependent_task(tasks[i + 1])

    # Create path
    p = model.Path("CE_path", tasks)
    s.bind_path(p)

    # Analyze
    task_results = analysis.analyze_system(s)

    # Collect per-hop WCRT
    hop_wcrts = [task_results[t].wcrt for t in tasks]

    # E2E
    _, e2e = path_analysis.end_to_end_latency(p, task_results, n=1)

    return hop_wcrts, e2e


def test_cqf_e2e():
    print("=" * 60)
    print("CQF E2E Multi-Hop Correction Test")
    print("=" * 60)
    print(f"T_CQF = {T_CQF} us, N_HOPS = {N_HOPS}, Period = {PERIOD} us")
    print()

    # --- Baseline: CQFPScheduler (no E2E correction) ---
    wcrts_base, e2e_base = run_scenario(cqfp.CQFPScheduler, "Baseline")
    print(f"[Baseline] CQFPScheduler (no E2E correction):")
    for i, w in enumerate(wcrts_base):
        print(f"  Hop {i+1} WCRT = {w:.3f} us")
    print(f"  E2E (sum of WCRT) = {e2e_base:.3f} us")
    print()

    # --- E2E: CQFPSchedulerE2E ---
    wcrts_e2e, e2e_corrected = run_scenario(cqfp.CQFPSchedulerE2E, "E2E")
    print(f"[E2E] CQFPSchedulerE2E (with correction):")
    for i, w in enumerate(wcrts_e2e):
        print(f"  Hop {i+1} WCRT = {w:.3f} us")
    print(f"  E2E (corrected)   = {e2e_corrected:.3f} us")
    print()

    # --- Verify ---
    # Per-hop WCRT should be identical (same local analysis)
    for i in range(N_HOPS):
        assert wcrts_base[i] == wcrts_e2e[i], \
            f"Hop {i+1} WCRT mismatch: {wcrts_base[i]} vs {wcrts_e2e[i]}"

    # E2E correction formula: N*T_CQF + (WCRT_last - T_CQF)  [Thesis Eq.(3.29)-(3.31)]
    last_hop_wcrt = wcrts_e2e[-1]
    expected_e2e = N_HOPS * T_CQF + (last_hop_wcrt - T_CQF)
    print(f"[Verify] Expected E2E = {N_HOPS}*{T_CQF} + ({last_hop_wcrt:.3f} - {T_CQF}) = {expected_e2e:.3f} us")
    print(f"         Actual E2E   = {e2e_corrected:.3f} us")
    print(f"         Baseline E2E = {e2e_base:.3f} us")
    print(f"         Savings      = {e2e_base - e2e_corrected:.3f} us ({(e2e_base - e2e_corrected)/e2e_base*100:.1f}%)")

    assert abs(e2e_corrected - expected_e2e) < 0.001, \
        f"E2E mismatch: got {e2e_corrected}, expected {expected_e2e}"

    # Corrected should be <= baseline
    assert e2e_corrected <= e2e_base + 0.001, \
        f"Corrected E2E ({e2e_corrected}) > baseline ({e2e_base})"

    print()
    print("=" * 60)
    print("Test PASSED")
    print("=" * 60)


if __name__ == "__main__":
    test_cqf_e2e()
