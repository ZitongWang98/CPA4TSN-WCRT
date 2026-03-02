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

### 4. Switch Forwarding Delay

**ForwardingTask** models the processing/transmission delay when a packet traverses a switch. It is inserted into the analysis path between hops and participates in both E2E latency calculation and event model propagation.

- Supports symmetric delay (`bcet = wcet`) or asymmetric delay (`bcet < wcet`)
- When `bcet != wcet`, the response time jitter (`wcet - bcet`) propagates into the downstream task's input event model, just like a regular scheduler
- No gate-closed blocking or same-priority interference
- Compatible with TAS E2E correction (`tas_aligned`)

Key functions:
- **`model.add_forwarding_delay_to_path(path, switch_resource, delay_us)`**: Add a single forwarding delay task for a specific switch
- **`model.add_forwarding_delays_for_path(path)`**: Automatically add forwarding delays for all switches on a path
- **`model.auto_add_forwarding_delays(system)`**: Automatically add forwarding delays for all paths in a system

`delay_us` can be a single number (symmetric) or a `(bcet, wcet)` tuple (asymmetric). `TSN_Resource` also accepts a `forwarding_delay` constructor parameter in either format.

### 5. Supported Mechanisms

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
# NST flow: guard_band is computed as max(max wcet of flows)
sw_default = s.bind_resource(model.TSN_Resource(
    "Switch3",
    schedulers.TASSchedulerE2E(),
    priority_mechanism_map={7: 'TAS', 1: None},
    tas_cycle_time=1000,
    tas_window_time_by_priority={7: 100}
))
```

#### Example 3: Forwarding Delay

```python
from pycpa import model, analysis, path_analysis, schedulers, options

options.init_pycpa()
s = model.System()

# Method 1: Symmetric delay (bcet = wcet = 5 us)
sw1 = s.bind_resource(model.TSN_Resource(
    "Switch1", schedulers.TASSchedulerE2E(),
    priority_mechanism_map={7: 'TAS'},
    tas_cycle_time=1000,
    tas_window_time_by_priority={7: 100},
    forwarding_delay=5
))

# Method 2: Asymmetric delay (bcet=3, wcet=7)
sw2 = s.bind_resource(model.TSN_Resource(
    "Switch2", schedulers.TASSchedulerE2E(),
    priority_mechanism_map={7: 'TAS'},
    tas_cycle_time=1000,
    tas_window_time_by_priority={7: 100},
    forwarding_delay=(3, 7)
))

# Create two-hop flow
task_h1 = model.Task('Flow_h1', bcet=12, wcet=12, scheduling_parameter=7)
sw1.bind_task(task_h1)
task_h1.in_event_model = model.PJdEventModel(P=1000, J=0)

task_h2 = model.Task('Flow_h2', bcet=12, wcet=12, scheduling_parameter=7)
sw2.bind_task(task_h2)
task_h1.link_dependent_task(task_h2)

# Create path and add forwarding delays automatically
path = model.Path('Flow_Path', [task_h1, task_h2])
s.bind_path(path)
model.add_forwarding_delays_for_path(path)
# Path is now: Flow_h1 -> FD_Switch1 -> Flow_h2 -> FD_Switch2

# Analyze
results = analysis.analyze_system(s)
lmin, lmax = path_analysis.end_to_end_latency(path, results, 1)
print(f"E2E: min={lmin} us, max={lmax} us")
```

#### Example 4: Comprehensive Multi-Hop Analysis

This example combines all TASSchedulerE2E features: TAS and non-TAS mixed priorities, per-priority and global guard band, asymmetric and symmetric forwarding delay, E2E correction with `tas_aligned`, and multi-flow interference.

```python
from pycpa import model, analysis, path_analysis, schedulers, options

options.init_pycpa()
s = model.System()

# Switch1: per-priority guard_band + asymmetric forwarding delay (bcet=3, wcet=7)
sw1 = s.bind_resource(model.TSN_Resource(
    "Switch1", schedulers.TASSchedulerE2E(),
    priority_mechanism_map={7: 'TAS', 1: None},   # TAS + non-TAS coexistence
    tas_cycle_time=1000,
    tas_window_time_by_priority={7: 100},
    guard_band_by_priority={7: 10, 1: 5},          # Per-priority guard band
    forwarding_delay=(3, 7)                         # Asymmetric forwarding delay
))

# Switch2: global guard_band + symmetric forwarding delay
sw2 = s.bind_resource(model.TSN_Resource(
    "Switch2", schedulers.TASSchedulerE2E(),
    priority_mechanism_map={7: 'TAS', 1: None},
    tas_cycle_time=1000,
    tas_window_time_by_priority={7: 100},
    guard_band=8,                                   # Global guard band
    forwarding_delay=5                              # Symmetric forwarding delay
))

