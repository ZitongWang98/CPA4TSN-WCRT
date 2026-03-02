"""
Test Forwarding Delay Support for TASSchedulerE2E

This example demonstrates:
  - Adding forwarding delay tasks to multi-hop TAS flows
  - Forwarding delay impact on E2E latency calculation
  - Ensuring forwarding tasks don't affect gate blocking calculations
  - Verifying that non_gate_closed includes forwarding delay

Topology:
    Terminal  --->  [Switch1]  --->  [Switch2]  --->  Terminal

Parameters:
    Link speed         : 1 Gbps
    Frame size         : 1518 bytes  =>  wcet = bcet = 12 us
    Forwarding delay   : 5 us per switch
    TAS cycle time     : 1000 us
    TAS window (prio 7): 100 us
    Period             : 1000 us, jitter = 0

Analysis based on:
    THIELE D, ERNST R, DIEMER J. Formal worst-case timing analysis of
    Ethernet TSN's time-aware and peristaltic shapers[C]//2015 IEEE
    Vehicular Networking Conference (VNC). Kyoto, Japan: IEEE, 2015: 251-258.

    Luo F, Zhu L, Wang Z, et al. Schedulability analysis of time aware shaper
    with preemption supported in time-sensitive networks[J]. Computer Networks,
    2025, 269: 111424.
"""

from pycpa import model, analysis, path_analysis, schedulers, options

# ========================================
# 1. Define common parameters
# ========================================
WCET = 12           # 1518B @ 1Gbps
FORWARDING_DELAY = 5 # us per switch
PERIOD = 1000       # us
CYCLE = 1000        # TAS cycle time (us)
WINDOW = 100        # TAS window time (us)


# ========================================
# 2. Helper functions
# ========================================

def create_two_hop_system(with_forwarding_delay=True, use_e2e_scheduler=True):
    """Create a two-hop TAS system.

    Args:
        with_forwarding_delay: If True, configure switch with forwarding_delay
        use_e2e_scheduler: If True, use TASSchedulerE2E, else TASScheduler

    Returns:
        (s, task_h1, task_h2): System and the two hop tasks
    """
    options.init_pycpa()
    s = model.System()

    # Select scheduler class
    sched_class = schedulers.TASSchedulerE2E if use_e2e_scheduler else schedulers.TASScheduler

    # Create switches with forwarding delay configuration
    kwargs = dict(
        priority_mechanism_map={7: 'TAS'},
        tas_cycle_time=CYCLE,
        tas_window_time_by_priority={7: WINDOW}
    )
    if with_forwarding_delay:
        kwargs['forwarding_delay'] = FORWARDING_DELAY

    sw1 = s.bind_resource(model.TSN_Resource("Switch1", sched_class(), **kwargs))
    sw2 = s.bind_resource(model.TSN_Resource("Switch2", sched_class(), **kwargs))

    # Create flow tasks
    task_h1 = model.Task('Flow_h1', bcet=WCET, wcet=WCET, scheduling_parameter=7)
    sw1.bind_task(task_h1)
    task_h1.in_event_model = model.PJdEventModel(P=PERIOD, J=0)

    task_h2 = model.Task('Flow_h2', bcet=WCET, wcet=WCET, scheduling_parameter=7)
    sw2.bind_task(task_h2)

    # Link tasks
    task_h1.link_dependent_task(task_h2)

    return s, task_h1, task_h2


def print_task_results(path, results):
    """Print results for all tasks in the path."""
    for t in path.tasks:
        if t in results:
            is_fd = model.ForwardingTask.is_forwarding_task(t)
            fd_marker = " [FD]" if is_fd else ""
            print(f"    {t.name}{fd_marker}: WCRT={results[t].wcrt} us, "
                  f"BCRT={results[t].bcrt} us")
            if is_fd and hasattr(results[t], 'non_gate_closed'):
                print(f"      non_gate_closed={results[t].non_gate_closed} us")


# ========================================
# 3. Test scenarios
# ========================================

