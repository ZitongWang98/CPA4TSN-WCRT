"""
Test TSN Parameter Validation on Per-Resource and Task-Chain Basis

All TSN mechanism configuration is done on TSN_Resource via priority_mechanism_map.
Plain Task objects are used — no TSN_SendingTask needed. A task's scheduling_parameter
(priority) determines which mechanism it uses by looking up the resource's map.

Per-Resource Basis Constraints:
===============================
1. For tasks using TAS on the same resource:
   - All tas_cycle_time values must be the same (shared on resource)
   - If scheduling_parameter (priority) is the same, tas_window_time must be the same
2. For tasks using CQF on the same resource:
   - If TAS is also used, cqf_cycle_time must be equal to or an even positive integer
     multiple of tas_cycle_time
   - Between CQF pairs, cqf_cycle_time must be equal or have an even positive integer
     multiple relationship

Per-Task-Chain Basis Constraints:
=================================
3. For all TSN tasks in the same task chain (path):
   - All TSN tasks must use the same mechanism (TAS or CQF)
   - For tasks using TAS: tas_cycle_time, tas_window_time must be equal
   - For tasks using CQF: cqf_cycle_time must be equal

Priority-Mechanism Map Constraints:
===================================
4. Map self-constraints (valid mechanisms, CQF keys are 2-tuples, no duplicate priorities)
5. Parameter completeness per mechanism
6. TSN parameter constraints (cycle time relationships)
7. Task-resource mapping consistency
"""

import logging
from pycpa import model
from pycpa import analysis
from pycpa import schedulers
from pycpa import options


# ============================================================
# Valid Configuration Tests
# ============================================================

def test_valid_tas_configuration():
    """Test 1: Valid TAS - all tasks have same cycle time, per-priority window times"""
    print("\n" + "="*60)
    print("Test 1: Valid TAS Configuration")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r1 = s.bind_resource(model.TSN_Resource("R1", schedulers.SPPScheduler(),
        priority_mechanism_map={1: 'TAS', 2: 'TAS'},
        tas_cycle_time=1000000,
        tas_window_time_by_priority={1: 500000, 2: 600000},
    ))

    task1 = model.Task('TAS_Task1', 1, 2, 1)
    r1.bind_task(task1)
    task2 = model.Task('TAS_Task2', 1, 2, 1)
    r1.bind_task(task2)
    task3 = model.Task('TAS_Task3', 1, 2, 2)
    r1.bind_task(task3)

    for t in r1.tasks:
        t.in_event_model = model.PJdEventModel(P=1000, J=0)

    try:
        results = analysis.analyze_system(s)
        print("SUCCESS: Analysis completed without errors!")
        for t in r1.tasks:
            print(f"  {t.name}: tas_cycle_time={r1.effective_tas_cycle_time(t.scheduling_parameter)}, "
                  f"tas_window_time={r1.effective_tas_window_time(t.scheduling_parameter)}, "
                  f"scheduling_parameter={t.scheduling_parameter}")
    except ValueError as e:
        print(f"FAILED: {e}")


def test_invalid_tas_different_cycle_times():
    """Test 2: Invalid TAS - different cycle times across chain"""
    print("\n" + "="*60)
    print("Test 2: Invalid TAS - Different Cycle Times (should fail)")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r1 = s.bind_resource(model.TSN_Resource("R1", schedulers.SPPScheduler(),
        priority_mechanism_map={1: 'TAS'},
        tas_cycle_time=1000000,
        tas_window_time_by_priority={1: 500000},
    ))
    r2 = s.bind_resource(model.TSN_Resource("R2", schedulers.SPPScheduler(),
        priority_mechanism_map={2: 'TAS'},
        tas_cycle_time=2000000,
        tas_window_time_by_priority={2: 1000000},
    ))

    task1 = model.Task('TAS_Task1', 1, 2, 1)
    r1.bind_task(task1)
    task2 = model.Task('TAS_Task2', 1, 2, 2)
    r2.bind_task(task2)

    task1.link_dependent_task(task2)
    path = model.Path("Path2", [task1, task2])
    s.bind_path(path)

    task1.in_event_model = model.PJdEventModel(P=1000, J=0)

    try:
        results = analysis.analyze_system(s)
        print("FAILED: Analysis should have raised ValueError!")
    except ValueError as e:
        print(f"SUCCESS: Expected error caught: {e}")


def test_invalid_tas_same_sched_param_different_window():
    """Test 3: Invalid TAS - same priority, different window in chain"""
    print("\n" + "="*60)
    print("Test 3: Invalid TAS - Same sched_param, Different Window (should fail)")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r1 = s.bind_resource(model.TSN_Resource("R1", schedulers.SPPScheduler(),
        priority_mechanism_map={1: 'TAS'},
        tas_cycle_time=1000000,
        tas_window_time_by_priority={1: 500000},
    ))
    r2 = s.bind_resource(model.TSN_Resource("R2", schedulers.SPPScheduler(),
        priority_mechanism_map={1: 'TAS'},
        tas_cycle_time=1000000,
        tas_window_time_by_priority={1: 600000},
    ))

    task1 = model.Task('TAS_Task1', 1, 2, 1)
    r1.bind_task(task1)
    task2 = model.Task('TAS_Task2', 1, 2, 1)
    r2.bind_task(task2)

    task1.link_dependent_task(task2)
    path = model.Path("Path3", [task1, task2])
    s.bind_path(path)

    task1.in_event_model = model.PJdEventModel(P=1000, J=0)

    try:
        results = analysis.analyze_system(s)
        print("SUCCESS: Analysis completed - both tasks get window_time from resource")
    except ValueError as e:
        print(f"SUCCESS: Expected error caught: {e}")


