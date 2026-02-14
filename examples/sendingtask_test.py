"""
Test TSN_SendingTask class for TSN mechanisms

This example demonstrates the usage of TSN_SendingTask with various
Time-Sensitive Networking (TSN) scheduling mechanisms.

TSN_SendingTask Overview:
=========================
TSN_SendingTask extends the Task model to support network-specific scheduling
mechanisms for real-time Ethernet and Time-Sensitive Networking (TSN) protocols.
It supports the following scheduling mechanisms:
- CBS (Credit-Based Shaper): Uses idleslope parameter for traffic shaping
- TAS (Time-Aware Shaper): Uses tas_cycle_time and tas_window_time for gated transmission
- CQF (Cyclic Queuing and Forwarding): Uses cqf_cycle_time for queue rotation
- ATS (Asynchronous Traffic Shaping): Uses dual-speed dual-bucket leaky bucket parameters
- Preemption: Supports frame preemption with is_express flag

Mechanism Compatibility Constraints:
===================================
- Each mechanism (CBS, TAS, CQF, ATS, Preemption) can be used independently
- When combining multiple mechanisms, Preemption is required:
  * TAS + Preemption: default is_express=True (express/fast traffic)
  * CQF + Preemption: is_express not constrained
  * CBS + Preemption: is_express not constrained
  * ATS + Preemption: is_express not constrained
- Maximum of 2 mechanisms can be combined (excluding Preemption)

Test Cases Summary:
===================

Test 1: Single Mechanism (CBS)
-------------------------------
Tests TSN_SendingTask with only CBS mechanism enabled (scheduling_flags=0b0001).
Validates that:
- CBS scheduling is correctly recognized (uses_cbs() returns True)
- Required CBS parameter (idleslope) is properly set
- Parameter validation passes for single mechanism usage

Test 2: Single Mechanism (CQF)
-------------------------------
Tests TSN_SendingTask with only CQF mechanism enabled (scheduling_flags=0b0100).
Validates that:
- CQF scheduling is correctly recognized (uses_cqf() returns True)
- Required CQF parameter (cqf_cycle_time) is properly set
- Parameter validation passes for single mechanism usage

Test 3: TAS + Preemption (defaults to express)
-----------------------------------------------
Tests TSN_SendingTask with TAS and Preemption enabled (scheduling_flags=0b1010).
Validates that:
- Both TAS and Preemption are correctly recognized
- is_express defaults to True when TAS + Preemption is used
- Required TAS parameters (tas_cycle_time, tas_window_time) are properly set

Test 4: CQF + Preemption with key-value pairs
----------------------------------------------
Tests TSN_SendingTask with CQF and Preemption using key-value pair syntax
for passing TSN parameters in positional arguments.
Validates that:
- Key-value pair parameter passing works correctly
- CQF + Preemption combination is valid
- is_express constraint is not applied for CQF + Preemption combo

Test 5: CBS + Preemption
--------------------------
Tests TSN_SendingTask with CBS and Preemption enabled (scheduling_flags=0b1001).
Validates that:
- Both CBS and Preemption are correctly recognized
- Required CBS parameter (idleslope) is properly set
- is_express can be explicitly set to False for preemptable frames

Test 6: TSN_SendingTask in Complete System
-------------------------------------------
Tests TSN_SendingTask integrated in a complete pycpa system with analysis.
Validates that:
- TSN_SendingTask can coexist with regular Task objects on the same resource
- Task linking works correctly between TSN_SendingTask and regular Task
- System analysis completes successfully
- Results can be queried for both task types
- Task type identification works using either isinstance() or is_tsn_sending_task flag

Test 7: Parameter Validation (Error Cases)
-------------------------------------------
Tests error handling for invalid parameter configurations with 5 sub-cases:

7.1: Missing CBS parameter
    - CBS flag is set but idleslope is not provided
    - Expected: ValueError raised

7.2: Missing TAS parameters
    - TAS flag is set but tas_window_time is not provided (only tas_cycle_time)
    - Expected: ValueError raised

7.3: CBS + TAS without Preemption (should fail)
    - Multiple mechanisms (CBS and TAS) combined without Preemption
    - Expected: ValueError raised - Preemption is required when combining mechanisms

7.4: CQF alone (should pass)
    - Only CQF mechanism is enabled (single mechanism is always allowed)
    - Expected: No error - validation passes

7.5: CQF + CBS without Preemption (should fail)
    - Multiple mechanisms (CQF and CBS) combined without Preemption
    - Expected: ValueError raised - Preemption is required when combining mechanisms
"""

