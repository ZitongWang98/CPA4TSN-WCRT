"""
Test TSN Parameter Validation on Per-Resource and Task-Chain Basis

This example tests the TSN scheduling parameter validation that ensures:

Per-Resource Basis Constraints:
===============================
1. For tasks using TAS on the same resource:
   - All tas_cycle_time values must be the same
   - If scheduling_parameter (priority) is the same, tas_window_time must be the same
2. For tasks using CQF on the same resource:
   - If TAS is also used, cqf_cycle_time must be equal to or an even positive integer multiple of tas_cycle_time
   - Between CQF tasks, cqf_cycle_time must be equal or have an even positive integer multiple relationship

Per-Task-Chain Basis Constraints:
=================================
3. For all TSN tasks in the same task chain (path):
   - All TSN tasks must use the same mechanism (TAS or CQF)
   - For tasks using TAS: tas_cycle_time, tas_window_time, and is_express (if preemption enabled) must be equal
   - For tasks using CQF: cqf_cycle_time must be equal

Test Cases Summary:
===================

Valid Configuration Tests (9 tests):
-------------------------------------
- Test 1: Valid TAS Configuration - All TAS tasks have same cycle_time, same scheduling_parameter
          tasks have same window_time
- Test 4: Valid CQF with TAS - CQF cycle_time is even multiple of TAS cycle_time (2x, 4x)
- Test 7: CQF Only - Same Cycle Time - Multiple CQF tasks with identical cycle_time
- Test 8: Mixed TAS and CQF - Full Valid Configuration - Multiple TAS tasks with same cycle_time,
          CQF tasks with cycle_time as even multiples of TAS cycle_time
- Test 9: CQF Only - Valid Even Multiple Relationship - CQF tasks: 2000000, 4000000, 8000000
          (each is 2x the previous)
- Test 10: No TSN Tasks - Resource with only regular Task objects (no TSN_SendingTask)
- Test 12: Valid CQF - Equal to TAS Cycle - CQF cycle_time equals TAS cycle_time (1x is allowed)
- Test 13: Valid Task Chain - All Tasks with Same TAS - Chain T1->T2->T3, all using TAS with identical
          parameters
- Test 16: Valid Task Chain - All Tasks with Same CQF - Chain T1->T2->T3, all using CQF with identical
          parameters

Invalid Configuration Tests (7 tests):
---------------------------------------
- Test 2: Invalid TAS - Different Cycle Times - TAS tasks with different tas_cycle_time values
          (1000000 vs 2000000)
- Test 3: Invalid TAS - Same sched_param, Different Window - SAME scheduling_parameter but
          DIFFERENT tas_window_time values
- Test 5: Invalid CQF - Not Even Multiple of TAS - CQF cycle_time is 3x TAS cycle_time (odd multiple)
- Test 6: Invalid CQF - No Even Multiple Relation - CQF tasks: 2000000 and 3000000 (no even
          multiple relationship)
- Test 11: Invalid CQF - Less Than TAS Cycle - CQF cycle_time (500000) < TAS cycle_time (1000000)
- Test 14: Invalid Task Chain - TAS and CQF Mixed - Chain T1(TAS)->T2(CQF)->T3(TAS), different
          mechanisms in same chain
- Test 15: Invalid Task Chain - Different TAS Parameters - Chain with TAS tasks having different
          tas_window_time values
"""

import logging
from pycpa import model
from pycpa import analysis
from pycpa import schedulers
from pycpa import options