# TAS flow (priority 7): two-hop, period 1000 us
tas_h1 = model.Task('TAS_h1', bcet=12, wcet=12, scheduling_parameter=7)
sw1.bind_task(tas_h1)
tas_h1.in_event_model = model.PJdEventModel(P=1000, J=0)

tas_h2 = model.Task('TAS_h2', bcet=12, wcet=12, scheduling_parameter=7)
sw2.bind_task(tas_h2)
tas_h1.link_dependent_task(tas_h2)

# Non-TAS flow (priority 1): two-hop, period 2000 us, coexists with TAS
nst_h1 = model.Task('NST_h1', bcet=50, wcet=50, scheduling_parameter=1)
sw1.bind_task(nst_h1)
nst_h1.in_event_model = model.PJdEventModel(P=2000, J=0)

nst_h2 = model.Task('NST_h2', bcet=50, wcet=50, scheduling_parameter=1)
sw2.bind_task(nst_h2)
nst_h1.link_dependent_task(nst_h2)

# TAS path with E2E correction (aligned mode)
tas_path = model.Path('TAS_Path', [tas_h1, tas_h2])
tas_path.tas_aligned = True    # Enable E2E correction, aligned mode
s.bind_path(tas_path)

# Non-TAS path (no E2E correction, tas_aligned not set)
nst_path = model.Path('NST_Path', [nst_h1, nst_h2])
s.bind_path(nst_path)

# Auto-add forwarding delays for all paths based on resource configuration
model.auto_add_forwarding_delays(s)
# TAS_Path: TAS_h1 -> FD_Switch1(3,7) -> TAS_h2 -> FD_Switch2(5,5)
# NST_Path: NST_h1 -> FD_Switch1(3,7) -> NST_h2 -> FD_Switch2(5,5)

# Analyze
results = analysis.analyze_system(s)

# Print TAS path results
print("TAS Path:", [t.name for t in tas_path.tasks])
for t in tas_path.tasks:
    if t in results:
        is_fd = model.ForwardingTask.is_forwarding_task(t)
        marker = " [FD]" if is_fd else ""
        print(f"  {t.name}{marker}: WCRT={results[t].wcrt} us, BCRT={results[t].bcrt} us")
lmin, lmax = path_analysis.end_to_end_latency(tas_path, results, 1)
print(f"  E2E (corrected, aligned): min={lmin} us, max={lmax} us")

# Print NST path results
print()
print("NST Path:", [t.name for t in nst_path.tasks])
for t in nst_path.tasks:
    if t in results:
        is_fd = model.ForwardingTask.is_forwarding_task(t)
        marker = " [FD]" if is_fd else ""
        print(f"  {t.name}{marker}: WCRT={results[t].wcrt} us, BCRT={results[t].bcrt} us")
lmin, lmax = path_analysis.end_to_end_latency(nst_path, results, 1)
print(f"  E2E: min={lmin} us, max={lmax} us")
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