def test_valid_cqf_with_tas():
    """Test 4: Valid CQF with TAS - CQF cycle is even multiple of TAS cycle"""
    print("\n" + "="*60)
    print("Test 4: Valid CQF with TAS")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r = s.bind_resource(model.TSN_Resource("R4", schedulers.SPPScheduler(),
        priority_mechanism_map={
            1: 'TAS',
            (2, 3): 'CQF',
            (4, 5): 'CQF',
        },
        tas_cycle_time=1000000,
        tas_window_time_by_priority={1: 500000},
        cqf_cycle_time_by_pair={(2, 3): 2000000, (4, 5): 4000000},
    ))

    tas_task = model.Task('TAS_Task', 1, 2, 1)
    r.bind_task(tas_task)
    cqf_task1 = model.Task('CQF_Task1', 1, 2, 2)
    r.bind_task(cqf_task1)
    cqf_task2 = model.Task('CQF_Task2', 1, 2, 4)
    r.bind_task(cqf_task2)

    for t in r.tasks:
        t.in_event_model = model.PJdEventModel(P=10000, J=0)

    try:
        results = analysis.analyze_system(s)
        print("SUCCESS: Analysis completed without errors!")
    except ValueError as e:
        print(f"FAILED: {e}")


def test_invalid_cqf_not_even_multiple_of_tas():
    """Test 5: Invalid CQF - 3x TAS cycle (odd multiple)"""
    print("\n" + "="*60)
    print("Test 5: Invalid CQF - Not Even Multiple of TAS (should fail)")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r = s.bind_resource(model.TSN_Resource("R5", schedulers.SPPScheduler(),
        priority_mechanism_map={
            1: 'TAS',
            (2, 3): 'CQF',
        },
        tas_cycle_time=1000000,
        tas_window_time_by_priority={1: 500000},
        cqf_cycle_time_by_pair={(2, 3): 3000000},
    ))

    tas_task = model.Task('TAS_Task', 1, 2, 1)
    r.bind_task(tas_task)
    cqf_task = model.Task('CQF_Task', 1, 2, 2)
    r.bind_task(cqf_task)

    for t in r.tasks:
        t.in_event_model = model.PJdEventModel(P=10000, J=0)

    try:
        results = analysis.analyze_system(s)
        print("FAILED: Analysis should have raised ValueError!")
    except ValueError as e:
        print(f"SUCCESS: Expected error caught: {e}")


def test_invalid_cqf_different_cycle_times():
    """Test 6: Invalid CQF - no even multiple relation between CQF pairs in chain"""
    print("\n" + "="*60)
    print("Test 6: Invalid CQF - No Even Multiple Relation (should fail)")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r1 = s.bind_resource(model.TSN_Resource("R6a", schedulers.SPPScheduler(),
        priority_mechanism_map={(1, 2): 'CQF'},
        cqf_cycle_time_by_pair={(1, 2): 2000000},
    ))
    r2 = s.bind_resource(model.TSN_Resource("R6b", schedulers.SPPScheduler(),
        priority_mechanism_map={(1, 2): 'CQF'},
        cqf_cycle_time_by_pair={(1, 2): 3000000},
    ))

    cqf_task1 = model.Task('CQF_Task1', 1, 2, 1)
    r1.bind_task(cqf_task1)
    cqf_task2 = model.Task('CQF_Task2', 1, 2, 1)
    r2.bind_task(cqf_task2)

    cqf_task1.link_dependent_task(cqf_task2)
    path = model.Path("Path6", [cqf_task1, cqf_task2])
    s.bind_path(path)

    cqf_task1.in_event_model = model.PJdEventModel(P=10000, J=0)

    try:
        results = analysis.analyze_system(s)
        print("FAILED: Analysis should have raised ValueError!")
    except ValueError as e:
        print(f"SUCCESS: Expected error caught: {e}")


def test_cqf_only_same_cycle():
    """Test 7: CQF Only - same cycle time"""
    print("\n" + "="*60)
    print("Test 7: CQF Only - Same Cycle Time")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r = s.bind_resource(model.TSN_Resource("R7", schedulers.SPPScheduler(),
        priority_mechanism_map={(1, 2): 'CQF'},
        cqf_cycle_time_by_pair={(1, 2): 2000000},
    ))

    cqf_task1 = model.Task('CQF_Task1', 1, 2, 1)
    r.bind_task(cqf_task1)
    cqf_task2 = model.Task('CQF_Task2', 1, 2, 2)
    r.bind_task(cqf_task2)

    for t in r.tasks:
        t.in_event_model = model.PJdEventModel(P=10000, J=0)

    try:
        results = analysis.analyze_system(s)
        print("SUCCESS: Analysis completed without errors!")
    except ValueError as e:
        print(f"FAILED: {e}")