def test_valid_tas_configuration():
    """Test valid TAS configuration - all tasks have same cycle time and proper window time"""
    print("\n" + "="*60)
    print("Test 1: Valid TAS Configuration")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r1 = s.bind_resource(model.Resource("R1", schedulers.SPPScheduler()))

    # All TAS tasks with same cycle_time = 1000000
    task1 = model.TSN_SendingTask('TAS_Task1', 1, 2, 1, 0b0010,
                                  tas_cycle_time=1000000,
                                  tas_window_time=500000)
    r1.bind_task(task1)

    # Same scheduling_parameter (1), same window_time -> should pass
    task2 = model.TSN_SendingTask('TAS_Task2', 1, 2, 1, 0b0010,
                                  tas_cycle_time=1000000,
                                  tas_window_time=500000)
    r1.bind_task(task2)

    # Different scheduling_parameter (2), can have different window_time -> should pass
    task3 = model.TSN_SendingTask('TAS_Task3', 1, 2, 2, 0b0010,
                                  tas_cycle_time=1000000,
                                  tas_window_time=600000)
    r1.bind_task(task3)

    # Set event models - use larger periods to lower load
    task1.in_event_model = model.PJdEventModel(P=1000, J=0)
    task2.in_event_model = model.PJdEventModel(P=1000, J=0)
    task3.in_event_model = model.PJdEventModel(P=1000, J=0)

    # Perform analysis - should NOT raise ValueError
    try:
        results = analysis.analyze_system(s)
        print("SUCCESS: Analysis completed without errors!")
        print("\nResults:")
        for t in r1.tasks:
            print(f"  {t.name}: tas_cycle_time={t.tas_cycle_time}, "
                  f"tas_window_time={t.tas_window_time}, scheduling_parameter={t.scheduling_parameter}")
    except ValueError as e:
        print(f"FAILED: {e}")


def test_invalid_tas_different_cycle_times():
    """Test invalid TAS configuration - different tas_cycle_time values"""
    print("\n" + "="*60)
    print("Test 2: Invalid TAS - Different Cycle Times (should fail)")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r2 = s.bind_resource(model.Resource("R2", schedulers.SPPScheduler()))

    # tas_cycle_time = 1000000
    task1 = model.TSN_SendingTask('TAS_Task1', 1, 2, 1, 0b0010,
                                  tas_cycle_time=1000000,
                                  tas_window_time=500000)
    r2.bind_task(task1)

    # tas_cycle_time = 2000000 -> DIFFERENT! Should fail
    task2 = model.TSN_SendingTask('TAS_Task2', 1, 2, 2, 0b0010,
                                  tas_cycle_time=2000000,
                                  tas_window_time=1000000)
    r2.bind_task(task2)

    task1.in_event_model = model.PJdEventModel(P=1000, J=0)
    task2.in_event_model = model.PJdEventModel(P=1000, J=0)

    # Should raise ValueError
    try:
        results = analysis.analyze_system(s)
        print("FAILED: Analysis should have raised ValueError!")
    except ValueError as e:
        print(f"SUCCESS: Expected error caught: {e}")


def test_invalid_tas_same_sched_param_different_window():
    """Test invalid TAS configuration - same scheduling_parameter but different tas_window_time"""
    print("\n" + "="*60)
    print("Test 3: Invalid TAS - Same sched_param, Different Window (should fail)")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r3 = s.bind_resource(model.Resource("R3", schedulers.SPPScheduler()))

    # Same cycle_time, same scheduling_parameter
    task1 = model.TSN_SendingTask('TAS_Task1', 1, 2, 1, 0b0010,
                                  tas_cycle_time=1000000,
                                  tas_window_time=500000)
    r3.bind_task(task1)

    # Same cycle_time, same scheduling_parameter, but DIFFERENT window_time -> should fail
    task2 = model.TSN_SendingTask('TAS_Task2', 1, 2, 1, 0b0010,
                                  tas_cycle_time=1000000,
                                  tas_window_time=600000)
    r3.bind_task(task2)

    task1.in_event_model = model.PJdEventModel(P=1000, J=0)
    task2.in_event_model = model.PJdEventModel(P=1000, J=0)

    # Should raise ValueError
    try:
        results = analysis.analyze_system(s)
        print("FAILED: Analysis should have raised ValueError!")
    except ValueError as e:
        print(f"SUCCESS: Expected error caught: {e}")