#### Switch Forwarding Delay Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `forwarding_delay` | int/float or tuple | No | Switch forwarding delay in microseconds. Single value for symmetric delay (`bcet=wcet`), or `(bcet, wcet)` tuple for asymmetric delay |

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
E2E_corrected = sum(non_gate_closed) + K_actual * G_duration + sum(forwarding_delay_wcrt)
```

Where:
- `non_gate_closed`: Portion of WCRT excluding gate-closed blocking for each regular hop
- `G_duration`: Gate-closed period duration = `tas_cycle - tas_window + guard_band`
- `K_actual = K_base + floor(sum_non_gate_closed / tas_window)`
  - `K_base = 0` when `tas_aligned = True`
  - `K_base = 1` when `tas_aligned = False`
- `forwarding_delay_wcrt`: WCRT of each forwarding task on the path (added independently, not affected by gate-closed correction)

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

---

## TODO / Future Work

The following features are planned for future development:

1. **Implement WCRT calculation for individual TSN mechanisms**:
   - CQF (Cyclic Queuing and Forwarding)
   - ATS (Asynchronous Traffic Shaping)
   - CBS (Credit-Based Shaper)
   - Frame preemption

2. **Progressively improve WCRT calculation for hybrid mechanisms**:
   - Start with pairwise combinations
   - Extend support for multiple mechanism combinations
   - Eventually support full mechanism fusion scenarios

3. **Implement tighter WCRT calculation based on trajectory method**:
   - Integrate trajectory analysis for more precise WCRT bounds
   - Improve accuracy for multi-hop scenarios with aligned schedules

---

# TSN 功能概述

一个基于 **pyCPA (组合性能分析)** 的 TSN (时间敏感网络) 调度机制统一 WCRT (最坏情况响应时间) 分析框架。本仓库旨在支持单个 TSN 调度器及其混合/组合使用场景。

## 主要功能

- 主要 TSN 调度机制的 WCRT 分析
- 支持混合调度组合
- 基于 pyCPA，易于扩展新模型

## TSN 功能详细说明

本项目实现了以下 TSN (时间敏感网络) 相关功能：

### 1. TSN 调度器

| 调度器名称 | 描述 |
|-----------|------|
| **TASScheduler** | 时间感知整形器 (Time-Aware Shaper) 调度器，基于 IEEE 802.1Qbv 标准 |
| **TASSchedulerE2E** | E2E优化版TAS调度器，支持端到端延迟修正，适用于多跳场景 |

### 2. TSN 资源模型

**TSN_Resource** 是扩展的 `Resource` 类，支持端口级 TSN 参数配置：

- **priority_mechanism_map**: 优先级到调度机制的映射
- **TAS 参数**: `tas_cycle_time`, `tas_window_time`, `tas_window_time_by_priority`, `guard_band`, `guard_band_by_priority`
- **CBS 参数**: `idleslope`, `idleslope_by_priority`
- **CQF 参数**: `cqf_cycle_time`, `cqf_cycle_time_by_pair`
- **帧抢占参数**: `is_express`, `is_express_by_priority`
- **ATS 参数**: `ats_cir`, `ats_cbs`, `ats_eir`, `ats_ebs`, `ats_scheduler_group`

### 3. 端到端分析

- **`path_analysis.end_to_end_latency()`**: 支持 TAS E2E 修正
- **`path.tas_aligned`**: 标记路径的 TAS 时间窗对齐状态
- **`TASSchedulerE2E`**: 自动记录 `gate_closed_blocking` 信息用于 E2E 修正

### 4. 交换机转发延迟

**ForwardingTask** 用于建模报文经过交换机时的处理/传输延迟。它被插入到分析路径中各跳之间，同时参与 E2E 延迟计算和事件模型传播。

- 支持对称延迟（`bcet = wcet`）或非对称延迟（`bcet < wcet`）
- 当 `bcet != wcet` 时，响应时间抖动（`wcet - bcet`）会传播到下游任务的输入事件模型中，与经过普通调度器的行为一致
- 不受门控阻塞和同优先级干扰的影响
- 兼容 TAS E2E 修正（`tas_aligned`）

关键函数：
- **`model.add_forwarding_delay_to_path(path, switch_resource, delay_us)`**: 为指定交换机添加单个转发延迟任务
- **`model.add_forwarding_delays_for_path(path)`**: 自动为路径上所有交换机添加转发延迟
- **`model.auto_add_forwarding_delays(system)`**: 自动为系统中所有路径添加转发延迟

`delay_us` 可以是单个数值（对称）或 `(bcet, wcet)` 元组（非对称）。`TSN_Resource` 的构造参数 `forwarding_delay` 同样支持这两种格式。

### 5. 支持的分析机制

| 机制 | 状态 | 描述 |
|-----|------|------|
| TAS | 已支持 | 时间感知整形器 (IEEE 802.1Qbv) |
| CBS | 部分支持 | 基于信用的整形器 (IEEE 802.1Qav) |
| CQF | 部分支持 | 循环排队转发 (IEEE 802.1Qci) |
| ATS | 部分支持 | 异步流量整形 (IEEE 802.1Qcr) |

## 依赖项

- Python 3.x
- pyCPA

## 快速开始

### 简单的 TAS 示例

以下是一个最简单的 TAS 调度器使用示例，创建一个单跳的 TAS 流量分析：

```python
from pycpa import model, analysis, schedulers, options

# 初始化 pyCPA
options.init_pycpa()

# 创建系统
s = model.System()

# 创建 TSN 资源（使用 TASScheduler）
# 优先级 7 使用 TAS，优先级 1 使用普通调度（None）
sw = s.bind_resource(model.TSN_Resource(
    "Switch1",
    schedulers.TASScheduler(),
    priority_mechanism_map={7: 'TAS', 1: None},
    tas_cycle_time=1000,                           # TAS 周期时间 (us)
    tas_window_time_by_priority={7: 100}          # TAS 窗口时间 (us)
))