def test_mixed_tas_cqf_full_valid():
    """Test 8: Mixed TAS and CQF - full valid configuration"""
    print("\n" + "="*60)
    print("Test 8: Mixed TAS and CQF - Full Valid Configuration")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r = s.bind_resource(model.TSN_Resource("R8", schedulers.SPPScheduler(),
        priority_mechanism_map={
            1: 'TAS',
            2: 'TAS',
            (3, 4): 'CQF',
            (5, 6): 'CQF',
        },
        tas_cycle_time=1000000,
        tas_window_time_by_priority={1: 500000, 2: 600000},
        cqf_cycle_time_by_pair={(3, 4): 2000000, (5, 6): 4000000},
    ))

    tas_task1 = model.Task('TAS1', 1, 2, 1)
    r.bind_task(tas_task1)
    tas_task2 = model.Task('TAS2', 1, 2, 1)
    r.bind_task(tas_task2)
    tas_task3 = model.Task('TAS3', 1, 2, 2)
    r.bind_task(tas_task3)
    cqf_task1 = model.Task('CQF1', 1, 2, 3)
    r.bind_task(cqf_task1)
    cqf_task2 = model.Task('CQF2', 1, 2, 5)
    r.bind_task(cqf_task2)

    for t in r.tasks:
        t.in_event_model = model.PJdEventModel(P=10000, J=0)

    try:
        results = analysis.analyze_system(s)
        print("SUCCESS: Analysis completed without errors!")
    except ValueError as e:
        print(f"FAILED: {e}")


def test_cqf_mixed_valid_even_multiple():
    """Test 9: CQF Only - valid even multiple relationship"""
    print("\n" + "="*60)
    print("Test 9: CQF Only - Valid Even Multiple Relationship")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r = s.bind_resource(model.TSN_Resource("R9", schedulers.SPPScheduler(),
        priority_mechanism_map={
            (1, 2): 'CQF',
            (3, 4): 'CQF',
            (5, 6): 'CQF',
        },
        cqf_cycle_time_by_pair={(1, 2): 2000000, (3, 4): 4000000, (5, 6): 8000000},
    ))

    cqf_task1 = model.Task('CQF1', 1, 2, 1)
    r.bind_task(cqf_task1)
    cqf_task2 = model.Task('CQF2', 1, 2, 3)
    r.bind_task(cqf_task2)
    cqf_task3 = model.Task('CQF3', 1, 2, 5)
    r.bind_task(cqf_task3)

    for t in r.tasks:
        t.in_event_model = model.PJdEventModel(P=100000, J=0)

    try:
        results = analysis.analyze_system(s)
        print("SUCCESS: Analysis completed without errors!")
    except ValueError as e:
        print(f"FAILED: {e}")


def test_no_tsn_tasks():
    """Test 10: No TSN Tasks - only regular Task objects on regular Resource"""
    print("\n" + "="*60)
    print("Test 10: No TSN Tasks")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r = s.bind_resource(model.Resource("R10", schedulers.SPPScheduler()))

    task1 = model.Task('Task1', 1, 2, 1)
    r.bind_task(task1)
    task2 = model.Task('Task2', 1, 2, 2)
    r.bind_task(task2)

    for t in r.tasks:
        t.in_event_model = model.PJdEventModel(P=1000, J=0)

    try:
        results = analysis.analyze_system(s)
        print("SUCCESS: Analysis completed without errors!")
    except ValueError as e:
        print(f"FAILED: {e}")


def test_cqf_less_than_tas_cycle():
    """Test 11: Invalid CQF - less than TAS cycle time"""
    print("\n" + "="*60)
    print("Test 11: Invalid CQF - Less Than TAS Cycle (should fail)")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r = s.bind_resource(model.TSN_Resource("R11", schedulers.SPPScheduler(),
        priority_mechanism_map={
            1: 'TAS',
            (2, 3): 'CQF',
        },
        tas_cycle_time=1000000,
        tas_window_time_by_priority={1: 500000},
        cqf_cycle_time_by_pair={(2, 3): 500000},
    ))

    tas_task = model.Task('TAS_Task', 1, 2, 1)
    r.bind_task(tas_task)
    cqf_task = model.Task('CQF_Task', 1, 2, 2)
    r.bind_task(cqf_task)

    for t in r.tasks:
        t.in_event_model = model.PJdEventModel(P=10000, J=0)

    try:
        results = analysis.analyze_system(s)
        print("FAILED: Analysis should have raised ValueError!")
    except ValueError as e:
        print(f"SUCCESS: Expected error caught: {e}")


def test_cqf_equal_to_tas_cycle():
    """Test 12: Valid CQF - equal to TAS cycle (1x is allowed)"""
    print("\n" + "="*60)
    print("Test 12: Valid CQF - Equal to TAS Cycle")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r = s.bind_resource(model.TSN_Resource("R12", schedulers.SPPScheduler(),
        priority_mechanism_map={
            1: 'TAS',
            (2, 3): 'CQF',
        },
        tas_cycle_time=1000000,
        tas_window_time_by_priority={1: 500000},
        cqf_cycle_time_by_pair={(2, 3): 1000000},
    ))

    tas_task = model.Task('TAS_Task', 1, 2, 1)
    r.bind_task(tas_task)
    cqf_task = model.Task('CQF_Task', 1, 2, 2)
    r.bind_task(cqf_task)

    for t in r.tasks:
        t.in_event_model = model.PJdEventModel(P=10000, J=0)

    try:
        results = analysis.analyze_system(s)
        print("SUCCESS: Analysis completed without errors!")
    except ValueError as e:
        print(f"FAILED: {e}")


