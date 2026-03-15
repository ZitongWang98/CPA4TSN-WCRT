"""
ADAS + Entertainment scenario for CQFPScheduler validation.
Replicates the exact scenario from the Luo2023 paper / old ADAS_and_ENT.py.

37 streams across 24 switch ports, 4 traffic classes.
"""
from pycpa import model, analysis, schedulers_cqfp as cqfp, options


def make_resource(s, name, ct, st_class, sra_class, srb_class, be_class):
    """Create TSN_Resource with priority-mechanism map derived from traffic class config."""
    # Map old traffic_class codes to (uses_cqf, is_express)
    # 0=N+E, 1=N+P, 2=C+E, 3=C+P
    TC = {0: (False, True), 1: (False, False), 2: (True, True), 3: (True, False)}

    # Build priority_mechanism_map and is_express_by_priority
    prio_map = {}
    express_map = {}
    cqf_pairs = {}

    classes = {7: TC[st_class], 5: TC[sra_class], 3: TC[srb_class], 1: TC[be_class]}

    # Collect CQF priorities to form pairs
    cqf_prios = [p for p, (cqf, _) in classes.items() if cqf]
    non_cqf_prios = [p for p, (cqf, _) in classes.items() if not cqf]

    for p in non_cqf_prios:
        prio_map[p] = None
        express_map[p] = classes[p][1]

    # Each CQF priority needs a pair; use (p, p-1)
    for p in cqf_prios:
        pair = (p, p - 1)
        prio_map[pair] = 'CQF'
        express_map[p] = classes[p][1]
        express_map[p - 1] = classes[p][1]
        cqf_pairs[pair] = ct

    r = model.TSN_Resource(name, cqfp.CQFPScheduler(),
        priority_mechanism_map=prio_map,
        cqf_cycle_time=ct,
        cqf_cycle_time_by_pair=cqf_pairs if cqf_pairs else None,
        is_express_by_priority=express_map)
    s.bind_resource(r)
    return r