def test_forwarding_delay_basic():
    """Test forwarding delay in TASSchedulerE2E."""
    print("\n" + "=" * 70)
    print("Test 1: Basic Forwarding Delay in TASSchedulerE2E")
    print("=" * 70)

    s, task_h1, task_h2 = create_two_hop_system(
        with_forwarding_delay=True,
        use_e2e_scheduler=True
    )

    # Create path WITHOUT forwarding delays (baseline)
    print("\n--- Baseline (no forwarding delays) ---")
    path_baseline = model.Path('Path_baseline', [task_h1, task_h2])
    s.bind_path(path_baseline)

    results_baseline = analysis.analyze_system(s)
    lmin_b, lmax_b = path_analysis.end_to_end_latency(path_baseline, results_baseline, 1)
    print(f"Hop1 WCRT: {results_baseline[task_h1].wcrt} us")
    print(f"Hop2 WCRT: {results_baseline[task_h2].wcrt} us")
    print(f"E2E (no FD): WCRT={lmax_b} us")

    # Remove baseline path and create path WITH forwarding delays
    s.paths.remove(path_baseline)
    path_with_fd = model.Path('Path_with_fd', [task_h1, task_h2])
    s.bind_path(path_with_fd)

    # Add forwarding delays
    fd_tasks = model.add_forwarding_delays_for_path(path_with_fd)
    print(f"\n--- With forwarding delays ---")
    print(f"Added {len(fd_tasks)} forwarding delay tasks:")
    for fd in fd_tasks:
        print(f"  {fd.name}: wcet={fd.wcet} us, bcet={fd.bcet} us")

    # Re-analyze with forwarding delays
    results_with_fd = analysis.analyze_system(s)
    lmin_fd, lmax_fd = path_analysis.end_to_end_latency(path_with_fd, results_with_fd, 1)

    print(f"\nTask breakdown:")
    print_task_results(path_with_fd, results_with_fd)
    print(f"\nE2E (with FD): WCRT={lmax_fd} us")
    print(f"E2E increase: {lmax_fd - lmax_b} us (expected: {len(fd_tasks) * FORWARDING_DELAY} us)")

    # Verify E2E includes forwarding delay
    expected_increase = len(fd_tasks) * FORWARDING_DELAY
    assert abs(lmax_fd - lmax_b - expected_increase) <= 1, \
        f"E2E should increase by {expected_increase} us, got {lmax_fd - lmax_b} us"
    print("  OK: E2E correctly includes forwarding delay.")


def test_output_model_propagation():
    """Test that output model from forwarding task propagates correctly."""
    print("\n" + "=" * 70)
    print("Test 2: Output Model Propagation Through Forwarding Tasks")
    print("=" * 70)

    s, task_h1, task_h2 = create_two_hop_system()

    # Create path with forwarding delays
    path = model.Path('Path_test', [task_h1, task_h2])
    s.bind_path(path)
    fd_tasks = model.add_forwarding_delays_for_path(path)

    # Verify dependency chain
    print("\nDependency chain:")
    for i, t in enumerate(path.tasks):
        is_fd = model.ForwardingTask.is_forwarding_task(t)
        marker = " [FD]" if is_fd else ""
        print(f"  [{i}] {t.name}{marker}")

        if hasattr(t, 'out_event_model'):
            print(f"      out_event_model: {t.out_event_model.__class__.__name__}")

        dep_list = list(t.dependent_tasks) if hasattr(t, 'dependent_tasks') else []
        if dep_list:
            for dep in dep_list:
                print(f"      -> links to: {dep.name}")

    # Verify: task_h1 -> FD1 -> task_h2 -> FD2
    expected_chain = [task_h1.name, 'FD_Switch1', task_h2.name, 'FD_Switch2']

    actual_chain = [t.name for t in path.tasks]
    assert actual_chain == expected_chain, \
        f"Expected chain {expected_chain}, got {actual_chain}"

    print("  OK: Dependency chain is correct.")