def test_valid_chain_same_tas():
    """Test 13: Valid Task Chain - all TAS with same parameters"""
    print("\n" + "="*60)
    print("Test 13: Valid Task Chain - All Tasks with Same TAS")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r1 = s.bind_resource(model.TSN_Resource("R13_1", schedulers.SPPScheduler(),
        priority_mechanism_map={1: 'TAS'},
        tas_cycle_time=1000000,
        tas_window_time_by_priority={1: 500000},
    ))
    r2 = s.bind_resource(model.TSN_Resource("R13_2", schedulers.SPPScheduler(),
        priority_mechanism_map={1: 'TAS'},
        tas_cycle_time=1000000,
        tas_window_time_by_priority={1: 500000},
    ))

    t1 = model.Task('T1', 1, 2, 1)
    r1.bind_task(t1)
    t2 = model.Task('T2', 1, 2, 1)
    r1.bind_task(t2)
    t3 = model.Task('T3', 1, 2, 1)
    r2.bind_task(t3)

    t1.link_dependent_task(t2)
    t2.link_dependent_task(t3)
    path = model.Path("Path13", [t1, t2, t3])
    s.bind_path(path)

    t1.in_event_model = model.PJdEventModel(P=1000, J=0)

    try:
        results = analysis.analyze_system(s)
        print("SUCCESS: Analysis completed without errors!")
    except ValueError as e:
        print(f"FAILED: {e}")


def test_invalid_chain_mixed_mechanisms():
    """Test 14: Invalid Task Chain - TAS and CQF mixed"""
    print("\n" + "="*60)
    print("Test 14: Invalid Task Chain - TAS and CQF Mixed (should fail)")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r1 = s.bind_resource(model.TSN_Resource("R14_1", schedulers.SPPScheduler(),
        priority_mechanism_map={1: 'TAS'},
        tas_cycle_time=1000000,
        tas_window_time_by_priority={1: 500000},
    ))
    r2 = s.bind_resource(model.TSN_Resource("R14_2", schedulers.SPPScheduler(),
        priority_mechanism_map={(1, 2): 'CQF'},
        cqf_cycle_time_by_pair={(1, 2): 2000000},
    ))
    r3 = s.bind_resource(model.TSN_Resource("R14_3", schedulers.SPPScheduler(),
        priority_mechanism_map={1: 'TAS'},
        tas_cycle_time=1000000,
        tas_window_time_by_priority={1: 500000},
    ))

    t1 = model.Task('T1', 1, 2, 1)
    r1.bind_task(t1)
    t2 = model.Task('T2', 1, 2, 1)
    r2.bind_task(t2)
    t3 = model.Task('T3', 1, 2, 1)
    r3.bind_task(t3)

    t1.link_dependent_task(t2)
    t2.link_dependent_task(t3)
    path = model.Path("Path14", [t1, t2, t3])
    s.bind_path(path)

    t1.in_event_model = model.PJdEventModel(P=1000, J=0)

    try:
        results = analysis.analyze_system(s)
        print("FAILED: Analysis should have raised ValueError!")
    except ValueError as e:
        print(f"SUCCESS: Expected error caught: {e}")


def test_invalid_chain_different_tas_params():
    """Test 15: Invalid Task Chain - different TAS window times"""
    print("\n" + "="*60)
    print("Test 15: Invalid Task Chain - Different TAS Parameters (should fail)")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r1 = s.bind_resource(model.TSN_Resource("R15_1", schedulers.SPPScheduler(),
        priority_mechanism_map={1: 'TAS'},
        tas_cycle_time=1000000,
        tas_window_time_by_priority={1: 500000},
    ))
    r2 = s.bind_resource(model.TSN_Resource("R15_2", schedulers.SPPScheduler(),
        priority_mechanism_map={1: 'TAS'},
        tas_cycle_time=1000000,
        tas_window_time_by_priority={1: 500000},
    ))
    r3 = s.bind_resource(model.TSN_Resource("R15_3", schedulers.SPPScheduler(),
        priority_mechanism_map={1: 'TAS'},
        tas_cycle_time=1000000,
        tas_window_time_by_priority={1: 400000},
    ))

    t1 = model.Task('T1', 1, 2, 1)
    r1.bind_task(t1)
    t2 = model.Task('T2', 1, 2, 1)
    r2.bind_task(t2)
    t3 = model.Task('T3', 1, 2, 1)
    r3.bind_task(t3)

    t1.link_dependent_task(t2)
    t2.link_dependent_task(t3)
    path = model.Path("Path15", [t1, t2, t3])
    s.bind_path(path)

    t1.in_event_model = model.PJdEventModel(P=1000, J=0)

    try:
        results = analysis.analyze_system(s)
        print("FAILED: Analysis should have raised ValueError!")
    except ValueError as e:
        print(f"SUCCESS: Expected error caught: {e}")