def test_valid_cqf_with_tas():
    """Test valid CQF with TAS - cqf_cycle_time is even multiple of tas_cycle_time"""
    print("\n" + "="*60)
    print("Test 4: Valid CQF with TAS")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r4 = s.bind_resource(model.Resource("R4", schedulers.SPPScheduler()))

    # TAS with cycle_time = 1000000
    tas_task = model.TSN_SendingTask('TAS_Task', 1, 2, 1, 0b0010,
                                     tas_cycle_time=1000000,
                                     tas_window_time=500000)
    r4.bind_task(tas_task)

    # CQF with cycle_time = 2000000 = 2 * tas_cycle_time (even multiple) -> should pass
    cqf_task1 = model.TSN_SendingTask('CQF_Task1', 1, 2, 2, 0b0100,
                                      cqf_cycle_time=2000000)
    r4.bind_task(cqf_task1)

    # CQF with cycle_time = 4000000 = 4 * tas_cycle_time (even multiple) -> should pass
    cqf_task2 = model.TSN_SendingTask('CQF_Task2', 1, 2, 3, 0b0100,
                                      cqf_cycle_time=4000000)
    r4.bind_task(cqf_task2)

    tas_task.in_event_model = model.PJdEventModel(P=1000, J=0)
    cqf_task1.in_event_model = model.PJdEventModel(P=1000, J=0)
    cqf_task2.in_event_model = model.PJdEventModel(P=1000, J=0)

    # Should NOT raise ValueError
    try:
        results = analysis.analyze_system(s)
        print("SUCCESS: Analysis completed without errors!")
        print("\nResults:")
        print(f"  TAS: tas_cycle_time={tas_task.tas_cycle_time}")
        print(f"  CQF1: cqf_cycle_time={cqf_task1.cqf_cycle_time} (2x TAS)")
        print(f"  CQF2: cqf_cycle_time={cqf_task2.cqf_cycle_time} (4x TAS)")
    except ValueError as e:
        print(f"FAILED: {e}")


def test_invalid_cqf_not_even_multiple_of_tas():
    """Test invalid CQF configuration - cqf_cycle_time is not an even multiple of tas_cycle_time"""
    print("\n" + "="*60)
    print("Test 5: Invalid CQF - Not Even Multiple of TAS (should fail)")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r5 = s.bind_resource(model.Resource("R5", schedulers.SPPScheduler()))

    # TAS with cycle_time = 1000000
    tas_task = model.TSN_SendingTask('TAS_Task', 1, 2, 1, 0b0010,
                                     tas_cycle_time=1000000,
                                     tas_window_time=500000)
    r5.bind_task(tas_task)

    # CQF with cycle_time = 3000000 = 3 * tas_cycle_time (ODD multiple) -> should fail
    cqf_task = model.TSN_SendingTask('CQF_Task', 1, 2, 2, 0b0100,
                                     cqf_cycle_time=3000000)
    r5.bind_task(cqf_task)

    tas_task.in_event_model = model.PJdEventModel(P=1000, J=0)
    cqf_task.in_event_model = model.PJdEventModel(P=1000, J=0)

    # Should raise ValueError
    try:
        results = analysis.analyze_system(s)
        print("FAILED: Analysis should have raised ValueError!")
    except ValueError as e:
        print(f"SUCCESS: Expected error caught: {e}")


def test_invalid_cqf_different_cycle_times():
    """Test invalid CQF configuration - cqf_cycle_time values don't have even multiple relationship"""
    print("\n" + "="*60)
    print("Test 6: Invalid CQF - No Even Multiple Relation (should fail)")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r6 = s.bind_resource(model.Resource("R6", schedulers.SPPScheduler()))

    # No TAS tasks on this resource

    # CQF with cycle_time = 2000000
    cqf_task1 = model.TSN_SendingTask('CQF_Task1', 1, 2, 1, 0b0100,
                                      cqf_cycle_time=2000000)
    r6.bind_task(cqf_task1)

    # CQF with cycle_time = 3000000 -> not an even multiple of 2000000 -> should fail
    cqf_task2 = model.TSN_SendingTask('CQF_Task2', 1, 2, 2, 0b0100,
                                      cqf_cycle_time=3000000)
    r6.bind_task(cqf_task2)

    cqf_task1.in_event_model = model.PJdEventModel(P=1000, J=0)
    cqf_task2.in_event_model = model.PJdEventModel(P=1000, J=0)

    # Should raise ValueError
    try:
        results = analysis.analyze_system(s)
        print("FAILED: Analysis should have raised ValueError!")
    except ValueError as e:
        print(f"SUCCESS: Expected error caught: {e}")