def adas_scenario(st_class, sra_class, srb_class, be_class, cycletime):
    s = model.System("ADAS")

    R = {}
    port_names = [
        "ZC_FR_port0", "ZC_FR_port1", "ZC_FR_port2", "ZC_FR_port3",
        "ZC_FL_port0", "ZC_FL_port1", "ZC_FL_port2",
        "ZC_RR_port0", "ZC_RR_port1", "ZC_RR_port2",
        "ZC_RL_port0", "ZC_RL_port1",
        "SwitchA_port0", "SwitchA_port1", "SwitchA_port2",
        "SwitchA_port3", "SwitchA_port4", "SwitchA_port5",
        "SwitchB_port0", "SwitchB_port1", "SwitchB_port2",
        "SwitchB_port3", "SwitchB_port4", "SwitchB_port5",
    ]
    for name in port_names:
        R[name] = make_resource(s, name, cycletime, st_class, sra_class, srb_class, be_class)

    def add_task(port, name, wcet, prio, payload):
        t = model.Task(name, wcet, wcet, prio, payload=payload)
        R[port].bind_task(t)
        return t

    tasks = {}
    streams = {}

    # Helper to define a stream
    def stream(sid, hops, wcet, prio, payload, period, jitter):
        ts = []
        for i, port in enumerate(hops):
            t = add_task(port, f"T{sid}{i+1}" if len(hops) > 1 else f"T{sid}1", wcet, prio, payload)
            ts.append(t)
        ts[0].in_event_model = model.PJdEventModel(P=period, J=jitter)
        for i in range(len(ts) - 1):
            ts[i].link_dependent_task(ts[i + 1])
        streams[sid] = ts
        return ts

    # ST streams (prio 7)
    stream(1,  ["SwitchA_port5", "SwitchB_port5"], 1.936, 7, 200, 1000000, 100000)
    stream(2,  ["SwitchA_port5", "SwitchB_port5"], 1.936, 7, 200, 200000, 20000)
    stream(3,  ["SwitchA_port5", "SwitchB_port5"], 1.936, 7, 200, 5000, 500)
    stream(4,  ["SwitchA_port5", "SwitchB_port5"], 1.936, 7, 200, 50000, 5000)
    stream(5,  ["SwitchA_port5", "SwitchB_port5"], 1.936, 7, 200, 100000, 10000)
    stream(6,  ["SwitchA_port5", "SwitchB_port5"], 1.936, 7, 200, 100000, 10000)
    stream(7,  ["SwitchA_port5", "SwitchB_port5"], 1.936, 7, 200, 200000, 20000)
    stream(8,  ["SwitchA_port5", "SwitchB_port5"], 1.936, 7, 200, 500000, 50000)
    stream(9,  ["SwitchA_port5", "SwitchB_port5"], 1.936, 7, 200, 1000000, 100000)
    stream(10, ["SwitchA_port5", "SwitchB_port5"], 1.936, 7, 200, 1000000, 100000)
    stream(11, ["SwitchB_port0", "SwitchA_port3"], 1.936, 7, 200, 100000, 10000)
    stream(12, ["SwitchB_port0", "SwitchA_port3"], 1.936, 7, 200, 200000, 20000)
    stream(13, ["SwitchB_port0", "SwitchA_port3"], 1.936, 7, 200, 500000, 50000)
    stream(14, ["SwitchB_port0", "SwitchA_port3"], 1.936, 7, 200, 500000, 50000)
    stream(15, ["SwitchB_port0", "SwitchA_port3"], 1.936, 7, 200, 1000000, 100000)
    stream(16, ["SwitchB_port0", "SwitchA_port0"], 1.936, 7, 200, 10000, 1000)
    stream(17, ["SwitchB_port0", "SwitchA_port0"], 1.936, 7, 200, 1000000, 100000)
    stream(18, ["ZC_FR_port3", "SwitchA_port5", "SwitchB_port5"], 1.936, 7, 200, 5000, 500)
    stream(19, ["ZC_FL_port2", "SwitchA_port5", "SwitchB_port5"], 1.936, 7, 200, 5000, 500)
    stream(20, ["ZC_RR_port2", "SwitchB_port5"], 1.936, 7, 200, 5000, 500)
    stream(21, ["ZC_RL_port1", "SwitchB_port5"], 1.936, 7, 200, 5000, 500)

    # SRA streams (prio 5)
    stream(22, ["ZC_FR_port3", "SwitchA_port0"], 12.336, 5, 1500, 1200, 120)
    stream(23, ["ZC_FL_port2", "SwitchA_port0"], 12.336, 5, 1500, 1200, 120)
    stream(24, ["ZC_FR_port3", "SwitchA_port0"], 12.336, 5, 1500, 1200, 120)
    stream(25, ["ZC_RR_port2", "SwitchB_port0", "SwitchA_port0"], 12.336, 5, 1500, 1200, 120)

    # SRB streams (prio 3)
    stream(26, ["SwitchA_port3"], 3.536, 3, 400, 5000, 500)
    stream(27, ["SwitchA_port5", "SwitchB_port2"], 5.136, 3, 600, 5000, 500)
    stream(29, ["SwitchB_port2"], 12.336, 3, 400, 1200, 120)

    # BE streams (prio 1)
    stream(28, ["SwitchA_port3"], 12.336, 1, 1500, 6000, 600)

    # More ST
    stream(30, ["SwitchA_port3"], 1.936, 7, 200, 200000, 20000)
    stream(31, ["SwitchA_port3"], 1.936, 7, 200, 1000000, 100000)
    stream(32, ["SwitchA_port0"], 1.936, 7, 200, 100000, 10000)
    stream(33, ["SwitchA_port0"], 1.936, 7, 200, 200000, 20000)
    stream(34, ["SwitchA_port0"], 1.936, 7, 200, 500000, 50000)

    # SRA
    stream(35, ["SwitchA_port3"], 12.336, 5, 1500, 1200, 120)

    # SRB
    stream(36, ["SwitchB_port0", "SwitchA_port3"], 5.136, 3, 600, 100000, 10000)

    # BE
    stream(37, ["SwitchB_port0", "SwitchA_port3"], 12.336, 1, 1500, 6000, 600)

    results = analysis.analyze_system(s)

    # Compute E2E latencies (same as old code)
    e2e = {}
    for sid, ts in streams.items():
        wcet_last = ts[-1].wcet
        e2e[sid] = sum(results[t].wcrt for t in ts) + wcet_last

    return results, streams, e2e


if __name__ == "__main__":
    options.init_pycpa()

    print("=" * 60)
    print("Config 1: ST=N+E, SRA=C+E, SRB=N+P, BE=C+P, cycle=200")
    print("=" * 60)
    results, streams, e2e = adas_scenario(0, 2, 1, 3, 200)

    for sid in sorted(e2e.keys()):
        ts = streams[sid]
        per_hop = " + ".join(f"{results[t].wcrt:.3f}" for t in ts)
        print(f"  Stream {sid:2d}: E2E = {e2e[sid]:10.3f}  ({per_hop} + {ts[-1].wcet})")
