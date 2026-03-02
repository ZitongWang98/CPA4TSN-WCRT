"""Property-based tests for AFDX FP/FIFO Forward Analysis.

Uses Hypothesis to generate random valid AFDX network configurations
and verify correctness properties of the FPFIFOForwardAnalyzer.
"""
import math
from hypothesis import given, settings, assume, HealthCheck
from hypothesis.strategies import (
    composite,
    integers,
    booleans,
    sampled_from,
    just,
    lists,
    floats,
    permutations,
)

from pycpa import model
from forward_analysis.fa_fpfifo import FPFIFOForwardAnalyzer, AnalysisResult, HopResult


# ---------------------------------------------------------------------------
# Hypothesis composite generator strategies
# ---------------------------------------------------------------------------

@composite
def valid_afdx_system(draw):
    """Generate a valid AFDX system with random configuration.

    Produces a ``model.System`` containing:

    - 1-3 Resources (switch output ports), each with optional forwarding_delay
      (0-50)
    - 1-5 Paths (VLs), each with 1-3 hops
    - Each hop is a ``model.Task`` bound to a Resource
    - First task in each path has a ``PJdEventModel`` with P (100-100000)
      and J (0-P//2)
    - Non-first-hop tasks also receive a ``PJdEventModel`` with the same P
      and J=0 (the analyzer reads ``in_event_model.P`` from all tasks on a
      shared resource, not only first-hop tasks)
    - Each task has: wcet (1-200), bcet (1-wcet), scheduling_parameter (1-4)
    - Multiple VLs can share the same Resource (creating interference)

    Constraints enforced:

    - bcet <= wcet
    - wcet > 0
    - P > 0
    - All tasks bound to a Resource
    - First task has in_event_model set
    - Total utilisation on each resource < 0.7 (ensures schedulability so
      the fixed-point iteration converges)

    Edge cases covered:

    - Single hop paths (1 task)
    - Single flow networks (1 path)
    - All flows same priority (pure FIFO)
    - No lower priority flows on a resource
    """
    # --- Number of resources (switch output ports) ---
    num_resources = draw(integers(min_value=1, max_value=3))

    # --- Create resources with optional forwarding_delay ---
    resources = []
    for r_idx in range(num_resources):
        r = model.Resource(f"SW{r_idx}_out")
        has_fwd_delay = draw(booleans())
        if has_fwd_delay:
            r.forwarding_delay = draw(integers(min_value=0, max_value=50))
        resources.append(r)

    # --- Number of paths (VLs) ---
    num_paths = draw(integers(min_value=1, max_value=5))

    # --- Decide priority mode ---
    # With some probability, force all flows to the same priority (pure FIFO)
    all_same_priority = draw(booleans())
    if all_same_priority:
        global_priority = draw(integers(min_value=1, max_value=4))

    # --- Create system ---
    system = model.System("TestAFDX")
    for r in resources:
        system.bind_resource(r)

    # Track utilisation per resource: sum of wcet/P for tasks on that resource
    resource_util: dict = {id(r): 0.0 for r in resources}

    # --- Create paths ---
    task_counter = 0
    paths = []
    for p_idx in range(num_paths):
        # Number of hops for this path (capped by available resources)
        max_hops = min(3, num_resources)
        num_hops = draw(integers(min_value=1, max_value=max_hops))

        # Select resources for each hop
        if num_hops == 1:
            hop_resources = [draw(sampled_from(resources))]
        else:
            # For multi-hop, pick distinct resources for each hop
            available = list(resources)
            assume(len(available) >= num_hops)
            hop_resources = []
            remaining = list(available)
            for _ in range(num_hops):
                chosen = draw(sampled_from(remaining))
                hop_resources.append(chosen)
                remaining.remove(chosen)

        # Draw the period for this VL (shared across all hops)
        P = draw(integers(min_value=100, max_value=100000))

        # --- Create tasks for this path ---
        tasks = []
        for h_idx, res in enumerate(hop_resources):
            wcet = draw(integers(min_value=1, max_value=200))
            bcet = draw(integers(min_value=1, max_value=wcet))

            if all_same_priority:
                sp = global_priority
            else:
                sp = draw(integers(min_value=1, max_value=4))

            task_name = f"VL{p_idx}_hop{h_idx}_t{task_counter}"
            task_counter += 1

            t = model.Task(task_name, bcet=bcet, wcet=wcet, scheduling_parameter=sp)
            res.bind_task(t)

            # Set event model on every task (the analyzer reads
            # in_event_model.P from interfering tasks on shared resources)
            if h_idx == 0:
                J = draw(integers(min_value=0, max_value=P // 2))
                t.in_event_model = model.PJdEventModel(P=P, J=J)
            else:
                # Non-first-hop tasks: same P, J=0
                t.in_event_model = model.PJdEventModel(P=P, J=0)

            # Track utilisation
            resource_util[id(res)] += wcet / P

            tasks.append(t)

        path = model.Path(f"VL{p_idx}", tasks)
        system.bind_path(path)
        paths.append(path)

    # --- Ensure schedulability: total utilisation < 0.7 on every resource ---
    for r in resources:
        assume(resource_util[id(r)] < 0.7)

    return system


# ---------------------------------------------------------------------------
# Smoke test: verify the generator produces analysable systems
# ---------------------------------------------------------------------------

class TestGeneratorSmoke:
    """Basic smoke tests to verify the generator produces valid systems."""

    @given(system=valid_afdx_system())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_generated_system_is_analyzable(self, system):
        """A generated system should be analysable without errors.

        Validates: Requirements 1.1, 6.1
        """
        analyzer = FPFIFOForwardAnalyzer(system)
        results = analyzer.analyze_all(with_serialization=False)

        # Should return one result per path
        assert len(results) == len(system.paths)

        # Every result should be an AnalysisResult with non-negative e2e_wcrt
        for path, result in results.items():
            assert isinstance(result, AnalysisResult)
            assert result.e2e_wcrt >= 0
            assert len(result.hop_results) > 0