# 创建 TAS 任务（优先级 7）
tas_task = model.Task('TAS_Task', bcet=12, wcet=12, scheduling_parameter=7)
sw.bind_task(tas_task)
tas_task.in_event_model = model.PJdEventModel(P=1000, J=0)

# 创建普通任务（优先级 1）
normal_task = model.Task('Normal_Task', bcet=12, wcet=12, scheduling_parameter=1)
sw.bind_task(normal_task)

# 进行系统分析
results = analysis.analyze_system(s)

# 输出结果
print(f"TAS Task: WCRT={results[tas_task].wcrt} us")
print(f"Normal Task: WCRT={results[normal_task].wcrt} us")
```

## TSN 使用示例

### 示例文件规范

所有 TSN 示例文件应遵循以下建模范式：

```python
"""
[文件描述 - 包括拓扑结构和参数说明]
"""

import logging
from pycpa import model, analysis, path_analysis, schedulers, options

# ========================================
# 1. 定义公共参数
# ========================================
WCET = 12       # 最坏/最好执行时间 (us)
PERIOD = 1000   # 任务周期 (us)
CYCLE = 1000    # TAS 周期时间 (us)
WINDOW = 100    # TAS 窗口时间 (us)

# ========================================
# 2. 分析场景函数
# ========================================
def scenario_name():
    """
    [场景描述]
    """
    # 初始化 pyCPA 选项
    options.init_pycpa()

    # 创建系统
    s = model.System()

    # 创建资源（使用 TSN_Resource）
    sw1 = s.bind_resource(model.TSN_Resource(
        "Switch1",
        schedulers.TASScheduler(),  # 或 TASSchedulerE2E()
        priority_mechanism_map={7: 'TAS', 1: None},
        tas_cycle_time=CYCLE,
        tas_window_time_by_priority={7: WINDOW},
        # 可选: guard_band=10, guard_band_by_priority={7: 10, 1: 5}
    ))

    # 创建任务
    task1 = model.Task('Task1', bcet=WCET, wcet=WCET, scheduling_parameter=7)
    sw1.bind_task(task1)
    task1.in_event_model = model.PJdEventModel(P=PERIOD, J=0)

    # 如果是端到端分析，创建路径
    if needs_path:
        s.bind_path(model.Path('Path1', [task1, ...]))

    # 设置 TAS 对齐状态（用于 E2E 修正，仅在使用 TASSchedulerE2E 时有效）
    if needs_e2e_correction:
        # 如需 E2E 修正，请使用 TASSchedulerE2E() 而非 TASScheduler()
        task1.path.tas_aligned = True  # 或 False

    # 进行分析
    results = analysis.analyze_system(s)

    # 输出结果
    for p in s.paths:
        lmin, lmax = path_analysis.end_to_end_latency(p, results, 1)
        print(f"Path '{p.name}': BCRT={lmin} us, WCRT={lmax} us")

# ========================================
# 3. 主函数入口
# ========================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    scenario_name()
```

### TASScheduler 使用示例

**TASScheduler** 是基础的时间感知整形器调度器，适用于单跳分析：

**注意**: `TASScheduler` **不支持** E2E 修正和 `tas_aligned` 配置。它总是将 E2E 延迟计算为各跳 WCRT 的简单求和。如需使用 `tas_aligned` 的 E2E 修正功能，请使用 `TASSchedulerE2E`。

```python
from pycpa import model, analysis, schedulers, options

options.init_pycpa()
s = model.System()

# 创建使用 TASScheduler 的交换机
sw = s.bind_resource(model.TSN_Resource(
    "Switch",
    schedulers.TASScheduler(),
    priority_mechanism_map={7: 'TAS', 1: None},
    tas_cycle_time=1000,
    tas_window_time_by_priority={7: 100}
))

# 创建 TAS 任务
tas_task = model.Task('TAS_Task', bcet=12, wcet=12, scheduling_parameter=7)
sw.bind_task(tas_task)
tas_task.in_event_model = model.PJdEventModel(P=1000, J=0)

# 分析
results = analysis.analyze_system(s)
print(f"WCRT={results[tas_task].wcrt} us")
```

### TASSchedulerE2E 使用示例

**TASSchedulerE2E** 是 E2E 优化版 TAS 调度器，具有以下特性：

1. **多跳 E2E 延迟修正**: 当路径的 `tas_aligned` 属性被设置时，自动应用 E2E 修正公式（此功能在 `TASScheduler` 中**不提供**）
2. **Guard Band 配置**: 支持全局或按优先级配置 guard band

**重要说明**: 如果需要使用 E2E 修正分析多跳路径，**必须**使用 `TASSchedulerE2E()`，而不是 `TASScheduler()`。使用 `TASScheduler` 时，`path.tas_aligned` 属性无任何效果。

#### 示例 1: 多跳路径的 E2E 分析（对齐模式）

```python
from pycpa import model, analysis, path_analysis, schedulers, options

