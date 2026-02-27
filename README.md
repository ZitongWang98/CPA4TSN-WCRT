# TSN-CPA-WCRT

A unified WCRT (Worst-Case Response Time) analysis framework for TSN (Time-Sensitive Networking) scheduling mechanisms, built on top of **pyCPA (Compositional Performance Analysis)**. This repository aims to support both individual TSN schedulers and their hybrid/combined usage scenarios.

---

## Features

- WCRT analysis for major TSN scheduling mechanisms
- Support for hybrid scheduling combinations
- Built on pyCPA, easy to extend with new models

---

## TSN Functionality Overview

This project implements the following TSN (Time-Sensitive Networking) related functionality:

### 1. TSN Schedulers

| Scheduler | Description |
|-----------|-------------|
| **TASScheduler** | Time-Aware Shaper scheduler based on IEEE 802.1Qbv |
| **TASSchedulerE2E** | E2E-optimized TAS scheduler supporting end-to-end latency correction for multi-hop scenarios |

### 2. TSN Resource Model

**TSN_Resource** is an extended `Resource` class supporting port-level TSN parameter configuration:

- **priority_mechanism_map**: Priority-to-scheduling-mechanism mapping
- **TAS parameters**: `tas_cycle_time`, `tas_window_time`, `tas_window_time_by_priority`, `guard_band`, `guard_band_by_priority`
- **CBS parameters**: `idleslope`, `idleslope_by_priority`
- **CQF parameters**: `cqf_cycle_time`, `cqf_cycle_time_by_pair`
- **Frame Preemption**: `is_express`, `is_express_by_priority`
- **ATS parameters**: `ats_cir`, `ats_cbs`, `ats_eir`, `ats_ebs`, `ats_scheduler_group`

### 3. End-to-End Analysis

- **`path_analysis.end_to_end_latency()`**: Supports TAS E2E correction
- **`path.tas_aligned`**: Marks TAS time window alignment status along the path
- **`TASSchedulerE2E`**: Automatically records `gate_closed_blocking` for E2E correction

### 4. Supported Mechanisms

| Mechanism | Status | Description |
|-----------|--------|-------------|
| TAS | Supported | Time-Aware Shaper (IEEE 802.1Qbv) |
| CBS | Partial | Credit-Based Shaper (IEEE 802.1Qav) |
| CQF | Partial | Cyclic Queuing and Forwarding (IEEE 802.1Qci) |
| ATS | Partial | Asynchronous Traffic Shaping (IEEE 802.1Qcr) |

---

## Dependencies

- Python 3.x
- pyCPA

---

## Quick Start

### Simple TAS Example

The following is a minimal example of using the TAS scheduler to analyze a single-hop TAS flow:

```python
from pycpa import model, analysis, schedulers, options

# Initialize pyCPA
options.init_pycpa()

# Create system
s = model.System()

# Create TSN resource using TASScheduler
# Priority 7 uses TAS, Priority 1 uses normal scheduling (None)
sw = s.bind_resource(model.TSN_Resource(
    "Switch1",
    schedulers.TASScheduler(),
    priority_mechanism_map={7: 'TAS', 1: None},
    tas_cycle_time=1000,                           # TAS cycle time (us)
    tas_window_time_by_priority={7: 100}          # TAS window time (us)
))

# Create TAS task (priority 7)
tas_task = model.Task('TAS_Task', bcet=12, wcet=12, scheduling_parameter=7)
sw.bind_task(tas_task)
tas_task.in_event_model = model.PJdEventModel(P=1000, J=0)

# Create normal task (priority 1)
normal_task = model.Task('Normal_Task', bcet=12, wcet=12, scheduling_parameter=1)
sw.bind_task(normal_task)

# Perform system analysis
results = analysis.analyze_system(s)

# Print results
print(f"TAS Task: WCRT={results[tas_task].wcrt} us")
print(f"Normal Task: WCRT={results[normal_task].wcrt} us")
```

---

## TSN Usage Examples

### Example File Specification

All TSN example files should follow the following modeling pattern:

```python
"""
[File description - including topology and parameter explanation]
"""

import logging
from pycpa import model, analysis, path_analysis, schedulers, options

# ========================================
# 1. Define common parameters
# ========================================
WCET = 12       # Worst/Best execution time (us)
PERIOD = 1000   # Task period (us)
CYCLE = 1000    # TAS cycle time (us)
WINDOW = 100    # TAS window time (us)

# ========================================
# 2. Analysis scenario function
# ========================================
def scenario_name():
    """
    [Scenario description]
    """
    # Initialize pyCPA options
    options.init_pycpa()

    # Create system
    s = model.System()

    # Create resource using TSN_Resource
    sw1 = s.bind_resource(model.TSN_Resource(
        "Switch1",
        schedulers.TASScheduler(),  # or TASSchedulerE2E()
        priority_mechanism_map={7: 'TAS', 1: None},
        tas_cycle_time=CYCLE,
        tas_window_time_by_priority={7: WINDOW},
        # Optional: guard_band=10, guard_band_by_priority={7: 10, 1: 5}
    ))

    # Create task
    task1 = model.Task('Task1', bcet=WCET, wcet=WCET, scheduling_parameter=7)
    sw1.bind_task(task1)
    task1.in_event_model = model.PJdEventModel(P=PERIOD, J=0)

    # For end-to-end analysis, create path
    if needs_path:
        s.bind_path(model.Path('Path1', [task1, ...]))

    # Set TAS alignment status for E2E correction (only works with TASSchedulerE2E)
    if needs_e2e_correction:
        # Use TASSchedulerE2E() instead of TASScheduler() for E2E correction
        task1.path.tas_aligned = True  # or False

    # Perform analysis
    results = analysis.analyze_system(s)

    # Print results
    for p in s.paths:
        lmin, lmax = path_analysis.end_to_end_latency(p, results, 1)
        print(f"Path '{p.name}': BCRT={lmin} us, WCRT={lmax} us")

# ========================================
# 3. Main function entry
# ========================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    scenario_name()
```

### TASScheduler Usage Example

**TASScheduler** is the basic Time-Aware Shaper scheduler, suitable for single-hop analysis:

**Note**: `TASScheduler` does **not** support E2E correction or the `tas_aligned` configuration. It always computes E2E latency as the simple sum of per-hop WCRT values. For E2E correction with `tas_aligned` support, use `TASSchedulerE2E` instead.

```python
from pycpa import model, analysis, schedulers, options

options.init_pycpa()
s = model.System()

# Create switch using TASScheduler
sw = s.bind_resource(model.TSN_Resource(
    "Switch",
    schedulers.TASScheduler(),
    priority_mechanism_map={7: 'TAS', 1: None},
    tas_cycle_time=1000,
    tas_window_time_by_priority={7: 100}
))

# Create TAS task
tas_task = model.Task('TAS_Task', bcet=12, wcet=12, scheduling_parameter=7)
sw.bind_task(tas_task)
tas_task.in_event_model = model.PJdEventModel(P=1000, J=0)

# Analyze
results = analysis.analyze_system(s)
print(f"WCRT={results[tas_task].wcrt} us")
```

### TASSchedulerE2E Usage Example

**TASSchedulerE2E** is the E2E-optimized TAS scheduler with the following features:

1. **Multi-hop E2E latency correction**: Automatically applies E2E correction when `path.tas_aligned` is set. This feature is **NOT** available in `TASScheduler`.
2. **Guard Band configuration**: Supports global or per-priority guard band configuration

**Important**: If you need E2E correction for multi-hop paths, you **must** use `TASSchedulerE2E()`, not `TASScheduler()`. The `path.tas_aligned` attribute has no effect when using `TASScheduler`.

#### Example 1: E2E Analysis for Multi-hop Path (Aligned Mode)

```python
from pycpa import model, analysis, path_analysis, schedulers, options

options.init_pycpa()
s = model.System()

# Create two switches using TASSchedulerE2E
for i in range(1, 3):
    sw = s.bind_resource(model.TSN_Resource(
        f"Switch{i}",
        schedulers.TASSchedulerE2E(),
        priority_mechanism_map={7: 'TAS'},
        tas_cycle_time=1000,
        tas_window_time_by_priority={7: 100}
    ))

# Create two-hop flow
task_h1 = model.Task('Flow_h1', bcet=12, wcet=12, scheduling_parameter=7)
s.resources[0].bind_task(task_h1)
task_h1.in_event_model = model.PJdEventModel(P=1000, J=0)

task_h2 = model.Task('Flow_h2', bcet=12, wcet=12, scheduling_parameter=7)
s.resources[1].bind_task(task_h2)

# Link tasks
task_h1.link_dependent_task(task_h2)

# Create path and set TAS alignment
s.bind_path(model.Path('Flow_Path', [task_h1, task_h2]))
task_h1.path.tas_aligned = True  # First hop has no gate-closed blocking

# Analyze
results = analysis.analyze_system(s)
lmin, lmax = path_analysis.end_to_end_latency(task_h1.path, results, 1)
print(f"E2E (corrected): WCRT={lmax} us")
```

