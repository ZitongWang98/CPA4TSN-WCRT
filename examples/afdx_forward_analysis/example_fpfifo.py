#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AFDX FP/FIFO Forward Analysis Example — Paper 2 Case Study
============================================================

Reproduces the case study from:
  Benammar N, Ridouard F, Bauer H, et al.
  "Forward end-to-end delay analysis extension for FP/FIFO policy
   in AFDX networks"[C]//2017 22nd IEEE International Conference on
  Emerging Technologies and Factory Automation (ETFA). IEEE, 2017: 1-8.

Network topology (Fig. 1):

    ES1 ──► S1 ──► S4 ──► S6 ──► ES6
                └──► S5 ──► ES5
    ES2 ──► S2 ──► S5 ──► ES5
                │       └──► S6 ──► ES6
                └──► S4 ──► S6 ──► ES6
    ES3 ──► S2 (same as above)
    ES4 ──► S3 ──► S5 ──► ES5
                │       └──► S6 ──► ES6
                └──► S6 ──► ES6

Table I — Flow parameters:
    v1: C=10us, T=100us, Priority=1, path: ES1→S1→S4→S6→ES6
    v2: C=10us, T=60us,  Priority=1, path: ES1→S1→S5→ES5
    v3: C=10us, T=60us,  Priority=2, multicast:
        v3_ES5: ES2→S2→S5→ES5
        v3_ES6: ES2→S2→S5→S6→ES6
    v4: C=20us, T=80us,  Priority=3, path: ES3→S2→S5→ES5
    v5: C=20us, T=60us,  Priority=1, path: ES3→S2→S4→S6→ES6
    v6: C=10us, T=80us,  Priority=2, path: ES4→S3→S5→S6→ES6
    v7: C=10us, T=100us, Priority=2, path: ES4→S3→S5→ES5
    v8: C=20us, T=80us,  Priority=1, path: ES4→S3→S6→ES6

Link rate: 100 Mbit/s
Technological latency: 16us per switch

Table II — Expected end-to-end delays (at last queue):
    Without serialization (Theorem 2):
        v1_ES6 @ S6→ES6: 168us
        v2_ES5 @ S5→ES5:  92us
        v3_ES5 @ S5→ES5: 122us
        v3_ES6 @ S6→ES6: 288us
        v4_ES5 @ S5→ES5: 152us
        v5_ES6 @ S6→ES6: 198us
        v6_ES6 @ S6→ES6: 308us
        v7_ES5 @ S5→ES5: 142us
        v8_ES6 @ S6→ES6: 142us

    With serialization (Theorem 4):
        v1_ES6 @ S6→ES6: 158us
        v2_ES5 @ S5→ES5:  92us
        v3_ES5 @ S5→ES5: 122us
        v3_ES6 @ S6→ES6: 278us
        v4_ES5 @ S5→ES5: 152us
        v5_ES6 @ S6→ES6: 188us
        v6_ES6 @ S6→ES6: 288us
        v7_ES5 @ S5→ES5: 132us
        v8_ES6 @ S6→ES6: 132us