options.init_pycpa()
s = model.System()

# 创建两个交换机（使用 TASSchedulerE2E）
for i in range(1, 3):
    sw = s.bind_resource(model.TSN_Resource(
        f"Switch{i}",
        schedulers.TASSchedulerE2E(),
        priority_mechanism_map={7: 'TAS'},
        tas_cycle_time=1000,
        tas_window_time_by_priority={7: 100}
    ))

# 创建两跳流量
task_h1 = model.Task('Flow_h1', bcet=12, wcet=12, scheduling_parameter=7)
s.resources[0].bind_task(task_h1)
task_h1.in_event_model = model.PJdEventModel(P=1000, J=0)

task_h2 = model.Task('Flow_h2', bcet=12, wcet=12, scheduling_parameter=7)
s.resources[1].bind_task(task_h2)

# 链接任务
task_h1.link_dependent_task(task_h2)

# 创建路径并设置 TAS 对齐
s.bind_path(model.Path('Flow_Path', [task_h1, task_h2]))
task_h1.path.tas_aligned = True  # 第一跳无 gate-closed 阻塞

# 分析
results = analysis.analyze_system(s)
lmin, lmax = path_analysis.end_to_end_latency(task_h1.path, results, 1)
print(f"E2E (corrected): WCRT={lmax} us")
```

#### 示例 2: Guard Band 配置

```python
# 方式 1: 全局 guard_band（所有优先级）
sw_global = s.bind_resource(model.TSN_Resource(
    "Switch1",
    schedulers.TASSchedulerE2E(),
    priority_mechanism_map={7: 'TAS', 1: None},
    tas_cycle_time=1000,
    tas_window_time_by_priority={7: 100},
    guard_band=10  # 全局 guard_band = 10 us
))

# 方式 2: 按优先级 guard_band
sw_per_prio = s.bind_resource(model.TSN_Resource(
    "Switch2",
    schedulers.TASSchedulerE2E(),
    priority_mechanism_map={7: 'TAS', 1: None},
    tas_cycle_time=1000,
    tas_window_time_by_priority={7: 100},
    guard_band_by_priority={7: 10, 1: 5}  # 优先级 7: 10us, 优先级 1: 5us
))

# 方式 3: 不设置（使用默认行为）
# TAS 流: guard_band = task.wcet
# NST 流: guard_band 计算为 max(流的 wcet)
sw_default = s.bind_resource(model.TSN_Resource(
    "Switch3",
    schedulers.TASSchedulerE2E(),
    priority_mechanism_map={7: 'TAS', 1: None},
    tas_cycle_time=1000,
    tas_window_time_by_priority={7: 100}
))
```

#### 示例 3: 交换机转发延迟

```python
from pycpa import model, analysis, path_analysis, schedulers, options

options.init_pycpa()
s = model.System()

# 方式 1: 对称延迟 (bcet = wcet = 5 us)
sw1 = s.bind_resource(model.TSN_Resource(
    "Switch1", schedulers.TASSchedulerE2E(),
    priority_mechanism_map={7: 'TAS'},
    tas_cycle_time=1000,
    tas_window_time_by_priority={7: 100},
    forwarding_delay=5
))

# 方式 2: 非对称延迟 (bcet=3, wcet=7)
sw2 = s.bind_resource(model.TSN_Resource(
    "Switch2", schedulers.TASSchedulerE2E(),
    priority_mechanism_map={7: 'TAS'},
    tas_cycle_time=1000,
    tas_window_time_by_priority={7: 100},
    forwarding_delay=(3, 7)
))

# 创建两跳流量
task_h1 = model.Task('Flow_h1', bcet=12, wcet=12, scheduling_parameter=7)
sw1.bind_task(task_h1)
task_h1.in_event_model = model.PJdEventModel(P=1000, J=0)

task_h2 = model.Task('Flow_h2', bcet=12, wcet=12, scheduling_parameter=7)
sw2.bind_task(task_h2)
task_h1.link_dependent_task(task_h2)

# 创建路径并自动添加转发延迟
path = model.Path('Flow_Path', [task_h1, task_h2])
s.bind_path(path)
model.add_forwarding_delays_for_path(path)
# 路径变为: Flow_h1 -> FD_Switch1 -> Flow_h2 -> FD_Switch2