def test_cqf_only_same_cycle():
    """Test CQF-only configuration with same cycle_time (valid)"""
    print("\n" + "="*60)
    print("Test 7: CQF Only - Same Cycle Time (valid)")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r7 = s.bind_resource(model.Resource("R7", schedulers.SPPScheduler()))

    # CQF tasks with SAME cycle_time -> should pass
    cqf_task1 = model.TSN_SendingTask('CQF_Task1', 1, 2, 1, 0b0100,
                                      cqf_cycle_time=2000000)
    r7.bind_task(cqf_task1)

    cqf_task2 = model.TSN_SendingTask('CQF_Task2', 1, 2, 2, 0b0100,
                                      cqf_cycle_time=2000000)
    r7.bind_task(cqf_task2)

    cqf_task1.in_event_model = model.PJdEventModel(P=1000, J=0)
    cqf_task2.in_event_model = model.PJdEventModel(P=1000, J=0)

    # Should NOT raise ValueError
    try:
        results = analysis.analyze_system(s)
        print("SUCCESS: Analysis completed without errors!")
        print("\nResults:")
        print(f"  CQF1: cqf_cycle_time={cqf_task1.cqf_cycle_time}")
        print(f"  CQF2: cqf_cycle_time={cqf_task2.cqf_cycle_time} (same)")
    except ValueError as e:
        print(f"FAILED: {e}")


def test_mixed_tas_cqf_full_valid():
    """Test mixed TAS and CQF with full valid configuration"""
    print("\n" + "="*60)
    print("Test 8: Mixed TAS and CQF - Full Valid Configuration")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r8 = s.bind_resource(model.Resource("R8", schedulers.SPPScheduler()))

    # Multiple TAS tasks with same cycle_time
    tas_task1 = model.TSN_SendingTask('TAS1', 1, 2, 1, 0b0010,
                                      tas_cycle_time=500000,
                                      tas_window_time=250000)
    r8.bind_task(tas_task1)

    tas_task2 = model.TSN_SendingTask('TAS2', 1, 2, 1, 0b0010,
                                      tas_cycle_time=500000,
                                      tas_window_time=250000)
    r8.bind_task(tas_task2)

    tas_task3 = model.TSN_SendingTask('TAS3', 1, 2, 2, 0b0010,
                                      tas_cycle_time=500000,
                                      tas_window_time=150000)
    r8.bind_task(tas_task3)

    # CQF tasks with cycle_time as even multiples of TAS cycle_time
    cqf_task1 = model.TSN_SendingTask('CQF1', 1, 2, 3, 0b0100,
                                      cqf_cycle_time=1000000)  # 2x TAS
    r8.bind_task(cqf_task1)

    cqf_task2 = model.TSN_SendingTask('CQF2', 1, 2, 4, 0b0100,
                                      cqf_cycle_time=2000000)  # 4x TAS, 2x CQF1
    r8.bind_task(cqf_task2)

    tas_task1.in_event_model = model.PJdEventModel(P=1000, J=0)
    tas_task2.in_event_model = model.PJdEventModel(P=1000, J=0)
    tas_task3.in_event_model = model.PJdEventModel(P=1000, J=0)
    cqf_task1.in_event_model = model.PJdEventModel(P=1000, J=0)
    cqf_task2.in_event_model = model.PJdEventModel(P=1000, J=0)

    # Should NOT raise ValueError
    try:
        results = analysis.analyze_system(s)
        print("SUCCESS: Analysis completed without errors!")
        print("\nResults:")
        print(f"  TAS1/TAS2: cycle=500000, window=250000, prio=1")
        print(f"  TAS3: cycle=500000, window=150000, prio=2")
        print(f"  CQF1: cycle=1000000 (2x TAS)")
        print(f"  CQF2: cycle=2000000 (4x TAS, 2x CQF1)")
    except ValueError as e:
        print(f"FAILED: {e}")