def test_valid_chain_same_cqf():
    """Test 16: Valid Task Chain - all CQF with same parameters"""
    print("\n" + "="*60)
    print("Test 16: Valid Task Chain - All Tasks with Same CQF")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r1 = s.bind_resource(model.TSN_Resource("R16_1", schedulers.SPPScheduler(),
        priority_mechanism_map={(1, 2): 'CQF'},
        cqf_cycle_time_by_pair={(1, 2): 2000000},
    ))
    r2 = s.bind_resource(model.TSN_Resource("R16_2", schedulers.SPPScheduler(),
        priority_mechanism_map={(1, 2): 'CQF'},
        cqf_cycle_time_by_pair={(1, 2): 2000000},
    ))

    t1 = model.Task('T1', 1, 2, 1)
    r1.bind_task(t1)
    t2 = model.Task('T2', 1, 2, 1)
    r1.bind_task(t2)
    t3 = model.Task('T3', 1, 2, 1)
    r2.bind_task(t3)

    t1.link_dependent_task(t2)
    t2.link_dependent_task(t3)
    path = model.Path("Path16", [t1, t2, t3])
    s.bind_path(path)

    t1.in_event_model = model.PJdEventModel(P=1000, J=0)

    try:
        results = analysis.analyze_system(s)
        print("SUCCESS: Analysis completed without errors!")
    except ValueError as e:
        print(f"FAILED: {e}")


# ============================================================
# Priority-Mechanism Map Tests
# ============================================================

def test_map_valid_full_config():
    """MAP-1: Valid full priority_mechanism_map with TAS, CQF, CBS, ATS, and None."""
    print("\n" + "="*60)
    print("Test MAP-1: Valid Full Priority-Mechanism Map Configuration")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r = s.bind_resource(model.TSN_Resource("Port1", schedulers.SPPScheduler(),
        priority_mechanism_map={
            7: 'TAS',
            6: 'TAS',
            (5, 4): 'CQF',
            3: 'ATS',
            1: 'CBS',
            0: None,
        },
        tas_cycle_time=1000,
        tas_window_time_by_priority={7: 100, 6: 200},
        cqf_cycle_time_by_pair={(5, 4): 1000},
        idleslope_by_priority={1: 5000000},
        ats_params_by_priority={3: {'cir': 2000000, 'cbs': 10000, 'eir': 500000,
                                    'ebs': 5000, 'scheduler_group': 1}},
    ))

    t7 = model.Task('T_P7', 1, 2, 7)
    r.bind_task(t7)
    t6 = model.Task('T_P6', 1, 2, 6)
    r.bind_task(t6)
    t5 = model.Task('T_P5', 1, 2, 5)
    r.bind_task(t5)
    t3 = model.Task('T_P3', 1, 2, 3)
    r.bind_task(t3)
    t1 = model.Task('T_P1', 1, 2, 1)
    r.bind_task(t1)
    t0 = model.Task('T_P0', 1, 2, 0)
    r.bind_task(t0)

    for t in r.tasks:
        t.in_event_model = model.PJdEventModel(P=10000, J=0)

    try:
        results = analysis.analyze_system(s)
        print("SUCCESS: Full map configuration validated!")
        print(f"  T_P7 uses_tas={r.priority_uses_tas(7)}, mechanism={r.get_mechanism_for_priority(7)}")
        print(f"  T_P6 uses_tas={r.priority_uses_tas(6)}, mechanism={r.get_mechanism_for_priority(6)}")
        print(f"  T_P5 uses_cqf={r.priority_uses_cqf(5)}, mechanism={r.get_mechanism_for_priority(5)}")
        print(f"  T_P3 uses_ats={r.priority_uses_ats(3)}, mechanism={r.get_mechanism_for_priority(3)}")
        print(f"  T_P1 uses_cbs={r.priority_uses_cbs(1)}, mechanism={r.get_mechanism_for_priority(1)}")
        print(f"  T_P0 mechanism={r.get_mechanism_for_priority(0)}")
    except ValueError as e:
        print(f"FAILED: {e}")


def test_map_valid_tas_only():
    """MAP-2: Valid map with only TAS priorities."""
    print("\n" + "="*60)
    print("Test MAP-2: Valid Map - TAS Only")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r = s.bind_resource(model.TSN_Resource("Port2", schedulers.SPPScheduler(),
        priority_mechanism_map={7: 'TAS', 6: 'TAS'},
        tas_cycle_time=1000,
        tas_window_time_by_priority={7: 100, 6: 200},
    ))

    t7 = model.Task('T7', 1, 2, 7)
    r.bind_task(t7)
    t6 = model.Task('T6', 1, 2, 6)
    r.bind_task(t6)

    for t in r.tasks:
        t.in_event_model = model.PJdEventModel(P=10000, J=0)

    try:
        results = analysis.analyze_system(s)
        print("SUCCESS: TAS-only map validated!")
        print(f"  T7 effective_tas_window_time={r.effective_tas_window_time(7)}")
        print(f"  T6 effective_tas_window_time={r.effective_tas_window_time(6)}")
    except ValueError as e:
        print(f"FAILED: {e}")