# 分析
results = analysis.analyze_system(s)
lmin, lmax = path_analysis.end_to_end_latency(path, results, 1)
print(f"E2E: min={lmin} us, max={lmax} us")
```

#### 示例 4: 综合多跳分析

本示例综合使用了 TASSchedulerE2E 的所有配置项：TAS 与非 TAS 混合优先级、按优先级和全局 guard band、非对称和对称转发延迟、`tas_aligned` E2E 修正、多流干扰。

```python
from pycpa import model, analysis, path_analysis, schedulers, options

options.init_pycpa()
s = model.System()

# Switch1: 按优先级 guard_band + 非对称转发延迟 (bcet=3, wcet=7)
sw1 = s.bind_resource(model.TSN_Resource(
    "Switch1", schedulers.TASSchedulerE2E(),
    priority_mechanism_map={7: 'TAS', 1: None},   # TAS + 非 TAS 共存
    tas_cycle_time=1000,
    tas_window_time_by_priority={7: 100},
    guard_band_by_priority={7: 10, 1: 5},          # 按优先级 guard band
    forwarding_delay=(3, 7)                         # 非对称转发延迟
))

# Switch2: 全局 guard_band + 对称转发延迟
sw2 = s.bind_resource(model.TSN_Resource(
    "Switch2", schedulers.TASSchedulerE2E(),
    priority_mechanism_map={7: 'TAS', 1: None},
    tas_cycle_time=1000,
    tas_window_time_by_priority={7: 100},
    guard_band=8,                                   # 全局 guard band
    forwarding_delay=5                              # 对称转发延迟
))

# TAS 流 (优先级 7): 两跳，周期 1000 us
tas_h1 = model.Task('TAS_h1', bcet=12, wcet=12, scheduling_parameter=7)
sw1.bind_task(tas_h1)
tas_h1.in_event_model = model.PJdEventModel(P=1000, J=0)

tas_h2 = model.Task('TAS_h2', bcet=12, wcet=12, scheduling_parameter=7)
sw2.bind_task(tas_h2)
tas_h1.link_dependent_task(tas_h2)

# 非 TAS 流 (优先级 1): 两跳，周期 2000 us，与 TAS 流共存
nst_h1 = model.Task('NST_h1', bcet=50, wcet=50, scheduling_parameter=1)
sw1.bind_task(nst_h1)
nst_h1.in_event_model = model.PJdEventModel(P=2000, J=0)

nst_h2 = model.Task('NST_h2', bcet=50, wcet=50, scheduling_parameter=1)
sw2.bind_task(nst_h2)
nst_h1.link_dependent_task(nst_h2)

# TAS 路径，启用 E2E 修正（对齐模式）
tas_path = model.Path('TAS_Path', [tas_h1, tas_h2])
tas_path.tas_aligned = True    # 启用 E2E 修正，对齐模式
s.bind_path(tas_path)

# 非 TAS 路径（不启用 E2E 修正）
nst_path = model.Path('NST_Path', [nst_h1, nst_h2])
s.bind_path(nst_path)

# 根据资源配置自动为所有路径添加转发延迟
model.auto_add_forwarding_delays(s)
# TAS_Path: TAS_h1 -> FD_Switch1(3,7) -> TAS_h2 -> FD_Switch2(5,5)
# NST_Path: NST_h1 -> FD_Switch1(3,7) -> NST_h2 -> FD_Switch2(5,5)

# 分析
results = analysis.analyze_system(s)

# 输出 TAS 路径结果
print("TAS Path:", [t.name for t in tas_path.tasks])
for t in tas_path.tasks:
    if t in results:
        is_fd = model.ForwardingTask.is_forwarding_task(t)
        marker = " [FD]" if is_fd else ""
        print(f"  {t.name}{marker}: WCRT={results[t].wcrt} us, BCRT={results[t].bcrt} us")
lmin, lmax = path_analysis.end_to_end_latency(tas_path, results, 1)
print(f"  E2E (corrected, aligned): min={lmin} us, max={lmax} us")

# 输出非 TAS 路径结果
print()
print("NST Path:", [t.name for t in nst_path.tasks])
for t in nst_path.tasks:
    if t in results:
        is_fd = model.ForwardingTask.is_forwarding_task(t)
        marker = " [FD]" if is_fd else ""
        print(f"  {t.name}{marker}: WCRT={results[t].wcrt} us, BCRT={results[t].bcrt} us")