def test_cqf_mixed_valid_even_multiple():
    """Test CQF tasks with valid even multiple relationship"""
    print("\n" + "="*60)
    print("Test 9: CQF Only - Valid Even Multiple Relationship")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r9 = s.bind_resource(model.Resource("R9", schedulers.SPPScheduler()))

    # CQF tasks: 2000000, 4000000, 8000000 -> each is 2x the previous -> should pass
    cqf_task1 = model.TSN_SendingTask('CQF1', 1, 2, 1, 0b0100,
                                      cqf_cycle_time=2000000)
    r9.bind_task(cqf_task1)

    cqf_task2 = model.TSN_SendingTask('CQF2', 1, 2, 2, 0b0100,
                                      cqf_cycle_time=4000000)  # 2x CQF1
    r9.bind_task(cqf_task2)

    cqf_task3 = model.TSN_SendingTask('CQF3', 1, 2, 3, 0b0100,
                                      cqf_cycle_time=8000000)  # 4x CQF1, 2x CQF2
    r9.bind_task(cqf_task3)

    cqf_task1.in_event_model = model.PJdEventModel(P=1000, J=0)
    cqf_task2.in_event_model = model.PJdEventModel(P=1000, J=0)
    cqf_task3.in_event_model = model.PJdEventModel(P=1000, J=0)

    # Should NOT raise ValueError
    try:
        results = analysis.analyze_system(s)
        print("SUCCESS: Analysis completed without errors!")
        print("\nResults:")
        print(f"  CQF1: cycle={cqf_task1.cqf_cycle_time}")
        print(f"  CQF2: cycle={cqf_task2.cqf_cycle_time} (2x CQF1)")
        print(f"  CQF3: cycle={cqf_task3.cqf_cycle_time} (4x CQF1, 2x CQF2)")
    except ValueError as e:
        print(f"FAILED: {e}")


def test_no_tsn_tasks():
    """Test resource with no TSN tasks - should pass"""
    print("\n" + "="*60)
    print("Test 10: No TSN Tasks (should pass)")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r10 = s.bind_resource(model.Resource("R10", schedulers.SPPScheduler()))

    # Regular tasks, no TSN_SendingTask
    task1 = model.Task('Regular1', 1, 2, 1)
    r10.bind_task(task1)

    task2 = model.Task('Regular2', 1, 2, 2)
    r10.bind_task(task2)

    task1.in_event_model = model.PJdEventModel(P=1000, J=0)
    task2.in_event_model = model.PJdEventModel(P=1000, J=0)

    # Should NOT raise ValueError
    try:
        results = analysis.analyze_system(s)
        print("SUCCESS: Analysis completed without errors!")
    except ValueError as e:
        print(f"FAILED: {e}")


def test_cqf_less_than_tas_cycle():
    """Test invalid CQF configuration - cqf_cycle_time is less than tas_cycle_time"""
    print("\n" + "="*60)
    print("Test 11: Invalid CQF - Less Than TAS Cycle (should fail)")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r11 = s.bind_resource(model.Resource("R11", schedulers.SPPScheduler()))

    # TAS with cycle_time = 1000000
    tas_task = model.TSN_SendingTask('TAS_Task', 1, 2, 1, 0b0010,
                                     tas_cycle_time=1000000,
                                     tas_window_time=500000)
    r11.bind_task(tas_task)

    # CQF with cycle_time = 500000 < tas_cycle_time -> should fail
    cqf_task = model.TSN_SendingTask('CQF_Task', 1, 2, 2, 0b0100,
                                     cqf_cycle_time=500000)
    r11.bind_task(cqf_task)

    tas_task.in_event_model = model.PJdEventModel(P=1000, J=0)
    cqf_task.in_event_model = model.PJdEventModel(P=1000, J=0)

    # Should raise ValueError
    try:
        results = analysis.analyze_system(s)
        print("FAILED: Analysis should have raised ValueError!")
    except ValueError as e:
        print(f"SUCCESS: Expected error caught: {e}")


def test_cqf_equal_to_tas_cycle():
    """Test valid CQF configuration - cqf_cycle_time equals tas_cycle_time (1x, which is even)"""
    print("\n" + "="*60)
    print("Test 12: Valid CQF - Equal to TAS Cycle (1x is even)")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r12 = s.bind_resource(model.Resource("R12", schedulers.SPPScheduler()))

    # TAS with cycle_time = 1000000
    tas_task = model.TSN_SendingTask('TAS_Task', 1, 2, 1, 0b0010,
                                     tas_cycle_time=1000000,
                                     tas_window_time=500000)
    r12.bind_task(tas_task)

    # CQF with cycle_time = 1000000 = 1 * tas_cycle_time (1 is NOT even!) -> should fail
    # Wait, 1 is not an even positive integer. Let me check the requirements again.
    # The requirement says "偶数正整数倍（或者相等）", which means "even positive integer multiple (or equal)"
    # So equal (1x) is allowed!
    cqf_task = model.TSN_SendingTask('CQF_Task', 1, 2, 2, 0b0100,
                                     cqf_cycle_time=1000000)
    r12.bind_task(cqf_task)

    tas_task.in_event_model = model.PJdEventModel(P=1000, J=0)
    cqf_task.in_event_model = model.PJdEventModel(P=1000, J=0)

    # Should NOT raise ValueError (equal is allowed)
    try:
        results = analysis.analyze_system(s)
        print("SUCCESS: Analysis completed without errors!")
        print(f"CQF cycle_time equals TAS cycle_time (1x is allowed)")
    except ValueError as e:
        print(f"FAILED: {e}")