def test_forwarding_task_no_gate_blocking():
    """Test that forwarding tasks have gate_closed_duration = 0."""
    print("\n" + "=" * 70)
    print("Test 3: Forwarding Tasks Have No Gate Blocking")
    print("=" * 70)

    s, task_h1, task_h2 = create_two_hop_system()

    path = model.Path('Path_test', [task_h1, task_h2])
    s.bind_path(path)
    fd_tasks = model.add_forwarding_delays_for_path(path)

    results = analysis.analyze_system(s)

    print("\nGate-closed blocking verification:")
    for t in path.tasks:
        if t in results:
            if model.ForwardingTask.is_forwarding_task(t):
                gc_dur = getattr(results[t], 'gate_closed_duration', 'N/A')
                print(f"  {t.name}: gate_closed_duration={gc_dur}")
                # Verify gate_closed_duration = 0
                assert gc_dur == 0, f"Forwarding task {t.name} should have gate_closed_duration=0"
                # Verify non_gate_closed = wcrt
                non_gc = getattr(results[t], 'non_gate_closed', 'N/A')
                print(f"            non_gate_closed={non_gc}")
                assert non_gc == t.wcet, f"non_gate_closed should equal wcet ({t.wcet})"

    print("  OK: Forwarding tasks have no gate blocking.")


def test_auto_add_forwarding_delays():
    """Test automatic forwarding delay configuration."""
    print("\n" + "=" * 70)
    print("Test 4: Automatic Forwarding Delay Configuration")
    print("=" * 70)

    # Create system WITHOUT forwarding_delay in TSN_Resource
    s = model.System()

    # Create switches with TASSchedulerE2E but no forwarding_delay attribute
    sw1 = s.bind_resource(model.TSN_Resource(
        "Switch1",
        schedulers.TASSchedulerE2E(),
        priority_mechanism_map={7: 'TAS'},
        tas_cycle_time=CYCLE,
        tas_window_time_by_priority={7: WINDOW}
    ))

    sw2 = s.bind_resource(model.TSN_Resource(
        "Switch2",
        schedulers.TASSchedulerE2E(),
        priority_mechanism_map={7: 'TAS'},
        tas_cycle_time=CYCLE,
        tas_window_time_by_priority={7: WINDOW}
    ))

    # Create flow
    task_h1 = model.Task('Flow_h1', bcet=WCET, wcet=WCET, scheduling_parameter=7)
    sw1.bind_task(task_h1)
    task_h1.in_event_model = model.PJdEventModel(P=PERIOD, J=0)

    task_h2 = model.Task('Flow_h2', bcet=WCET, wcet=WCET, scheduling_parameter=7)
    sw2.bind_task(task_h2)
    task_h1.link_dependent_task(task_h2)

    # Create path
    path = model.Path('Path_auto', [task_h1, task_h2])
    s.bind_path(path)

    # Use auto_add_forwarding_delays with latency_by_resource dict
    print("\n--- Auto-add forwarding delays with latency dict ---")
    latency_map = {'Switch1': 5, 'Switch2': 8}  # Different delays per switch
    added = model.auto_add_forwarding_delays(s, latency_by_resource=latency_map)

    print(f"Added {len(added)} forwarding delay tasks:")
    for key, (fd_task, latency) in added.items():
        print(f"  {key}: {fd_task.name}, latency={latency} us")

    # Verify path tasks
    print(f"\nPath tasks: {[t.name for t in path.tasks]}")
    assert any('FD_Switch1' in t.name for t in path.tasks), "FD_Switch1 not found in path"
    assert any('FD_Switch2' in t.name for t in path.tasks), "FD_Switch2 not found in path"

    # Analyze
    results = analysis.analyze_system(s)
    lmin, lmax = path_analysis.end_to_end_latency(path, results, 1)

    print(f"\nTask breakdown:")
    print_task_results(path, results)
    print(f"E2E (auto-added FD): WCRT={lmax} us")

    # Verify total forwarding delay
    fd_wcrt_sum = sum(t.wcet for t in path.tasks if model.ForwardingTask.is_forwarding_task(t))
    expected_fd_total = sum(latency_map.values())
    assert fd_wcrt_sum == expected_fd_total, \
        f"Total FD WCRT ({fd_wcrt_sum}) != expected ({expected_fd_total})"

    print("  OK: Automatic forwarding delay configuration works correctly.")