lmin, lmax = path_analysis.end_to_end_latency(nst_path, results, 1)
print(f"  E2E: min={lmin} us, max={lmax} us")
```

## TSN 配置参数说明

### TSN_Resource 构造参数

#### 优先级-机制映射

| 参数 | 类型 | 必需 | 描述 |
|-----|------|-----|------|
| `priority_mechanism_map` | dict | 否 | 优先级到调度机制的映射 |

`priority_mechanism_map` 格式说明：
- 键: 优先级（整数）或优先级对（元组，用于 CQF）
- 值: 机制名称字符串 (`'TAS'`, `'CQF'`, `'CBS'`, `'ATS'`, 或 `None`)

```python
priority_mechanism_map={
    7: 'TAS',           # 优先级 7 使用 TAS
    6: 'TAS',           # 优先级 6 使用 TAS
    (5, 4): 'CQF',      # 优先级 5 和 4 组成 CQF 对
    1: 'CBS',           # 优先级 1 使用 CBS
    0: None,            # 优先级 0 无特殊机制
}
```

#### TAS (Time-Aware Shaper) 参数

| 参数 | 类型 | 必需 | 描述 |
|-----|------|-----|------|
| `tas_cycle_time` | int/float | 是（使用 TAS 时） | TAS 门控列表（GCL）的周期时间，单位微秒 |
| `tas_window_time` | int/float | 否 | 默认 gate open 窗口持续时间 |
| `tas_window_time_by_priority` | dict | 是（使用 TAS 时） | 按优先级 TAS 窗口时间映射，如 `{7: 100, 6: 200}` |
| `guard_band` | int/float | 否 | 全局 guard band 持续时间，适用于 TASSchedulerE2E |
| `guard_band_by_priority` | dict | 否 | 按优先级 guard band 映射，如 `{7: 10, 5: 8}` |

**Guard Band 含义**: Guard band 是保留的时间，用于防止帧在其 gate 关闭后仍在链路上传输（由于链路传播延迟）。当 gate 关闭时，确保没有正在传输的帧被中断。

#### CBS (Credit-Based Shaper) 参数

| 参数 | 类型 | 必需 | 描述 |
|-----|------|-----|------|
| `idleslope` | int/float | 否 | 默认 idleSlope 参数，单位比特/秒 |
| `idleslope_by_priority` | dict | 是（使用 CBS 时） | 按优先级 idleSlope 映射，如 `{1: 5000000}` |

#### CQF (Cyclic Queuing and Forwarding) 参数

| 参数 | 类型 | 必需 | 描述 |
|-----|------|-----|------|
| `cqf_cycle_time` | int/float | 否 | CQF 队列的默认循环周期 |
| `cqf_cycle_time_by_pair` | dict | 是（使用 CQF 时） | 按 CQF 对的循环周期映射，如 `{(5, 4): 500}` |

#### 帧抢占参数

| 参数 | 类型 | 必需 | 描述 |
|-----|------|-----|------|
| `is_express` | bool | 否 | 端口上帧抢占的默认分类 |
| `is_express_by_priority` | dict | 否 | 按优先级抢占分类，如 `{7: True, 1: False}` |

#### ATS (Asynchronous Traffic Shaping) 参数

| 参数 | 类型 | 必需 | 描述 |
|-----|------|-----|------|
| `ats_cir` | int/float | 否 | 默认承诺信息速率 |
| `ats_cbs` | int/float | 否 | 默认承诺突发大小 |
| `ats_eir` | int/float | 否 | 默认超出信息速率 |
| `ats_ebs` | int/float | 否 | 默认超出突发大小 |
| `ats_scheduler_group` | int | 否 | 默认调度器组 |
| `ats_params_by_priority` | dict | 是（使用 ATS 时） | 按优先级 ATS 参数映射 |

#### 交换机转发延迟参数

| 参数 | 类型 | 必需 | 描述 |
|-----|------|-----|------|
| `forwarding_delay` | int/float 或 tuple | 否 | 交换机转发延迟，单位微秒。单个数值表示对称延迟（`bcet=wcet`），`(bcet, wcet)` 元组表示非对称延迟 |

### Path 属性

| 属性 | 类型 | 使用条件 | 描述 |
|-----|------|----------|------|
| `tas_aligned` | bool | TASSchedulerE2E 多跳分析 | 是否 TAS 时间窗对齐。True 表示第一跳无 gate-closed 阻塞，False 表示第一跳有 1 次 gate-closed 阻塞 |

### TASSchedulerE2E Task Results 属性

使用 TASSchedulerE2E 分析完成后，任务结果包含以下额外属性：

| 属性 | 类型 | 描述 |
|-----|------|------|
| `gate_closed_duration` | int/float | 一个完整的 gate-closed 周期的持续时间 |
| `non_gate_closed` | int/float | WCRT 中排除 gate-closed 阻塞的部分 |

## E2E 修正说明

**注意**: E2E 修正仅在使用 `TASSchedulerE2E` 时可用。当使用 `TASScheduler` 时，无论 `path.tas_aligned` 设置为何值，E2E 延迟始终计算为各跳 WCRT 的简单求和。

当使用 `TASSchedulerE2E` 且 `path.tas_aligned` 被设置时，端到端延迟计算会应用修正公式：

```
E2E_corrected = sum(non_gate_closed) + K_actual * G_duration + sum(forwarding_delay_wcrt)
```

其中：
- `non_gate_closed`: 每个常规跳 WCRT 排除 gate-closed 阻塞的部分
- `G_duration`: gate-closed 周期持续时间 = `tas_cycle - tas_window + guard_band`
- `K_actual = K_base + floor(sum_non_gate_closed / tas_window)`
  - `K_base = 0` 当 `tas_aligned = True`
  - `K_base = 1` 当 `tas_aligned = False`
- `forwarding_delay_wcrt`: 路径上每个转发延迟任务的 WCRT（独立累加，不受门控修正影响）

## 完整示例

### 双跳 TAS 流量分析（对齐模式）

```python
from pycpa import model, analysis, path_analysis, schedulers, options