def test_valid_chain_same_tas():
    """Test valid task chain with all tasks using TAS with same parameters"""
    print("\n" + "="*60)
    print("Test 13: Valid Task Chain - All Tasks with Same TAS")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r13_1 = s.bind_resource(model.Resource("R13_1", schedulers.SPPScheduler()))
    r13_2 = s.bind_resource(model.Resource("R13_2", schedulers.SPPScheduler()))

    # Chain: t1 -> t2 -> t3, all using TAS with same parameters
    t1 = model.TSN_SendingTask('T1', 1, 2, 1, 0b0010,
                               tas_cycle_time=1000000,
                               tas_window_time=500000)
    r13_1.bind_task(t1)

    t2 = model.TSN_SendingTask('T2', 1, 2, 1, 0b0010,
                               tas_cycle_time=1000000,
                               tas_window_time=500000)
    r13_1.bind_task(t2)

    t3 = model.TSN_SendingTask('T3', 1, 2, 1, 0b0010,
                               tas_cycle_time=1000000,
                               tas_window_time=500000)
    r13_2.bind_task(t3)

    # Connect tasks: t1 -> t2 -> t3
    t1.link_dependent_task(t2)
    t2.link_dependent_task(t3)

    # Create a path (task chain)
    path = model.Path("Path13", [t1, t2, t3])
    s.bind_path(path)

    t1.in_event_model = model.PJdEventModel(P=1000, J=0)

    # Should NOT raise ValueError
    try:
        results = analysis.analyze_system(s)
        print("SUCCESS: Analysis completed without errors!")
        print("All TAS tasks in chain have same parameters (valid)")
    except ValueError as e:
        print(f"FAILED: {e}")


def test_invalid_chain_mixed_mechanisms():
    """Test invalid task chain with TAS and CQF tasks mixed"""
    print("\n" + "="*60)
    print("Test 14: Invalid Task Chain - TAS and CQF Mixed (should fail)")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r14_1 = s.bind_resource(model.Resource("R14_1", schedulers.SPPScheduler()))
    r14_2 = s.bind_resource(model.Resource("R14_2", schedulers.SPPScheduler()))

    # Chain: t1 (TAS) -> t2 (CQF) -> t3 (TAS) - different mechanisms!
    t1 = model.TSN_SendingTask('T1', 1, 2, 1, 0b0010,
                               tas_cycle_time=1000000,
                               tas_window_time=500000)
    r14_1.bind_task(t1)

    t2 = model.TSN_SendingTask('T2', 1, 2, 1, 0b0100,
                               cqf_cycle_time=1000000)
    r14_1.bind_task(t2)

    t3 = model.TSN_SendingTask('T3', 1, 2, 1, 0b0010,
                               tas_cycle_time=1000000,
                               tas_window_time=500000)
    r14_2.bind_task(t3)

    # Connect tasks: t1 -> t2 -> t3
    t1.link_dependent_task(t2)
    t2.link_dependent_task(t3)

    # Create a path (task chain) - this should fail validation
    path = model.Path("Path14", [t1, t2, t3])
    s.bind_path(path)

    t1.in_event_model = model.PJdEventModel(P=1000, J=0)

    # Should raise ValueError
    try:
        results = analysis.analyze_system(s)
        print("FAILED: Analysis should have raised ValueError!")
    except ValueError as e:
        print(f"SUCCESS: Expected error caught: {e}")


