"""
Test TSN mechanism configuration via TSN_Resource with plain Task objects

All TSN mechanism configuration is done on the TSN_Resource via priority_mechanism_map
and per-priority parameter dictionaries. A plain Task's scheduling_parameter (priority)
determines which mechanism it uses by looking up the resource's map.

Test Cases Summary:
===================

Test 1: Single Mechanism (CBS) via resource map
Test 2: Single Mechanism (CQF) via resource map
Test 3: TAS mechanism via resource map
Test 4: CBS with preemption via resource map
Test 5: Plain Task in a complete pycpa system with analysis
Test 6: Parameter validation — missing CBS idleslope on resource
Test 7: Parameter validation — missing TAS window time on resource
Test 8: CQF alone — single mechanism is valid
"""

import logging
from pycpa import model
from pycpa import analysis
from pycpa import schedulers
from pycpa import options


def test_single_cbs():
    """Test plain Task with CBS mechanism configured on resource"""
    print("\n" + "="*60)
    print("Test 1: Single Mechanism (CBS) via Resource Map")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r = s.bind_resource(model.TSN_Resource("R1", schedulers.SPPScheduler(),
        priority_mechanism_map={1: 'CBS'},
        idleslope_by_priority={1: 5000000},
    ))

    task1 = model.Task('CBS_Task', 10, 20, 1)
    r.bind_task(task1)
    task1.in_event_model = model.PJdEventModel(P=10000, J=0)

    print(f"Task name: {task1.name}")
    print(f"BCET: {task1.bcet}, WCET: {task1.wcet}")
    print(f"Uses CBS: {r.priority_uses_cbs(task1.scheduling_parameter)}")
    print(f"Effective idleslope: {r.effective_idleslope(task1.scheduling_parameter)}")
    print(f"Validation: {r.validate_task_parameters(task1)}")


def test_single_cqf():
    """Test plain Task with CQF mechanism configured on resource"""
    print("\n" + "="*60)
    print("Test 2: Single Mechanism (CQF) via Resource Map")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r = s.bind_resource(model.TSN_Resource("R2", schedulers.SPPScheduler(),
        priority_mechanism_map={(5, 4): 'CQF'},
        cqf_cycle_time_by_pair={(5, 4): 250000},
    ))

    task2 = model.Task('CQF_Task', 15, 30, 5)
    r.bind_task(task2)
    task2.in_event_model = model.PJdEventModel(P=10000, J=0)

    print(f"Task name: {task2.name}")
    print(f"BCET: {task2.bcet}, WCET: {task2.wcet}")
    print(f"Uses CQF: {r.priority_uses_cqf(task2.scheduling_parameter)}")
    print(f"Effective cqf_cycle_time: {r.effective_cqf_cycle_time(task2.scheduling_parameter)}")
    print(f"Validation: {r.validate_task_parameters(task2)}")


def test_tas_mechanism():
    """Test TAS mechanism via resource map"""
    print("\n" + "="*60)
    print("Test 3: TAS Mechanism via Resource Map")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r = s.bind_resource(model.TSN_Resource("R3", schedulers.SPPScheduler(),
        priority_mechanism_map={7: 'TAS', 6: 'TAS'},
        tas_cycle_time=2000000,
        tas_window_time_by_priority={7: 1000000, 6: 800000},
    ))

    task3 = model.Task('TAS_Task_P7', 20, 40, 7)
    r.bind_task(task3)
    task3.in_event_model = model.PJdEventModel(P=10000, J=0)

    task4 = model.Task('TAS_Task_P6', 20, 40, 6)
    r.bind_task(task4)
    task4.in_event_model = model.PJdEventModel(P=10000, J=0)

    print(f"Task P7: uses_tas={r.priority_uses_tas(7)}, cycle={r.effective_tas_cycle_time(7)}, "
          f"window={r.effective_tas_window_time(7)}")
    print(f"Task P6: uses_tas={r.priority_uses_tas(6)}, cycle={r.effective_tas_cycle_time(6)}, "
          f"window={r.effective_tas_window_time(6)}")
    print(f"Validation P7: {r.validate_task_parameters(task3)}")
    print(f"Validation P6: {r.validate_task_parameters(task4)}")


def test_cbs_with_preemption():
    """Test CBS with preemption configured on resource"""
    print("\n" + "="*60)
    print("Test 4: CBS with Preemption via Resource Map")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r = s.bind_resource(model.TSN_Resource("R4", schedulers.SPPScheduler(),
        priority_mechanism_map={3: 'CBS'},
        idleslope_by_priority={3: 8000000},
        is_express_by_priority={3: False},
    ))

    task5 = model.Task('CBS_Prep_Task', 18, 35, 3)
    r.bind_task(task5)
    task5.in_event_model = model.PJdEventModel(P=10000, J=0)

    print(f"Task name: {task5.name}")
    print(f"Uses CBS: {r.priority_uses_cbs(3)}")
    print(f"Uses Preemption: {r.priority_uses_preemption(3)}")
    print(f"Effective is_express: {r.effective_is_express(3)}")
    print(f"Effective idleslope: {r.effective_idleslope(3)}")
    print(f"Validation: {r.validate_task_parameters(task5)}")