def test_map_valid_multiple_cqf_pairs():
    """MAP-3: Valid map with multiple CQF pairs having even-multiple cycle times."""
    print("\n" + "="*60)
    print("Test MAP-3: Valid Map - Multiple CQF Pairs (Even Multiple)")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r = s.bind_resource(model.TSN_Resource("Port3", schedulers.SPPScheduler(),
        priority_mechanism_map={
            (7, 6): 'CQF',
            (5, 4): 'CQF',
        },
        cqf_cycle_time_by_pair={(7, 6): 1000, (5, 4): 2000},
    ))

    t7 = model.Task('T7', 1, 2, 7)
    r.bind_task(t7)
    t5 = model.Task('T5', 1, 2, 5)
    r.bind_task(t5)

    for t in r.tasks:
        t.in_event_model = model.PJdEventModel(P=10000, J=0)

    try:
        results = analysis.analyze_system(s)
        print("SUCCESS: Multiple CQF pairs validated!")
        print(f"  T7 cqf_cycle_time={r.effective_cqf_cycle_time(7)}")
        print(f"  T5 cqf_cycle_time={r.effective_cqf_cycle_time(5)}")
    except ValueError as e:
        print(f"FAILED: {e}")


def test_map_valid_auto_derive():
    """MAP-4: Mechanism is auto-derived from resource map."""
    print("\n" + "="*60)
    print("Test MAP-4: Auto-Derive Mechanism from Map")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r = s.bind_resource(model.TSN_Resource("Port4", schedulers.SPPScheduler(),
        priority_mechanism_map={
            7: 'TAS',
            (5, 4): 'CQF',
            1: 'CBS',
            0: None,
        },
        tas_cycle_time=1000,
        tas_window_time_by_priority={7: 100},
        cqf_cycle_time_by_pair={(5, 4): 1000},
        idleslope_by_priority={1: 5000000},
    ))

    t_tas = model.Task('T_TAS', 1, 2, 7)
    r.bind_task(t_tas)
    t_cqf = model.Task('T_CQF', 1, 2, 5)
    r.bind_task(t_cqf)
    t_cbs = model.Task('T_CBS', 1, 2, 1)
    r.bind_task(t_cbs)
    t_none = model.Task('T_NONE', 1, 2, 0)
    r.bind_task(t_none)

    for t in r.tasks:
        t.in_event_model = model.PJdEventModel(P=10000, J=0)

    try:
        results = analysis.analyze_system(s)
        assert r.priority_uses_tas(7), "Priority 7 should use TAS"
        assert r.priority_uses_cqf(5), "Priority 5 should use CQF"
        assert r.priority_uses_cbs(1), "Priority 1 should use CBS"
        assert not r.priority_uses_tas(0) and not r.priority_uses_cqf(0), "Priority 0 should use nothing"
        print("SUCCESS: Mechanisms auto-derived correctly!")
        print(f"  T_TAS: mechanism={r.get_mechanism_for_priority(7)}, uses_tas={r.priority_uses_tas(7)}")
        print(f"  T_CQF: mechanism={r.get_mechanism_for_priority(5)}, uses_cqf={r.priority_uses_cqf(5)}")
        print(f"  T_CBS: mechanism={r.get_mechanism_for_priority(1)}, uses_cbs={r.priority_uses_cbs(1)}")
        print(f"  T_NONE: mechanism={r.get_mechanism_for_priority(0)}")
    except (ValueError, AssertionError) as e:
        print(f"FAILED: {e}")


def test_map_invalid_mechanism_name():
    """MAP-5: Invalid mechanism name in map."""
    print("\n" + "="*60)
    print("Test MAP-5: Invalid Mechanism Name (should fail)")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r = s.bind_resource(model.TSN_Resource("PortBad1", schedulers.SPPScheduler(),
        priority_mechanism_map={7: 'INVALID_MECH'},
    ))

    t = model.Task('T1', 1, 2, 7)
    r.bind_task(t)
    t.in_event_model = model.PJdEventModel(P=10000, J=0)

    try:
        results = analysis.analyze_system(s)
        print("FAILED: Should have raised ValueError!")
    except ValueError as e:
        print(f"SUCCESS: Expected error caught: {e}")


def test_map_invalid_cqf_single_priority():
    """MAP-6: CQF with single priority key (needs tuple of 2)."""
    print("\n" + "="*60)
    print("Test MAP-6: CQF with Single Priority Key (should fail)")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r = s.bind_resource(model.TSN_Resource("PortBad2", schedulers.SPPScheduler(),
        priority_mechanism_map={5: 'CQF'},
        cqf_cycle_time_by_pair={},
    ))

    t = model.Task('T1', 1, 2, 5)
    r.bind_task(t)
    t.in_event_model = model.PJdEventModel(P=10000, J=0)

    try:
        results = analysis.analyze_system(s)
        print("FAILED: Should have raised ValueError!")
    except ValueError as e:
        print(f"SUCCESS: Expected error caught: {e}")


def test_map_invalid_cqf_three_priorities():
    """MAP-7: CQF with 3-tuple key (needs exactly 2)."""
    print("\n" + "="*60)
    print("Test MAP-7: CQF with 3-Tuple Key (should fail)")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r = s.bind_resource(model.TSN_Resource("PortBad3", schedulers.SPPScheduler(),
        priority_mechanism_map={(5, 4, 3): 'CQF'},
        cqf_cycle_time_by_pair={(5, 4, 3): 500},
    ))

    t = model.Task('T1', 1, 2, 5)
    r.bind_task(t)
    t.in_event_model = model.PJdEventModel(P=10000, J=0)

    try:
        results = analysis.analyze_system(s)
        print("FAILED: Should have raised ValueError!")
    except ValueError as e:
        print(f"SUCCESS: Expected error caught: {e}")