#### Example 2: Guard Band Configuration

```python
# Method 1: Global guard_band (all priorities)
sw_global = s.bind_resource(model.TSN_Resource(
    "Switch1",
    schedulers.TASSchedulerE2E(),
    priority_mechanism_map={7: 'TAS', 1: None},
    tas_cycle_time=1000,
    tas_window_time_by_priority={7: 100},
    guard_band=10  # Global guard_band = 10 us
))

# Method 2: Per-priority guard_band
sw_per_prio = s.bind_resource(model.TSN_Resource(
    "Switch2",
    schedulers.TASSchedulerE2E(),
    priority_mechanism_map={7: 'TAS', 1: None},
    tas_cycle_time=1000,
    tas_window_time_by_priority={7: 100},
    guard_band_by_priority={7: 10, 1: 5}  # Prio 7: 10us, Prio 1: 5us
))

# Method 3: No guard_band set (use default behavior)
# TAS flow: guard_band = task.wcet
# NST flow: guard_band is computed as max(wcet of lower-priority flows)
sw_default = s.bind_resource(model.TSN_Resource(
    "Switch3",
    schedulers.TASSchedulerE2E(),
    priority_mechanism_map={7: 'TAS', 1: None},
    tas_cycle_time=1000,
    tas_window_time_by_priority={7: 100}
))
```

---

## TSN Configuration Parameters

### TSN_Resource Constructor Parameters

#### Priority-Mechanism Mapping

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `priority_mechanism_map` | dict | No | Priority-to-scheduling-mechanism mapping |

`priority_mechanism_map` format:
- Key: Priority (integer) or priority pair (tuple for CQF)
- Value: Mechanism name string (`'TAS'`, `'CQF'`, `'CBS'`, `'ATS'`, or `None`)

```python
priority_mechanism_map={
    7: 'TAS',           # Priority 7 uses TAS
    6: 'TAS',           # Priority 6 uses TAS
    (5, 4): 'CQF',      # Priorities 5 and 4 form a CQF pair
    1: 'CBS',           # Priority 1 uses CBS
    0: None,            # Priority 0 has no special mechanism
}
```

#### TAS (Time-Aware Shaper) Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tas_cycle_time` | int/float | Yes (when using TAS) | TAS Gate Control List (GCL) cycle time in microseconds |
| `tas_window_time` | int/float | No | Default gate open window duration |
| `tas_window_time_by_priority` | dict | Yes (when using TAS) | Per-priority TAS window time mapping, e.g., `{7: 100, 6: 200}` |
| `guard_band` | int/float | No | Global guard band duration for TASSchedulerE2E |
| `guard_band_by_priority` | dict | No | Per-priority guard band mapping, e.g., `{7: 10, 5: 8}` |

**Guard Band Meaning**: The time reserved to prevent a frame from transmitting after its gate closes due to link propagation delay. When a gate closes, it ensures no frame still being transmitted is left incomplete.

#### CBS (Credit-Based Shaper) Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `idleslope` | int/float | No | Default idleSlope parameter in bits per second |
| `idleslope_by_priority` | dict | Yes (when using CBS) | Per-priority idleSlope mapping, e.g., `{1: 5000000}` |

#### CQF (Cyclic Queuing and Forwarding) Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `cqf_cycle_time` | int/float | No | Default CQF queue cycle time |
| `cqf_cycle_time_by_pair` | dict | Yes (when using CQF) | Per-CQF-pair cycle time mapping, e.g., `{(5, 4): 500}` |

#### Frame Preemption Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `is_express` | bool | No | Default frame preemption classification on the port |
| `is_express_by_priority` | dict | No | Per-priority preemption classification, e.g., `{7: True, 1: False}` |