import logging
from pycpa import model
from pycpa import analysis
from pycpa import schedulers
from pycpa import options

def test_single_mechanism():
    """Test TSN_SendingTask with single TSN mechanism"""
    print("\n" + "="*60)
    print("Test 1: Single Mechanism (CBS)")
    print("="*60)

    # Using keyword arguments - single mechanism is allowed
    task1 = model.TSN_SendingTask('CBS_Task', 10, 20, 1, 0b0001, idleslope=5000000)

    print(f"Task name: {task1.name}")
    print(f"BCET: {task1.bcet}, WCET: {task1.wcet}")
    print(f"Scheduling flags: {bin(task1.scheduling_flags)}")
    print(f"Uses CBS: {task1.uses_cbs()}")
    print(f"Idle slope: {task1.idleslope}")
    print(f"Validation: {task1.validate_parameters()}")


def test_cqf_single():
    """Test TSN_SendingTask with single CQF mechanism"""
    print("\n" + "="*60)
    print("Test 2: Single Mechanism (CQF)")
    print("="*60)

    # Single CQF mechanism is allowed
    task2 = model.TSN_SendingTask('CQF_Task',
                             bcet=15, wcet=30, scheduling_parameter=2,
                             scheduling_flags=0b0100,  # CQF only
                             cqf_cycle_time=250000)

    print(f"Task name: {task2.name}")
    print(f"BCET: {task2.bcet}, WCET: {task2.wcet}")
    print(f"Scheduling flags: {bin(task2.scheduling_flags)}")
    print(f"Uses CQF: {task2.uses_cqf()}, cycle: {task2.cqf_cycle_time}")
    print(f"Validation: {task2.validate_parameters()}")


def test_tas_preemption():
    """Test TAS + Preemption combination (defaults to express traffic)"""
    print("\n" + "="*60)
    print("Test 3: TAS + Preemption (defaults to express)")
    print("="*60)

    # TAS + Preemption - is_express defaults to True
    task3 = model.TSN_SendingTask('TAS_Prep_Task',
                             20, 40, 3,
                             0b1010,  # TAS + Preemption
                             tas_cycle_time=2000000,
                             tas_window_time=1000000)
    # Note: is_express not set, will default to True after validation

    print(f"Task name: {task3.name}")
    print(f"Scheduling flags: {bin(task3.scheduling_flags)}")
    print(f"Uses TAS: {task3.uses_tas()}, cycle: {task3.tas_cycle_time}, window: {task3.tas_window_time}")
    print(f"Uses Preemption: {task3.uses_preemption()}, is_express: {task3.is_express} (should be True after validation)")
    task3.validate_parameters()
    print(f"is_express after validation: {task3.is_express}")


def test_key_value_pairs():
    """Test TSN_SendingTask using key-value pairs in positional arguments"""
    print("\n" + "="*60)
    print("Test 4: CQF + Preemption with key-value pairs")
    print("="*60)

    # CQF + Preemption - is_express can be anything
    task4 = model.TSN_SendingTask('KV_Pair_Task', 25, 50, 4, 0b1100,
                             'cqf_cycle_time', 750000)      # CQF parameter
    # Note: Preemption flag is set (bit 3), CQF flag is set (bit 2)
    # is_express not set, no constraint for CQF+Preemption combo

    print(f"Task name: {task4.name}")
    print(f"Scheduling flags: {bin(task4.scheduling_flags)}")
    print(f"Uses CQF: {task4.uses_cqf()}, cycle: {task4.cqf_cycle_time}")
    print(f"Uses Preemption: {task4.uses_preemption()}, is_express: {task4.is_express}")
    print(f"Validation: {task4.validate_parameters()}")