def test_map_invalid_duplicate_priority():
    """MAP-8: Duplicate priority in map."""
    print("\n" + "="*60)
    print("Test MAP-8: Duplicate Priority in Map (should fail)")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r = s.bind_resource(model.TSN_Resource("PortBad4", schedulers.SPPScheduler(),
        priority_mechanism_map={
            7: 'TAS',
            (7, 6): 'CQF',
        },
        tas_cycle_time=1000,
        tas_window_time_by_priority={7: 100},
        cqf_cycle_time_by_pair={(7, 6): 500},
    ))

    t = model.Task('T1', 1, 2, 7)
    r.bind_task(t)
    t.in_event_model = model.PJdEventModel(P=10000, J=0)

    try:
        results = analysis.analyze_system(s)
        print("FAILED: Should have raised ValueError!")
    except ValueError as e:
        print(f"SUCCESS: Expected error caught: {e}")


def test_map_invalid_missing_tas_window():
    """MAP-9: TAS priority missing from tas_window_time_by_priority."""
    print("\n" + "="*60)
    print("Test MAP-9: Missing TAS Window Time for Priority (should fail)")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r = s.bind_resource(model.TSN_Resource("PortBad5", schedulers.SPPScheduler(),
        priority_mechanism_map={7: 'TAS', 6: 'TAS'},
        tas_cycle_time=1000,
        tas_window_time_by_priority={7: 100},
    ))

    t7 = model.Task('T7', 1, 2, 7)
    r.bind_task(t7)
    t6 = model.Task('T6', 1, 2, 6)
    r.bind_task(t6)

    for t in r.tasks:
        t.in_event_model = model.PJdEventModel(P=10000, J=0)

    try:
        results = analysis.analyze_system(s)
        print("FAILED: Should have raised ValueError!")
    except ValueError as e:
        print(f"SUCCESS: Expected error caught: {e}")


def test_map_invalid_missing_cqf_cycle():
    """MAP-10: CQF pair missing from cqf_cycle_time_by_pair."""
    print("\n" + "="*60)
    print("Test MAP-10: Missing CQF Cycle Time for Pair (should fail)")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r = s.bind_resource(model.TSN_Resource("PortBad6", schedulers.SPPScheduler(),
        priority_mechanism_map={(5, 4): 'CQF'},
    ))

    t = model.Task('T1', 1, 2, 5)
    r.bind_task(t)
    t.in_event_model = model.PJdEventModel(P=10000, J=0)

    try:
        results = analysis.analyze_system(s)
        print("FAILED: Should have raised ValueError!")
    except ValueError as e:
        print(f"SUCCESS: Expected error caught: {e}")


def test_map_invalid_missing_cbs_idleslope():
    """MAP-11: CBS priority missing from idleslope_by_priority."""
    print("\n" + "="*60)
    print("Test MAP-11: Missing CBS idleslope for Priority (should fail)")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r = s.bind_resource(model.TSN_Resource("PortBad7", schedulers.SPPScheduler(),
        priority_mechanism_map={1: 'CBS'},
    ))

    t = model.Task('T1', 1, 2, 1)
    r.bind_task(t)
    t.in_event_model = model.PJdEventModel(P=10000, J=0)

    try:
        results = analysis.analyze_system(s)
        print("FAILED: Should have raised ValueError!")
    except ValueError as e:
        print(f"SUCCESS: Expected error caught: {e}")


def test_map_invalid_missing_ats_params():
    """MAP-12: ATS priority missing from ats_params_by_priority."""
    print("\n" + "="*60)
    print("Test MAP-12: Missing ATS Params for Priority (should fail)")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r = s.bind_resource(model.TSN_Resource("PortBad8", schedulers.SPPScheduler(),
        priority_mechanism_map={4: 'ATS'},
    ))

    t = model.Task('T1', 1, 2, 4)
    r.bind_task(t)
    t.in_event_model = model.PJdEventModel(P=10000, J=0)

    try:
        results = analysis.analyze_system(s)
        print("FAILED: Should have raised ValueError!")
    except ValueError as e:
        print(f"SUCCESS: Expected error caught: {e}")


def test_map_invalid_ats_incomplete_params():
    """MAP-13: ATS with incomplete parameter dict."""
    print("\n" + "="*60)
    print("Test MAP-13: Incomplete ATS Params (should fail)")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r = s.bind_resource(model.TSN_Resource("PortBad9", schedulers.SPPScheduler(),
        priority_mechanism_map={4: 'ATS'},
        ats_params_by_priority={4: {'cir': 2000000, 'cbs': 10000}},
    ))

    t = model.Task('T1', 1, 2, 4)
    r.bind_task(t)
    t.in_event_model = model.PJdEventModel(P=10000, J=0)

    try:
        results = analysis.analyze_system(s)
        print("FAILED: Should have raised ValueError!")
    except ValueError as e:
        print(f"SUCCESS: Expected error caught: {e}")


