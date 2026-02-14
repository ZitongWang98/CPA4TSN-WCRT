"""
Test SendingTask class for TSN mechanisms

This example demonstrates the usage of SendingTask with various
Time-Sensitive Networking (TSN) scheduling mechanisms.
"""

import logging
from pycpa import model
from pycpa import analysis
from pycpa import schedulers
from pycpa import options

def test_single_mechanism():
    """Test SendingTask with single TSN mechanism"""
    print("\n" + "="*60)
    print("Test 1: Single Mechanism (CBS)")
    print("="*60)

    # Using keyword arguments
    task1 = model.SendingTask('CBS_Task', 10, 20, 1, 0b0001, idleslope=5000000)

    print(f"Task name: {task1.name}")
    print(f"BCET: {task1.bcet}, WCET: {task1.wcet}")
    print(f"Scheduling flags: {bin(task1.scheduling_flags)}")
    print(f"Uses CBS: {task1.uses_cbs()}")
    print(f"Idle slope: {task1.idleslope}")
    print(f"Validation: {task1.validate_parameters()}")


def test_multiple_mechanisms():
    """Test SendingTask with multiple TSN mechanisms"""
    print("\n" + "="*60)
    print("Test 2: Multiple Mechanisms (CBS + TAS + CQF)")
    print("="*60)

    # Using keyword arguments - multiple mechanisms combined
    task2 = model.SendingTask('Multi_Task',
                             bcet=15, wcet=30, scheduling_parameter=2,
                             scheduling_flags=0b0111,  # CBS(0)+TAS(1)+CQF(2)
                             idleslope=10000000,
                             tas_cycle_time=1000000,
                             tas_window_time=500000,
                             cqf_cycle_time=250000)

    print(f"Task name: {task2.name}")
    print(f"BCET: {task2.bcet}, WCET: {task2.wcet}")
    print(f"Scheduling flags: {bin(task2.scheduling_flags)}")
    print(f"Uses CBS: {task2.uses_cbs()}, idleslope: {task2.idleslope}")
    print(f"Uses TAS: {task2.uses_tas()}, cycle: {task2.tas_cycle_time}, window: {task2.tas_window_time}")
    print(f"Uses CQF: {task2.uses_cqf()}, cycle: {task2.cqf_cycle_time}")
    print(f"Validation: {task2.validate_parameters()}")


def test_all_mechanisms():
    """Test SendingTask with all TSN mechanisms"""
    print("\n" + "="*60)
    print("Test 3: All Mechanisms (CBS + TAS + CQF + Preempt + ATS)")
    print("="*60)

    # Using keyword arguments - all mechanisms
    task3 = model.SendingTask('All_Mech_Task',
                             20, 40, 3,
                             0b11111,  # CBS+TAS+CQF+Preempt+ATS
                             idleslope=12000000,
                             tas_cycle_time=2000000,
                             tas_window_time=1000000,
                             cqf_cycle_time=800000,
                             is_express=False,
                             ats_cir=3000000,
                             ats_cbs=15000,
                             ats_eir=800000,
                             ats_ebs=8000,
                             ats_scheduler_group=2)

    print(f"Task name: {task3.name}")
    print(f"BCET: {task3.bcet}, WCET: {task3.wcet}")
    print(f"Scheduling flags: {bin(task3.scheduling_flags)}")
    print(f"Uses CBS: {task3.uses_cbs()}, idleslope: {task3.idleslope}")
    print(f"Uses TAS: {task3.uses_tas()}, cycle: {task3.tas_cycle_time}, window: {task3.tas_window_time}")
    print(f"Uses CQF: {task3.uses_cqf()}, cycle: {task3.cqf_cycle_time}")
    print(f"Uses Preemption: {task3.uses_preemption()}, is_express: {task3.is_express}")
    print(f"Uses ATS: {task3.uses_ats()}")
    print(f"  ATS params - CIR: {task3.ats_cir}, CBS: {task3.ats_cbs}")
    print(f"             EIR: {task3.ats_eir}, EBS: {task3.ats_ebs}")
    print(f"             Scheduler group: {task3.ats_scheduler_group}")
    print(f"Validation: {task3.validate_parameters()}")