def test_cbs_preemption():
    """Test CBS + Preemption combination"""
    print("\n" + "="*60)
    print("Test 5: CBS + Preemption")
    print("="*60)

    # CBS + Preemption - is_express can be anything
    task5 = model.TSN_SendingTask('CBS_Prep_Task', 18, 35, 3, 0b1001,
                                  idleslope=8000000,
                                  is_express=False)  # Preemptable frame

    print(f"Task name: {task5.name}")
    print(f"Scheduling flags: {bin(task5.scheduling_flags)}")
    print(f"Uses CBS: {task5.uses_cbs()}, idleslope: {task5.idleslope}")
    print(f"Uses Preemption: {task5.uses_preemption()}, is_express: {task5.is_express}")
    print(f"Validation: {task5.validate_parameters()}")


def test_with_system():
    """Test TSN_SendingTask in a complete pycpa system"""
    print("\n" + "="*60)
    print("Test 6: TSN_SendingTask in Complete System")
    print("="*60)

    options.init_pycpa()
    s = model.System()
    r1 = s.bind_resource(model.Resource("R1", schedulers.SPPScheduler()))

    # Create TSN_SendingTask with single TAS mechanism
    task6 = model.TSN_SendingTask('TAS_Task', wcet=8, bcet=4,
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
            # Method 1: Using isinstance()
            if isinstance(t, model.TSN_SendingTask):
                print(f"    TSN flags: {bin(t.scheduling_flags)}")
                if t.uses_tas():
                    print(f"    TAS - cycle: {t.tas_cycle_time}, window: {t.tas_window_time}")

    # Alternative: Using the is_tsn_sending_task flag
    print("\nAlternative task identification using class flag:")
    for r in sorted(s.resources, key=str):
        for t in sorted(r.tasks, key=str):
            if getattr(t, 'is_tsn_sending_task', False):
                print(f"  {t.name} is a TSN_SendingTask")
                print(f"    TSN flags: {bin(t.scheduling_flags)}")
            else:
                print(f"  {t.name} is a regular Task")


def test_validations():
    """Test parameter validation - error cases"""
    print("\n" + "="*60)
    print("Test 7: Parameter Validation (Error Cases)")
    print("="*60)

    # 1. Missing required parameter for CBS
    print("\n7.1: Missing CBS parameter")
    try:
        task_error = model.TSN_SendingTask('Error_Task', 10, 20, 1, 0b0001)
        task_error.validate_parameters()
        print("ERROR: Should have raised ValueError!")
    except ValueError as e:
        print(f"Expected error caught: {e}")

    # 2. Missing required parameters for TAS
    print("\n7.2: Missing TAS parameters")
    try:
        task_error = model.TSN_SendingTask('Error_Task', 10, 20, 1, 0b0010,
                                           tas_cycle_time=1000000)
        task_error.validate_parameters()
        print("ERROR: Should have raised ValueError!")
    except ValueError as e:
        print(f"Expected error caught (TAS missing window): {e}")

    # 3. Multiple mechanisms without Preemption - CBS + TAS
    print("\n7.3: CBS + TAS without Preemption (should fail)")
    try:
        task_error = model.TSN_SendingTask('Error_Task', 10, 20, 1, 0b0011,
                                           idleslope=5000000,
                                           tas_cycle_time=1000000,
                                           tas_window_time=500000)
        task_error.validate_parameters()
        print("ERROR: Should have raised ValueError!")
    except ValueError as e:
        print(f"Expected error caught: {e}")

    # 4. CQF alone is allowed
    print("\n7.4: CQF alone (should pass)")
    try:
        task_ok = model.TSN_SendingTask('OK_Task', 10, 20, 1, 0b0100,
                                        cqf_cycle_time=500000)
        result = task_ok.validate_parameters()
        print(f"No error - CQF alone is allowed: {result}")
    except ValueError as e:
        print(f"Unexpected error: {e}")

    # 5. CQF + CBS without Preemption - should fail
    print("\n7.5: CQF + CBS without Preemption (should fail)")
    try:
        task_error = model.TSN_SendingTask('Error_Task', 10, 20, 1, 0b0101,
                                           idleslope=5000000,
                                           cqf_cycle_time=300000)
        task_error.validate_parameters()
        print("ERROR: Should have raised ValueError!")
    except ValueError as e:
        print(f"Expected error caught: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    test_single_mechanism()
    test_cqf_single()
    test_tas_preemption()
    test_key_value_pairs()
    test_cbs_preemption()
    test_with_system()
    test_validations()

    print("\n" + "="*60)
    print("All tests completed!")
    print("="*60)