def test_e2e_correction_with_forwarding_delay():
    """Test that TAS E2E correction works correctly when forwarding delays are present.

    This verifies that _is_tas_path() in _apply_tas_e2e_correction does not
    incorrectly reject the path due to ForwardingTask's negative scheduling_parameter.

    Expected behavior:
        - With tas_aligned=True and NO forwarding delay, E2E correction should apply
        - With tas_aligned=True and WITH forwarding delay, E2E correction should still apply
        - The corrected E2E with FD should equal corrected E2E without FD + total FD delay
    """
    print("\n" + "=" * 70)
    print("Test 5: E2E Correction + Forwarding Delay Interaction")
    print("=" * 70)

    # --- Case A: E2E correction WITHOUT forwarding delay ---
    s_a, task_h1_a, task_h2_a = create_two_hop_system(
        with_forwarding_delay=True,
        use_e2e_scheduler=True
    )
    path_a = model.Path('Path_no_fd', [task_h1_a, task_h2_a])
    path_a.tas_aligned = True  # Enable E2E correction
    s_a.bind_path(path_a)

    results_a = analysis.analyze_system(s_a)
    _, lmax_a = path_analysis.end_to_end_latency(path_a, results_a, 1)
    print(f"\nCase A (no FD, tas_aligned=True): E2E = {lmax_a} us")

    # Check if E2E correction was actually applied by comparing with sum of WCRTs
    sum_wcrt_a = sum(results_a[t].wcrt for t in path_a.tasks if t in results_a)
    correction_applied_a = (lmax_a != sum_wcrt_a)
    print(f"  sum(WCRT) = {sum_wcrt_a} us, corrected E2E = {lmax_a} us")
    print(f"  E2E correction applied: {correction_applied_a}")

    # --- Case B: E2E correction WITH forwarding delay ---
    s_b, task_h1_b, task_h2_b = create_two_hop_system(
        with_forwarding_delay=True,
        use_e2e_scheduler=True
    )
    path_b = model.Path('Path_with_fd', [task_h1_b, task_h2_b])
    path_b.tas_aligned = True  # Enable E2E correction
    s_b.bind_path(path_b)

    # Add forwarding delays
    fd_tasks = model.add_forwarding_delays_for_path(path_b)
    total_fd = sum(fd.wcet for fd in fd_tasks)
    print(f"\nCase B (with FD, tas_aligned=True): added {len(fd_tasks)} FD tasks, total={total_fd} us")

    results_b = analysis.analyze_system(s_b)
    _, lmax_b = path_analysis.end_to_end_latency(path_b, results_b, 1)
    print(f"  E2E = {lmax_b} us")

    # Check if E2E correction was applied
    sum_wcrt_b = sum(results_b[t].wcrt for t in path_b.tasks if t in results_b)
    correction_applied_b = (lmax_b != sum_wcrt_b)
    print(f"  sum(WCRT) = {sum_wcrt_b} us, corrected E2E = {lmax_b} us")
    print(f"  E2E correction applied: {correction_applied_b}")

    # --- Verify ---
    # E2E correction must be applied in both cases
    assert correction_applied_a, "E2E correction should apply in Case A (no FD)"
    assert correction_applied_b, "E2E correction should apply in Case B (with FD)"

    # The corrected E2E with FD should equal corrected E2E without FD + total FD delay
    diff = lmax_b - lmax_a
    print(f"\n  E2E difference: {diff} us (expected: {total_fd} us)")
    assert abs(diff - total_fd) <= 1, \
        f"E2E difference ({diff}) should equal total FD ({total_fd})"
    print("  OK: E2E correction works correctly with forwarding delays.")