"""

from pycpa import model
from forward_analysis import FPFIFOForwardAnalyzer


# ---------------------------------------------------------------------------
# Flow definitions from Table I
# ---------------------------------------------------------------------------
# (base_name, C_us, T_us, priority)
FLOW_TABLE = {
    "v1": (10, 100, 1),
    "v2": (10,  60, 1),
    "v3": (10,  60, 2),
    "v4": (20,  80, 3),
    "v5": (20,  60, 1),
    "v6": (10,  80, 2),
    "v7": (10, 100, 2),
    "v8": (20,  80, 1),
}

# (flow_instance_name, base_vl_key, node_path)
FLOW_SPECS = [
    ("v1_ES6", "v1", ["ES1", "S1", "S4", "S6", "ES6"]),
    ("v2_ES5", "v2", ["ES1", "S1", "S5", "ES5"]),
    ("v3_ES5", "v3", ["ES2", "S2", "S5", "ES5"]),
    ("v3_ES6", "v3", ["ES2", "S2", "S5", "S6", "ES6"]),
    ("v4_ES5", "v4", ["ES3", "S2", "S5", "ES5"]),
    ("v5_ES6", "v5", ["ES3", "S2", "S4", "S6", "ES6"]),
    ("v6_ES6", "v6", ["ES4", "S3", "S5", "S6", "ES6"]),
    ("v7_ES5", "v7", ["ES4", "S3", "S5", "ES5"]),
    ("v8_ES6", "v8", ["ES4", "S3", "S6", "ES6"]),
]

TECH_LATENCY = 16.0   # us per switch
LINK_RATE = 100.0      # Mbit/s (used to derive C from frame size)

# Expected results from Table II  (flow_instance, last_queue) -> e2e delay (us)
EXPECTED_NO_SER = {
    ("v1_ES6", "S6->ES6"): 168,
    ("v2_ES5", "S5->ES5"):  92,
    ("v3_ES5", "S5->ES5"): 122,
    ("v3_ES6", "S6->ES6"): 288,
    ("v4_ES5", "S5->ES5"): 152,
    ("v5_ES6", "S6->ES6"): 198,
    ("v6_ES6", "S6->ES6"): 308,
    ("v7_ES5", "S5->ES5"): 142,
    ("v8_ES6", "S6->ES6"): 142,
}

EXPECTED_SER = {
    ("v1_ES6", "S6->ES6"): 158,
    ("v2_ES5", "S5->ES5"):  92,
    ("v3_ES5", "S5->ES5"): 122,
    ("v3_ES6", "S6->ES6"): 278,
    ("v4_ES5", "S5->ES5"): 152,
    ("v5_ES6", "S6->ES6"): 188,
    ("v6_ES6", "S6->ES6"): 288,
    ("v7_ES5", "S5->ES5"): 132,
    ("v8_ES6", "S6->ES6"): 132,
}


# ---------------------------------------------------------------------------
# Helper: edge name
# ---------------------------------------------------------------------------
def _edge(a, b):
    """Return the queue/resource name for the link from node a to node b."""
    return f"{a}->{b}"


def _node_path_to_edges(node_path):
    """Convert a node-level path [ES1, S1, S4, ...] to edge-level path."""
    return [_edge(node_path[i], node_path[i + 1]) for i in range(len(node_path) - 1)]


# ---------------------------------------------------------------------------
# Build the Paper 2 case study using pycpa model objects
# ---------------------------------------------------------------------------
def build_paper2_case_study():
    """Build the Paper 2 AFDX network using pycpa model objects.

    Each directed edge (e.g. ES1→S1, S1→S4) is modelled as a pycpa Resource
    (representing the output queue of the source node towards the destination).
    Each flow's hop at an edge becomes a pycpa Task bound to that Resource.

    Returns:
        Tuple of (system, paths_dict) where paths_dict maps flow instance
        name (e.g. "v1_ES6") to the corresponding pycpa Path object.
    """
    system = model.System("Paper2_AFDX")

    # --- Collect all edges and create Resources ---
    all_edges = set()
    for _, _, node_path in FLOW_SPECS:
        for edge in _node_path_to_edges(node_path):
            all_edges.add(edge)

    resources = {}
    for edge_name in sorted(all_edges):
        r = model.Resource(edge_name)
        r.forwarding_delay = TECH_LATENCY
        system.bind_resource(r)
        resources[edge_name] = r

    # --- Create Tasks and Paths for each flow instance ---
    # For multicast VLs (same base_key), share Task objects on common
    # path segments so the analyzer counts them as one physical flow.
    # Key: (base_key, edge_name) -> Task
    shared_tasks = {}

    paths = {}
    for flow_name, base_key, node_path in FLOW_SPECS:
        C, T, prio = FLOW_TABLE[base_key]
        edge_path = _node_path_to_edges(node_path)

        tasks = []
        for hop_idx, edge_name in enumerate(edge_path):
            key = (base_key, edge_name)
            if key in shared_tasks:
                # Reuse existing task for multicast shared segment
                t = shared_tasks[key]
            else:
                task_name = f"{base_key}@{edge_name}"
                t = model.Task(task_name, bcet=C, wcet=C, scheduling_parameter=prio)
                resources[edge_name].bind_task(t)
                t.in_event_model = model.PJdEventModel(P=T, J=0)
                shared_tasks[key] = t

            # Link to previous task for serialization detection
            if tasks:
                prev_t = tasks[-1]
                # Only link if not already linked
                if t not in prev_t.next_tasks:
                    prev_t.link_dependent_task(t)

            tasks.append(t)

        p = model.Path(flow_name, tasks)
        system.bind_path(p)
        paths[flow_name] = p

    return system, paths


# ---------------------------------------------------------------------------
# Result comparison with paper Table II
# ---------------------------------------------------------------------------
def compare_with_paper(results, paths, expected, label):
    """Compare analysis results against expected paper values.

    Args:
        results: Dict[Path, AnalysisResult] from the analyzer.
        paths: Dict mapping flow name to Path.
        expected: Dict mapping (flow_name, last_queue) to expected e2e delay.
        label: Description string for this comparison.

    Returns:
        True if all results match within tolerance.
    """
    print(f"\n{label}:")
    print(f"  {'Flow':<14} {'Last queue':<14} {'FA (us)':>10} {'Expected':>10} {'Match':>8}")
    print("  " + "-" * 58)

    all_ok = True
    for (flow_name, last_queue), exp_val in sorted(expected.items()):
        path = paths[flow_name]
        result = results[path]
        computed = result.e2e_wcrt
        diff = abs(computed - exp_val)
        pct = diff / exp_val * 100 if exp_val else 0
        status = "OK" if diff < 0.5 else f"{pct:.1f}%"
        if diff >= 0.5:
            all_ok = False
        print(f"  {flow_name:<14} {last_queue:<14} {computed:>10.2f} {exp_val:>10} {status:>8}")

    print()
    if all_ok:
        print(f"  ALL MATCH for {label}")
    else:
        print(f"  SOME MISMATCHES for {label}")
    return all_ok


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    """Run the Paper 2 case study and compare with expected results."""
    print("=" * 70)
    print("Paper 2: FA extension for FP/FIFO policy in AFDX networks")
    print("Benammar et al., IEEE, 2017")
    print("=" * 70)
    print()

    # Build the network
    system, paths = build_paper2_case_study()
    print(f"Network: {len(system.resources)} queues (edges), "
          f"{len(system.paths)} flow paths")
    print()

    # --- Theorem 2: no serialization ---
    print("Computing FA-FP/FIFO (Theorem 2, no serialization)...")
    analyzer1 = FPFIFOForwardAnalyzer(system)
    results_no_ser = analyzer1.analyze_all(with_serialization=False)
    analyzer1.print_results(results_no_ser)

    ok1 = compare_with_paper(results_no_ser, paths, EXPECTED_NO_SER,
                             "FA-FP/FIFO (Theorem 2, no serialization)")

    # --- Theorem 4: with serialization ---
    print("Computing FA-FP/FIFO (Theorem 4, with serialization)...")
    system2, paths2 = build_paper2_case_study()
    analyzer2 = FPFIFOForwardAnalyzer(system2)
    results_ser = analyzer2.analyze_all(with_serialization=True)
    analyzer2.print_results(results_ser)

    ok2 = compare_with_paper(results_ser, paths2, EXPECTED_SER,
                             "FA-FP/FIFO (Theorem 4, with serialization)")

    # --- Summary ---
    print()
    print("=" * 70)
    if ok1 and ok2:
        print("ALL RESULTS MATCH PAPER TABLE II!")
    else:
        print("Some results do not match.")
    print("=" * 70)

    return ok1 and ok2


if __name__ == "__main__":
    main()
