"""
Basic test for CQFPScheduler.

Sets up a simple scenario with 4 traffic classes (N+E, N+P, C+E, C+P)
on a single TSN switch port and verifies the analysis completes.
"""
import sys
sys.path.insert(0, '..')

from pycpa import model
from pycpa import analysis
from pycpa import schedulers_cqfp as cqfp
from pycpa import options

def cqfp_basic_test():
    options.init_pycpa()

    s = model.System("CQFP_Test")

    # Create TSN resource with CQF + Preemption configuration
    r = model.TSN_Resource(
        "Switch_Port1",
        cqfp.CQFPScheduler(),
        priority_mechanism_map={
            7: None,       # N+E (prio 7, non-CQF, express)
            6: None,       # N+P (prio 6, non-CQF, preemptable)
            (5, 4): 'CQF', # C+E (prio 5, CQF, express)
            (3, 2): 'CQF', # C+P (prio 3, CQF, preemptable)
        },
        cqf_cycle_time=500,  # 500 us
        cqf_cycle_time_by_pair={(5, 4): 500, (3, 2): 500},
        is_express_by_priority={
            7: True,
            6: False,
            5: True,
            4: True,
            3: False,
            2: False,
        },
    )
    s.bind_resource(r)

    # N+E stream (prio 7, highest)
    t_ne = model.Task("NE_flow", 0, 10, 7)
    t_ne.in_event_model = model.PJdEventModel(P=1000, J=0)
    r.bind_task(t_ne)

    # N+P stream (prio 6)
    t_np = model.Task("NP_flow", 0, 12, 6, payload=200)
    t_np.in_event_model = model.PJdEventModel(P=2000, J=0)
    r.bind_task(t_np)

    # C+E stream (prio 5)
    t_ce = model.Task("CE_flow", 0, 8, 5)
    t_ce.in_event_model = model.PJdEventModel(P=1000, J=0)
    r.bind_task(t_ce)

    # C+P stream (prio 3)
    t_cp = model.Task("CP_flow", 0, 15, 3, payload=300)
    t_cp.in_event_model = model.PJdEventModel(P=2000, J=0)
    r.bind_task(t_cp)

    print("=== CQFP Scheduler Test ===")
    print(f"CQF cycle time: 500 us")
    print(f"Link rate: 1 Gbps")
    print()

    # Verify traffic class detection
    for t in [t_ne, t_np, t_ce, t_cp]:
        uses_cqf, is_express = cqfp._get_traffic_class(t, r)
        tc_name = ("C" if uses_cqf else "N") + "+" + ("E" if is_express else "P")
        print(f"  {t.name}: prio={t.scheduling_parameter}, class={tc_name}, "
              f"CQF={uses_cqf}, express={is_express}")
    print()

    # Run analysis
    task_results = analysis.analyze_system(s)

    # Print results
    print("=== Analysis Results ===")
    for t in [t_ne, t_np, t_ce, t_cp]:
        print(f"  {t.name}: WCRT = {task_results[t].wcrt:.3f} us")

    print("\nTest PASSED - analysis completed successfully")
    return task_results

if __name__ == "__main__":
    cqfp_basic_test()