def test_asymmetric_forwarding_delay():
    """Test forwarding delay with bcet != wcet and event model propagation.

    When bcet < wcet, the forwarding task introduces response time jitter
    (jitter = wcet - bcet), which must propagate into the downstream task's
    input event model, just like a regular scheduler would.
    """
    print("\n" + "=" * 70)
    print("Test 6: Asymmetric Forwarding Delay (bcet != wcet) and Event Model Propagation")
    print("=" * 70)

    FD_BCET = 3
    FD_WCET = 7

    options.init_pycpa()
    s = model.System()

    sw1 = s.bind_resource(model.TSN_Resource("Switch1", schedulers.TASSchedulerE2E(),
        priority_mechanism_map={7: 'TAS'}, tas_cycle_time=CYCLE,
        tas_window_time_by_priority={7: WINDOW},
        forwarding_delay=(FD_BCET, FD_WCET)))
    sw2 = s.bind_resource(model.TSN_Resource("Switch2", schedulers.TASSchedulerE2E(),
        priority_mechanism_map={7: 'TAS'}, tas_cycle_time=CYCLE,
        tas_window_time_by_priority={7: WINDOW},
        forwarding_delay=(FD_BCET, FD_WCET)))

    task_h1 = model.Task('Flow_h1', bcet=WCET, wcet=WCET, scheduling_parameter=7)
    sw1.bind_task(task_h1)
    task_h1.in_event_model = model.PJdEventModel(P=PERIOD, J=0)

    task_h2 = model.Task('Flow_h2', bcet=WCET, wcet=WCET, scheduling_parameter=7)
    sw2.bind_task(task_h2)
    task_h1.link_dependent_task(task_h2)

    path = model.Path('Path_asym', [task_h1, task_h2])
    s.bind_path(path)
    fd_tasks = model.add_forwarding_delays_for_path(path)

    print(f"\nForwarding tasks:")
    for fd in fd_tasks:
        print(f"  {fd.name}: bcet={fd.bcet}, wcet={fd.wcet}")
        assert fd.bcet == FD_BCET, f"Expected bcet={FD_BCET}, got {fd.bcet}"
        assert fd.wcet == FD_WCET, f"Expected wcet={FD_WCET}, got {fd.wcet}"

    results = analysis.analyze_system(s)

    # Verify BCRT != WCRT for forwarding tasks
    print(f"\nTask analysis results:")
    for t in path.tasks:
        if t in results:
            is_fd = model.ForwardingTask.is_forwarding_task(t)
            marker = " [FD]" if is_fd else ""
            print(f"  {t.name}{marker}: WCRT={results[t].wcrt}, BCRT={results[t].bcrt}")
            if is_fd:
                assert results[t].wcrt == FD_WCET, \
                    f"{t.name} WCRT should be {FD_WCET}, got {results[t].wcrt}"
                assert results[t].bcrt == FD_BCET, \
                    f"{t.name} BCRT should be {FD_BCET}, got {results[t].bcrt}"

    # Verify event model propagation: FD task introduces jitter = wcet - bcet
    # Find FD_Switch1 by name (fd_tasks order depends on set iteration)
    fd1 = next(fd for fd in fd_tasks if 'Switch1' in fd.name)
    fd_jitter = FD_WCET - FD_BCET
    print(f"\n  FD jitter (wcet - bcet) = {fd_jitter} us")

    # FD_Switch1's output model feeds into Flow_h2's input model.
    # The jitter from FD (wcet - bcet) makes delta_min decrease (more bursty).
    fd1_in_dmin2 = fd1.in_event_model.delta_min(2)
    t2_in_dmin2 = task_h2.in_event_model.delta_min(2)
    print(f"  FD_Switch1 in_event_model delta_min(2) = {fd1_in_dmin2}")
    print(f"  Flow_h2 in_event_model delta_min(2) = {t2_in_dmin2}")
    assert t2_in_dmin2 < fd1_in_dmin2, \
        f"Flow_h2 delta_min(2) ({t2_in_dmin2}) should be smaller than FD input ({fd1_in_dmin2}) (jitter added)"

    # E2E latency
    lmin, lmax = path_analysis.end_to_end_latency(path, results, 1)
    print(f"\n  E2E: min={lmin} us, max={lmax} us")
    print("  OK: Asymmetric forwarding delay with event model propagation works correctly.")




# ========================================
# 4. Main function entry
# ========================================
if __name__ == "__main__":
    test_forwarding_delay_basic()
    test_output_model_propagation()
    test_forwarding_task_no_gate_blocking()
    test_auto_add_forwarding_delays()
    test_e2e_correction_with_forwarding_delay()
    test_asymmetric_forwarding_delay()

    print("\n" + "=" * 70)
    print("All forwarding delay tests completed successfully.")
    print("=" * 70)
