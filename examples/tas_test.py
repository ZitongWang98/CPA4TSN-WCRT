"""
TAS (Time-Aware Shaper) analysis example

This example demonstrates the usage of TASScheduler with plain Task objects
bound to a TSN_Resource for Ethernet TSN networks.

Scenario:
=========
- Simple network with one switch and three terminals
- Terminal1 (T1) and Terminal2 (T2) are sending nodes
- Terminal3 (T3) is the receiving node
- Two flows: Flow1 from T1 to T3, Flow2 from T2 to T3
- Flow1 uses TAS scheduling (ST - Schedulable Traffic)
- Flow2 does NOT use TAS (BE - Best Effort Traffic)

Analysis Based on:
==================
THIELE D, ERNST R, DIEMER J. Formal worst-case timing analysis of
Ethernet TSN's time-aware and peristaltic shapers[C]//2015 IEEE
Vehicular Networking Conference (VNC). Kyoto, Japan: IEEE, 2015: 251-258.
"""

from pycpa import model
from pycpa import analysis
from pycpa import schedulers
from pycpa import graph
from pycpa import options


def tas_test():
    """ TAS analysis test with a switch and three terminals """

    options.init_pycpa()

    # Create system
    s = model.System()

    # Create switch resource with TASScheduler and TSN port-level parameters
    # priority_mechanism_map defines which priorities use which TSN mechanism
    switch = s.bind_resource(model.TSN_Resource("Switch", schedulers.TASScheduler(),
                                                priority_mechanism_map={
                                                    7: 'TAS',
                                                    1: None,
                                                },
                                                tas_cycle_time=1000,
                                                tas_window_time_by_priority={7: 100}))

    # --- Terminal 1 (Sending Node) ---
    # Plain Task — mechanism is determined by priority 7 -> TAS (from resource map)
    # wcet=bcet=12us: Ethernet frame transmission time on 1Gbps (1518 bytes)
    t1_flow = model.Task('Flow1', wcet=12, bcet=12,
                         scheduling_parameter=7)
    # Input event model: periodic without jitter (P=1000us, d=0us)
    t1_flow.in_event_model = model.PJdEventModel()
    t1_flow.in_event_model.set_PJd(1000, 0)

    # --- Terminal 2 (Sending Node) ---
    # Create regular Task for Best Effort (BE) traffic - no TAS scheduling
    # wcet=bcet=12us: Ethernet frame transmission time on 1Gbps (1518 bytes)
    t2_flow = model.Task('Flow2', wcet=12, bcet=12,
                         scheduling_parameter=1)  # Lower priority than Flow1
    # Input event model: periodic without jitter (P=1000us, d=0us)
    t2_flow.in_event_model = model.PJdEventModel()
    t2_flow.in_event_model.set_PJd(1000, 0)

    # Bind tasks to switch resource
    switch.bind_task(t1_flow)
    switch.bind_task(t2_flow)

    # Generate network graph
    graph.graph_system(s, 'tas_network_graph.pdf')
    print("Network graph generated: tas_network_graph.pdf")

    # Perform analysis
    print("\nPerforming mixed TAS/BE analysis...")
    print("=" * 60)
    print("System Configuration:")
    print("  - Switch Resource: TASScheduler")
    print("  - Flow1 (ST): TAS (cycle/window configured on resource), wcet=bcet=12us (1Gbps, 1518B)")
    print("  - Flow2 (BE): No TAS, wcet=bcet=12us (1Gbps, 1518B)")
    print("  - Both flows: Period=1000us, Jitter=0us")
    print("=" * 60)

    try:
        results = analysis.analyze_system(s)

        print("\nResults:")
        print("-" * 60)
        for r in sorted(s.resources, key=str):
            for t in sorted(r.tasks, key=str):
                print(f"{str(t)}:")
                print(f"  WCET: {t.wcet}")
                print(f"  BCET: {t.bcet}")
                print(f"  Priority: {t.scheduling_parameter}")
                res = t.resource
                if getattr(res, 'is_tsn_resource', False) and res.priority_uses_tas(t.scheduling_parameter):
                    print(f"  TAS Cycle Time: {res.effective_tas_cycle_time(t.scheduling_parameter)}")
                    print(f"  TAS Window Time: {res.effective_tas_window_time(t.scheduling_parameter)}")
                print(f"  WCRT: {results[t].wcrt}")
                print(f"  BCRT: {results[t].bcrt}")
                print(f"  Jitter: {results[t].wcrt - results[t].bcrt}")
                print(f"  Busy Times: {results[t].busy_times[:5]}...")  # Show first 5
        print("-" * 60)

    except Exception as e:
        print(f"\nAnalysis failed: {e}")
        print("Note: TASScheduler implementation is incomplete.")
        print("This test demonstrates the setup and parameter configuration.")


if __name__ == "__main__":
    tas_test()