def test_with_system():
    """Test plain Task in a complete pycpa system"""
    print("\n" + "="*60)
    print("Test 5: Plain Task on TSN_Resource in Complete System")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r1 = s.bind_resource(model.TSN_Resource("R1", schedulers.SPPScheduler(),
        priority_mechanism_map={
            1: 'TAS',
            2: None,
        },
        tas_cycle_time=1000000,
        tas_window_time_by_priority={1: 500000},
    ))

    task6 = model.Task('TAS_Task', wcet=8, bcet=4,
                        scheduling_parameter=1)
    r1.bind_task(task6)

    task7 = model.Task('Regular_Task', wcet=6, bcet=3,
                       scheduling_parameter=2)
    r1.bind_task(task7)

    task6.link_dependent_task(task7)
    task6.in_event_model = model.PJdEventModel(P=40, J=80)

    print("Performing analysis...")
    results = analysis.analyze_system(s)

    print("\nResults:")
    for r in sorted(s.resources, key=str):
        for t in sorted(r.tasks, key=str):
            print(f"  {t.name}: wcrt={results[t].wcrt}")
            res = t.resource
            if getattr(res, 'is_tsn_resource', False):
                mech = res.get_mechanism_for_priority(t.scheduling_parameter)
                print(f"    mechanism={mech}")
                if res.priority_uses_tas(t.scheduling_parameter):
                    print(f"    TAS - cycle: {res.effective_tas_cycle_time(t.scheduling_parameter)}, "
                          f"window: {res.effective_tas_window_time(t.scheduling_parameter)}")

    print("\nTask identification via resource:")
    for r in sorted(s.resources, key=str):
        for t in sorted(r.tasks, key=str):
            res = t.resource
            if getattr(res, 'is_tsn_resource', False):
                mech = res.get_mechanism_for_priority(t.scheduling_parameter)
                print(f"  {t.name} on TSN_Resource (mechanism: {mech})")
            else:
                print(f"  {t.name} on regular Resource")


def test_validations():
    """Test parameter validation - error cases"""
    print("\n" + "="*60)
    print("Test 6-8: Parameter Validation")
    print("="*60)

    options.init_pycpa()

    # 6. Missing required parameter for CBS (no idleslope_by_priority)
    print("\n6: Missing CBS idleslope on resource")
    s = model.System()
    r = s.bind_resource(model.TSN_Resource("R_bad1", schedulers.SPPScheduler(),
        priority_mechanism_map={1: 'CBS'},
    ))
    try:
        task_error = model.Task('Error_Task', 10, 20, 1)
        r.bind_task(task_error)
        task_error.in_event_model = model.PJdEventModel(P=10000, J=0)
        results = analysis.analyze_system(s)
        print("ERROR: Should have raised ValueError!")
    except ValueError as e:
        print(f"Expected error caught: {e}")

    # 7. Missing TAS window time on resource
    print("\n7: Missing TAS window time on resource")
    s = model.System()
    r = s.bind_resource(model.TSN_Resource("R_bad2", schedulers.SPPScheduler(),
        priority_mechanism_map={1: 'TAS'},
        tas_cycle_time=1000000,
    ))
    try:
        task_error = model.Task('Error_Task', 10, 20, 1)
        r.bind_task(task_error)
        task_error.in_event_model = model.PJdEventModel(P=10000, J=0)
        results = analysis.analyze_system(s)
        print("ERROR: Should have raised ValueError!")
    except ValueError as e:
        print(f"Expected error caught: {e}")

    # 8. CQF alone is valid
    print("\n8: CQF alone (should pass)")
    s = model.System()
    r = s.bind_resource(model.TSN_Resource("R_ok", schedulers.SPPScheduler(),
        priority_mechanism_map={(5, 4): 'CQF'},
        cqf_cycle_time_by_pair={(5, 4): 500000},
    ))
    try:
        task_ok = model.Task('OK_Task', 10, 20, 5)
        r.bind_task(task_ok)
        task_ok.in_event_model = model.PJdEventModel(P=10000, J=0)
        result = r.validate_task_parameters(task_ok)
        print(f"No error - CQF alone is allowed: {result}")
    except ValueError as e:
        print(f"Unexpected error: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)

    test_single_cbs()
    test_single_cqf()
    test_tas_mechanism()
    test_cbs_with_preemption()
    test_with_system()
    test_validations()

    print("\n" + "="*60)
    print("All tests completed!")
    print("="*60)