def test_key_value_pairs():
    """Test SendingTask using key-value pairs in positional arguments"""
    print("\n" + "="*60)
    print("Test 4: Key-Value Pairs in Positional Arguments")
    print("="*60)

    # Using key-value pairs - order doesn't matter
    task4 = model.SendingTask('KV_Pair_Task', 25, 50, 4, 0b0011,
                             'tas_window_time', 750000,      # TAS parameter
                             'idleslope', 15000000,          # CBS parameter
                             'tas_cycle_time', 1500000)      # TAS parameter

    print(f"Task name: {task4.name}")
    print(f"Uses CBS: {task4.uses_cbs()}, idleslope: {task4.idleslope}")
    print(f"Uses TAS: {task4.uses_tas()}, cycle: {task4.tas_cycle_time}, window: {task4.tas_window_time}")
    print(f"Validation: {task4.validate_parameters()}")


def test_dictionary():
    """Test SendingTask using dictionary for TSN parameters"""
    print("\n" + "="*60)
    print("Test 5: Dictionary for TSN Parameters")
    print("="*60)

    # Using dictionary
    tsn_params = {
        'idleslope': 8000000,
        'tas_cycle_time': 1200000,
        'tas_window_time': 600000,
        'cqf_cycle_time': 600000
    }

    task5 = model.SendingTask('Dict_Task', 18, 35, 3, 0b0111, tsn_params)

    print(f"Task name: {task5.name}")
    print(f"Uses CBS: {task5.uses_cbs()}, idleslope: {task5.idleslope}")
    print(f"Uses TAS: {task5.uses_tas()}, cycle: {task5.tas_cycle_time}, window: {task5.tas_window_time}")
    print(f"Uses CQF: {task5.uses_cqf()}, cycle: {task5.cqf_cycle_time}")
    print(f"Validation: {task5.validate_parameters()}")


def test_with_system():
    """Test SendingTask in a complete pycpa system"""
    print("\n" + "="*60)
    print("Test 6: SendingTask in Complete System")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r1 = s.bind_resource(model.Resource("R1", schedulers.SPPScheduler()))

    # Create SendingTask with TAS mechanism
    task6 = model.SendingTask('TAS_Task', wcet=8, bcet=4,
                             scheduling_parameter=1,
                             scheduling_flags=0b0010,
                             tas_cycle_time=1000000,
                             tas_window_time=500000)
    r1.bind_task(task6)

    # Create regular Task for comparison
    task7 = model.Task('Regular_Task', wcet=6, bcet=3,
                      scheduling_parameter=2)
    r1.bind_task(task7)

    # Connect tasks: task6 -> task7
    task6.link_dependent_task(task7)

    # Set event model only for source task (task6)
    # task7's in_event_model will be derived from task6's output event model
    task6.in_event_model = model.PJdEventModel(P=40, J=80)

    # Perform analysis
    print("Performing analysis...")
    results = analysis.analyze_system(s)

    print("\nResults:")
    for r in sorted(s.resources, key=str):
        for t in sorted(r.tasks, key=str):
            print(f"  {t.name}: wcrt={results[t].wcrt}")
            if isinstance(t, model.SendingTask):
                print(f"    TSN flags: {bin(t.scheduling_flags)}")
                if t.uses_tas():
                    print(f"    TAS - cycle: {t.tas_cycle_time}, window: {t.tas_window_time}")


def test_validations():
    """Test parameter validation - error cases"""
    print("\n" + "="*60)
    print("Test 7: Parameter Validation (Error Cases)")
    print("="*60)

    # Missing required parameter for CBS
    try:
        task_error = model.SendingTask('Error_Task', 10, 20, 1, 0b0001)
        task_error.validate_parameters()
        print("ERROR: Should have raised ValueError!")
    except ValueError as e:
        print(f"Expected error caught: {e}")

    # Missing required parameters for TAS
    try:
        task_error = model.SendingTask('Error_Task', 10, 20, 1, 0b0010,
                                      tas_cycle_time=1000000)
        task_error.validate_parameters()
        print("ERROR: Should have raised ValueError!")
    except ValueError as e:
        print(f"Expected error caught (TAS missing window): {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    test_single_mechanism()
    test_multiple_mechanisms()
    test_all_mechanisms()
    test_key_value_pairs()
    test_dictionary()
    test_with_system()
    test_validations()

    print("\n" + "="*60)
    print("All tests completed!")
    print("="*60)