#### ATS (Asynchronous Traffic Shaping) Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `ats_cir` | int/float | No | Default Committed Information Rate |
| `ats_cbs` | int/float | No | Default Committed Burst Size |
| `ats_eir` | int/float | No | Default Excess Information Rate |
| `ats_ebs` | int/float | No | Default Excess Burst Size |
| `ats_scheduler_group` | int | No | Default scheduler group |
| `ats_params_by_priority` | dict | Yes (when using ATS) | Per-priority ATS parameter mapping |

### Path Attributes

| Attribute | Type | Condition | Description |
|-----------|------|-----------|-------------|
| `tas_aligned` | bool | TASSchedulerE2E multi-hop analysis | Whether TAS time windows are aligned. True means first hop has no gate-closed blocking, False means first hop has 1 gate-closed blocking |

### TASSchedulerE2E Task Results Attributes

After analysis with TASSchedulerE2E, task results include the following additional attributes:

| Attribute | Type | Description |
|-----------|------|-------------|
| `gate_closed_duration` | int/float | Duration of one complete gate-closed period |
| `non_gate_closed` | int/float | Portion of WCRT excluding gate-closed blocking |

---

## E2E Correction Explanation

**Note**: E2E correction is only supported when using `TASSchedulerE2E`. When using `TASScheduler`, E2E latency is always computed as the simple sum of per-hop WCRT values, regardless of the `path.tas_aligned` setting.

When using `TASSchedulerE2E` and `path.tas_aligned` is set, end-to-end latency calculation applies the correction formula:

```
E2E_corrected = sum(non_gate_closed) + K_actual * G_duration
```

Where:
- `non_gate_closed`: Portion of WCRT excluding gate-closed blocking for each hop
- `G_duration`: Gate-closed period duration = `tas_cycle - tas_window + guard_band`
- `K_actual = K_base + floor(sum_non_gate_closed / tas_window)`
  - `K_base = 0` when `tas_aligned = True`
  - `K_base = 1` when `tas_aligned = False`

---

## Complete Example

### Two-hop TAS Flow Analysis (Aligned Mode)

```python
from pycpa import model, analysis, path_analysis, schedulers, options

# Parameter configuration
WCET = 12      # 1518 bytes @ 1Gbps
PERIOD = 1000  # us
CYCLE = 1000   # TAS cycle time (us)
WINDOW = 100   # TAS window time (us)

def two_hop_tas_aligned():
    """Two-hop TAS flow analysis using aligned mode."""
    options.init_pycpa()
    s = model.System()

    # Create two switches
    for i in range(1, 3):
        s.bind_resource(model.TSN_Resource(
            f"Switch{i}",
            schedulers.TASSchedulerE2E(),
            priority_mechanism_map={7: 'TAS'},
            tas_cycle_time=CYCLE,
            tas_window_time_by_priority={7: WINDOW}
        ))

    # Create two-hop tasks
    task_h1 = model.Task('Flow_h1', bcet=WCET, wcet=WCET, scheduling_parameter=7)
    s.resources[0].bind_task(task_h1)
    task_h1.in_event_model = model.PJdEventModel(P=PERIOD, J=0)

    task_h2 = model.Task('Flow_h2', bcet=WCET, wcet=WCET, scheduling_parameter=7)
    s.resources[1].bind_task(task_h2)

    # Link tasks and create path
    task_h1.link_dependent_task(task_h2)
    s.bind_path(model.Path('Flow_Path', [task_h1, task_h2]))

    # Set TAS alignment
    task_h1.path.tas_aligned = True

    # Analyze and print
    results = analysis.analyze_system(s)
    print(f"Hop1 WCRT: {results[task_h1].wcrt} us")
    print(f"Hop2 WCRT: {results[task_h2].wcrt} us")

    lmin, lmax = path_analysis.end_to_end_latency(task_h1.path, results, 1)
    print(f"E2E (corrected): BCRT={lmin} us, WCRT={lmax} us")

if __name__ == "__main__":
    two_hop_tas_aligned()
```

---

## References

- **TASScheduler**:
  THIELE D, ERNST R, DIEMER J. Formal worst-case timing analysis of Ethernet TSN's time-aware and peristaltic shapers[C]//2015 IEEE Vehicular Networking Conference (VNC). Kyoto, Japan: IEEE, 2015: 251-258.

- **TASSchedulerE2E** (E2E correction):
  Luo F, Zhu L, Wang Z, et al. Schedulability analysis of time aware shaper with preemption supported in time-sensitive networks[J]. Computer Networks, 2025, 269: 111424.

---

## Contributing

Issues and pull requests are welcome.