# 参数配置
WCET = 12      # 1518 字节 @ 1Gbps
PERIOD = 1000  # us
CYCLE = 1000   # TAS 周期时间 (us)
WINDOW = 100   # TAS 窗口时间 (us)

def two_hop_tas_aligned():
    """双跳 TAS 流量分析，使用对齐模式。"""
    options.init_pycpa()
    s = model.System()

    # 创建两个交换机
    for i in range(1, 3):
        s.bind_resource(model.TSN_Resource(
            f"Switch{i}",
            schedulers.TASSchedulerE2E(),
            priority_mechanism_map={7: 'TAS'},
            tas_cycle_time=CYCLE,
            tas_window_time_by_priority={7: WINDOW}
        ))

    # 创建两跳任务
    task_h1 = model.Task('Flow_h1', bcet=WCET, wcet=WCET, scheduling_parameter=7)
    s.resources[0].bind_task(task_h1)
    task_h1.in_event_model = model.PJdEventModel(P=PERIOD, J=0)

    task_h2 = model.Task('Flow_h2', bcet=WCET, wcet=WCET, scheduling_parameter=7)
    s.resources[1].bind_task(task_h2)

    # 链接并创建路径
    task_h1.link_dependent_task(task_h2)
    s.bind_path(model.Path('Flow_Path', [task_h1, task_h2]))

    # 设置 TAS 对齐
    task_h1.path.tas_aligned = True

    # 分析并输出
    results = analysis.analyze_system(s)
    print(f"Hop1 WCRT: {results[task_h1].wcrt} us")
    print(f"Hop2 WCRT: {results[task_h2].wcrt} us")

    lmin, lmax = path_analysis.end_to_end_latency(task_h1.path, results, 1)
    print(f"E2E (corrected): BCRT={lmin} us, WCRT={lmax} us")

if __name__ == "__main__":
    two_hop_tas_aligned()
```

## 参考文献

- **TASScheduler**:
  THIELE D, ERNST R, DIEMER J. Formal worst-case timing analysis of Ethernet TSN's time-aware and peristaltic shapers[C]//2015 IEEE Vehicular Networking Conference (VNC). Kyoto, Japan: IEEE, 2015: 251-258.

- **TASSchedulerE2E** (E2E 修正和抢占支持):
  Luo F, Zhu L, Wang Z, et al. Schedulability analysis of time aware shaper with preemption supported in time-sensitive networks[J]. Computer Networks, 2025, 269: 111424.

## 贡献

欢迎提交 Issue 和 Pull Request。

## 待办事项 / TODO

以下功能计划在后续版本中实现：

1. **实现单独 TSN 机制的 WCRT 计算**：
   - CQF (循环排队转发)
   - ATS (异步流量整形)
   - CBS (基于信用的整形器)
   - 帧抢占

2. **逐步完善机制融合下的各类流 WCRT 计算**：
   - 从两两机制结合开始
   - 逐步扩展支持多机制组合
   - 最终支持全机制融合场景

3. **实现基于轨迹法的 WCRT 更紧密计算**：
   - 集成轨迹分析法以获得更精确的 WCRT 边界
   - 改进对齐调度下的多跳场景分析精度