def test_map_invalid_cqf_tas_odd_multiple():
    """MAP-14: CQF cycle time is odd multiple of TAS cycle time."""
    print("\n" + "="*60)
    print("Test MAP-14: CQF Cycle Time Odd Multiple of TAS (should fail)")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r = s.bind_resource(model.TSN_Resource("PortBad10", schedulers.SPPScheduler(),
        priority_mechanism_map={
            7: 'TAS',
            (5, 4): 'CQF',
        },
        tas_cycle_time=1000,
        tas_window_time_by_priority={7: 100},
        cqf_cycle_time_by_pair={(5, 4): 3000},
    ))

    t7 = model.Task('T7', 1, 2, 7)
    r.bind_task(t7)
    t5 = model.Task('T5', 1, 2, 5)
    r.bind_task(t5)

    for t in r.tasks:
        t.in_event_model = model.PJdEventModel(P=10000, J=0)

    try:
        results = analysis.analyze_system(s)
        print("FAILED: Should have raised ValueError!")
    except ValueError as e:
        print(f"SUCCESS: Expected error caught: {e}")


def test_map_invalid_cqf_pairs_bad_relation():
    """MAP-15: Two CQF pairs with non-even-multiple cycle times."""
    print("\n" + "="*60)
    print("Test MAP-15: CQF Pairs Bad Cycle Time Relation (should fail)")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r = s.bind_resource(model.TSN_Resource("PortBad11", schedulers.SPPScheduler(),
        priority_mechanism_map={
            (7, 6): 'CQF',
            (5, 4): 'CQF',
        },
        cqf_cycle_time_by_pair={(7, 6): 1000, (5, 4): 3000},
    ))

    t7 = model.Task('T7', 1, 2, 7)
    r.bind_task(t7)
    t5 = model.Task('T5', 1, 2, 5)
    r.bind_task(t5)

    for t in r.tasks:
        t.in_event_model = model.PJdEventModel(P=10000, J=0)

    try:
        results = analysis.analyze_system(s)
        print("FAILED: Should have raised ValueError!")
    except ValueError as e:
        print(f"SUCCESS: Expected error caught: {e}")


def test_map_invalid_task_priority_not_in_map():
    """MAP-16: Task with priority not in the map."""
    print("\n" + "="*60)
    print("Test MAP-16: Task Priority Not in Map (should fail)")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r = s.bind_resource(model.TSN_Resource("PortBad12", schedulers.SPPScheduler(),
        priority_mechanism_map={7: 'TAS'},
        tas_cycle_time=1000,
        tas_window_time_by_priority={7: 100},
    ))

    t7 = model.Task('T7', 1, 2, 7)
    r.bind_task(t7)
    t3 = model.Task('T3', 1, 2, 3)
    r.bind_task(t3)

    for t in r.tasks:
        t.in_event_model = model.PJdEventModel(P=10000, J=0)

    try:
        results = analysis.analyze_system(s)
        print("FAILED: Should have raised ValueError!")
    except ValueError as e:
        print(f"SUCCESS: Expected error caught: {e}")


def test_map_invalid_tuple_key_non_cqf():
    """MAP-17: Tuple key mapped to non-CQF mechanism."""
    print("\n" + "="*60)
    print("Test MAP-17: Tuple Key for Non-CQF Mechanism (should fail)")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r = s.bind_resource(model.TSN_Resource("PortBad14", schedulers.SPPScheduler(),
        priority_mechanism_map={(7, 6): 'TAS'},
        tas_cycle_time=1000,
        tas_window_time_by_priority={7: 100, 6: 200},
    ))

    t = model.Task('T7', 1, 2, 7)
    r.bind_task(t)
    t.in_event_model = model.PJdEventModel(P=10000, J=0)

    try:
        results = analysis.analyze_system(s)
        print("FAILED: Should have raised ValueError!")
    except ValueError as e:
        print(f"SUCCESS: Expected error caught: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)

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

    # Invalid configurations
    test_invalid_tas_different_cycle_times()
    test_invalid_tas_same_sched_param_different_window()
    test_invalid_cqf_not_even_multiple_of_tas()
    test_invalid_cqf_different_cycle_times()
    test_cqf_less_than_tas_cycle()
    test_invalid_chain_mixed_mechanisms()
    test_invalid_chain_different_tas_params()

    print("\n" + "#"*60)
    print("# Priority-Mechanism Map Tests")
    print("#"*60)

    # Map valid configurations
    test_map_valid_full_config()
    test_map_valid_tas_only()
    test_map_valid_multiple_cqf_pairs()
    test_map_valid_auto_derive()

    # Map invalid configurations
    test_map_invalid_mechanism_name()
    test_map_invalid_cqf_single_priority()
    test_map_invalid_cqf_three_priorities()
    test_map_invalid_duplicate_priority()
    test_map_invalid_missing_tas_window()
    test_map_invalid_missing_cqf_cycle()
    test_map_invalid_missing_cbs_idleslope()
    test_map_invalid_missing_ats_params()
    test_map_invalid_ats_incomplete_params()
    test_map_invalid_cqf_tas_odd_multiple()
    test_map_invalid_cqf_pairs_bad_relation()
    test_map_invalid_task_priority_not_in_map()
    test_map_invalid_tuple_key_non_cqf()

    print("\n" + "#"*60)
    print("# All tests completed!")
    print("#"*60)