def test_invalid_chain_different_tas_params():
    """Test invalid task chain with TAS tasks having different parameters"""
    print("\n" + "="*60)
    print("Test 15: Invalid Task Chain - Different TAS Parameters (should fail)")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r15_1 = s.bind_resource(model.Resource("R15_1", schedulers.SPPScheduler()))
    r15_2 = s.bind_resource(model.Resource("R15_2", schedulers.SPPScheduler()))

    # Chain: t1 -> t2 -> t3, all using TAS but with different tas_window_time
    t1 = model.TSN_SendingTask('T1', 1, 2, 1, 0b0010,
                               tas_cycle_time=1000000,
                               tas_window_time=500000)
    r15_1.bind_task(t1)

    t2 = model.TSN_SendingTask('T2', 1, 2, 1, 0b0010,
                               tas_cycle_time=1000000,
                               tas_window_time=400000)  # Different!
    r15_1.bind_task(t2)

    t3 = model.TSN_SendingTask('T3', 1, 2, 1, 0b0010,
                               tas_cycle_time=1000000,
                               tas_window_time=500000)
    r15_2.bind_task(t3)

    # Connect tasks: t1 -> t2 -> t3
    t1.link_dependent_task(t2)
    t2.link_dependent_task(t3)

    # Create a path (task chain) - this should fail validation
    path = model.Path("Path15", [t1, t2, t3])
    s.bind_path(path)

    t1.in_event_model = model.PJdEventModel(P=1000, J=0)

    # Should raise ValueError
    try:
        results = analysis.analyze_system(s)
        print("FAILED: Analysis should have raised ValueError!")
    except ValueError as e:
        print(f"SUCCESS: Expected error caught: {e}")


def test_valid_chain_same_cqf():
    """Test valid task chain with all tasks using CQF with same parameters"""
    print("\n" + "="*60)
    print("Test 16: Valid Task Chain - All Tasks with Same CQF")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r16_1 = s.bind_resource(model.Resource("R16_1", schedulers.SPPScheduler()))
    r16_2 = s.bind_resource(model.Resource("R16_2", schedulers.SPPScheduler()))

    # Chain: t1 -> t2 -> t3, all using CQF with same parameters
    t1 = model.TSN_SendingTask('T1', 1, 2, 1, 0b0100,
                               cqf_cycle_time=2000000)
    r16_1.bind_task(t1)

    t2 = model.TSN_SendingTask('T2', 1, 2, 1, 0b0100,
                               cqf_cycle_time=2000000)
    r16_1.bind_task(t2)

    t3 = model.TSN_SendingTask('T3', 1, 2, 1, 0b0100,
                               cqf_cycle_time=2000000)
    r16_2.bind_task(t3)

    # Connect tasks: t1 -> t2 -> t3
    t1.link_dependent_task(t2)
    t2.link_dependent_task(t3)

    # Create a path (task chain)
    path = model.Path("Path16", [t1, t2, t3])
    s.bind_path(path)

    t1.in_event_model = model.PJdEventModel(P=1000, J=0)

    # Should NOT raise ValueError
    try:
        results = analysis.analyze_system(s)
        print("SUCCESS: Analysis completed without errors!")
        print("All CQF tasks in chain have same parameters (valid)")
    except ValueError as e:
        print(f"FAILED: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)  # Reduce output noise

    print("\n" + "#"*60)
    print("# TSN Parameter Validation Tests")
    print("#"*60)

    # Valid configurations
    test_valid_tas_configuration()
    test_valid_cqf_with_tas()
    test_cqf_only_same_cycle()
    test_mixed_tas_cqf_full_valid()
    test_cqf_mixed_valid_even_multiple()
    test_no_tsn_tasks()
    test_cqf_equal_to_tas_cycle()
    test_valid_chain_same_tas()
    test_valid_chain_same_cqf()

    # Invalid configurations (should raise ValueError)
    test_invalid_tas_different_cycle_times()
    test_invalid_tas_same_sched_param_different_window()
    test_invalid_cqf_not_even_multiple_of_tas()
    test_invalid_cqf_different_cycle_times()
    test_cqf_less_than_tas_cycle()
    test_invalid_chain_mixed_mechanisms()
    test_invalid_chain_different_tas_params()

    print("\n" + "#"*60)
    print("# All tests completed!")
    print("#"*60)
