#!/usr/bin/env python3
"""Paper evaluation experiments.

Automotive TSN topology inspired by Gavrilut et al. [IEEE Access 2018]
and Tamas-Selicean et al. [Real-Time Systems 2015] ("SAE" test case).

5-switch zonal architecture, 16 flows, 6 traffic classes (ST/CQF/ATS/NC+E/NC+P).
Port-level modeling: each directed link is a separate egress-port resource.
Link speed 1 Gbps, periods 100 μs – 10 ms.

E1: Automotive TSN topology baseline (5 switches, 16 flows, 6 traffic classes)
E2: E2E improvement vs hop count (2-7 hops)
E3: Cross-interference necessity (fusion vs ignoring TAS gate blocking)
E4: Closed-loop configuration vs traffic load (light/medium/heavy)
E5: Configuration iteration curves (parameter + E2E convergence)
E6: Single-hop WCRT breakdown
E7: Scalability (analysis time vs flow count)
"""
import sys, os, copy, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pycpa import model, analysis, path_analysis, options
from pycpa.schedulers_fusion import FusionScheduler, FusionSchedulerE2E

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'config_optimizer'))
from config_optimizer import FusionConfigOptimizer

options.set_opt('e2e_improved', False)

# ======================================================================
# Helpers
# ======================================================================

def make_resource(name, sched_cls=FusionSchedulerE2E, tas_w=100,
                  tas_c=500, cqf_c=500, has_ats=True, linkspeed=1e9):
    r = model.TSN_Resource(name, scheduler=sched_cls(), linkspeed=linkspeed)
    pmap = {7: 'TAS', (5, 4): 'CQF', 3: None, 2: None, 1: None}
    if has_ats:
        pmap[6] = 'ATS'
    r.priority_mechanism_map = pmap
    r.tas_cycle_time = tas_c
    r.tas_window_time_by_priority = {7: tas_w}
    r.cqf_cycle_time_by_pair = {(5, 4): cqf_c}
    r.is_express_by_priority = {
        7: True, 6: True, 5: True, 4: True, 3: True, 2: False, 1: False}
    return r


def make_flow(system, resources, name, prio, wcet, period,
              tas_aligned=None, cir=None, cbs=None, payload=None):
    """Create multi-hop flow, return (path, tasks)."""
    tasks = []
    for i, r in enumerate(resources):
        kw = dict(wcet=wcet, bcet=wcet, scheduling_parameter=prio)
        if cir is not None:
            kw['CIR'] = cir; kw['CBS'] = cbs or 12000
        if payload is not None:
            kw['payload'] = payload
        t = model.Task('%s_h%d' % (name, i), **kw)
        if i == 0:
            t.in_event_model = model.PJdEventModel(P=period, J=0)
        r.bind_task(t)
        if i > 0:
            tasks[-1].link_dependent_task(t)
        tasks.append(t)
    p = model.Path('path_%s' % name, tasks)
    if tas_aligned is not None:
        p.tas_aligned = tas_aligned
    system.bind_path(p)
    return p, tasks


def add_background(r, prefix, st_wcet=10, ats_wcet=12):
    """Add ST + ATS interferers on a resource (background traffic)."""
    t_st = model.Task('%s_ST' % prefix, wcet=st_wcet, bcet=st_wcet,
                      scheduling_parameter=7)
    t_st.in_event_model = model.PJdEventModel(P=500, J=0)
    r.bind_task(t_st)
    if r.get_mechanism_for_priority(6) == 'ATS':
        t_ats = model.Task('%s_ATS' % prefix, wcet=ats_wcet, bcet=ats_wcet,
                           scheduling_parameter=6, CIR=100e6, CBS=12000,
                           src_port='bg')
        t_ats.in_event_model = model.PJdEventModel(P=500, J=0)
        r.bind_task(t_ats)


# ======================================================================
# E1: Automotive TSN Topology
# ======================================================================

def build_automotive_topology(sched_cls=FusionSchedulerE2E, tas_w=100,
                              tas_c=500, cqf_c=500, scale=1.0):
    """Build automotive TSN topology inspired by Gavrilut et al. [IEEE Access 2018].

    Topology: 5-switch zonal architecture with bidirectional traffic.
    Port-level modeling: each directed link is a separate egress-port resource.

        ES1,ES2 ── SW1 ── SW2 ── SW3 ── SW4 ── SW5 ── ES7,ES8
                                   │
                                 ES5,ES6

    6 traffic classes: ST (TAS), CQF, ATS, NC+Express, NC+Preemptable.
    Link speed: 1 Gbps.  Frame sizes: 64–1522 B (wcet in μs at 1 Gbps).
    Periods: 100 μs – 10 ms, matching SAE automotive communication profiles.

    scale: multiplier for wcet (traffic load scaling)
    """
    s = model.System('automotive')
    ports = {}

    # Create egress port resources for each directed link
    for i, j in [(1,2),(2,1),(2,3),(3,2),(3,4),(4,3),(4,5),(5,4)]:
        name = 'SW%d_to_SW%d' % (i, j)
        ports[(i,j)] = make_resource(name, sched_cls, tas_w, tas_c, cqf_c)
        s.bind_resource(ports[(i,j)])

    def port_chain(sw_list):
        """[1,2,3,4] → [ports[(1,2)], ports[(2,3)], ports[(3,4)]]"""
        return [ports[(sw_list[k], sw_list[k+1])] for k in range(len(sw_list)-1)]

    paths = {}
    C = scale
    # wcet at 1 Gbps: 1 byte = 8 ns = 0.008 μs
    # 300 B frame → 2.4 μs,  800 B → 6.4 μs,  1522 B → 12.2 μs

    # --- ST flows (brake/steering, hard real-time, TAS-scheduled) ---
    # ST1: brake command, 4 hops, 300 B, period 500 μs
    paths['ST1'] = make_flow(s, port_chain([1,2,3,4,5]), 'ST1', 7,
                             wcet=int(10*C), period=500, tas_aligned=True)
    # ST2: brake feedback, 4 hops reverse, 350 B, period 500 μs
    paths['ST2'] = make_flow(s, port_chain([5,4,3,2,1]), 'ST2', 7,
                             wcet=int(12*C), period=500, tas_aligned=True)
    # ST3: steering, 2 hops, 250 B, period 1000 μs
    paths['ST3'] = make_flow(s, port_chain([1,2,3]), 'ST3', 7,
                             wcet=int(8*C), period=1000, tas_aligned=True)
    # ST4: powertrain, 2 hops, 300 B, period 1000 μs
    paths['ST4'] = make_flow(s, port_chain([3,4,5]), 'ST4', 7,
                             wcet=int(10*C), period=1000, tas_aligned=True)

    # --- CQF flows (lidar/radar fusion, cyclic queuing) ---
    # CQF1: lidar point cloud, 3 hops, 1500 B, period 1000 μs
    paths['CQF1'] = make_flow(s, port_chain([1,2,3,4]), 'CQF1', 5,
                              wcet=int(15*C), period=1000)
    # CQF2: radar return, 3 hops reverse, 1200 B, period 1000 μs
    paths['CQF2'] = make_flow(s, port_chain([5,4,3,2]), 'CQF2', 5,
                              wcet=int(12*C), period=1000)
    # CQF3: ultrasonic, 2 hops, 1000 B, period 500 μs
    paths['CQF3'] = make_flow(s, port_chain([2,3,4]), 'CQF3', 5,
                              wcet=int(10*C), period=500)

    # --- ATS flows (camera/sensor, asynchronous traffic shaping) ---
    # ATS1: front camera, 2 hops, 1522 B, period 2000 μs
    paths['ATS1'] = make_flow(s, port_chain([1,2,3]), 'ATS1', 6,
                              wcet=int(20*C), period=2000,
                              cir=200e6, cbs=24000)
    # ATS2: rear camera, 2 hops reverse, 1200 B, period 2000 μs
    paths['ATS2'] = make_flow(s, port_chain([5,4,3]), 'ATS2', 6,
                              wcet=int(15*C), period=2000,
                              cir=150e6, cbs=18000)
    # ATS3: surround sensor, 3 hops, 1000 B, period 2000 μs
    paths['ATS3'] = make_flow(s, port_chain([2,3,4,5]), 'ATS3', 6,
                              wcet=int(12*C), period=2000,
                              cir=100e6, cbs=15000)

    # --- NC express flows (OTA update, diagnostics) ---
    # NC_E1: OTA download, 4 hops, 1500 B, period 5000 μs
    paths['NC_E1'] = make_flow(s, port_chain([1,2,3,4,5]), 'NC_E1', 3,
                               wcet=int(15*C), period=5000, tas_aligned=False)
    # NC_E2: diagnostic response, 4 hops reverse, 1200 B, period 5000 μs
    paths['NC_E2'] = make_flow(s, port_chain([5,4,3,2,1]), 'NC_E2', 3,
                               wcet=int(12*C), period=5000, tas_aligned=False)

    # --- NC preemptable flows (logging, bulk transfer) ---
    # NC_P1: event log, 2 hops, 300 B, period 10000 μs
    paths['NC_P1'] = make_flow(s, port_chain([1,2,3]), 'NC_P1', 2,
                               wcet=int(15*C), period=10000,
                               tas_aligned=False, payload=300)
    # NC_P2: map update, 2 hops, 250 B, period 10000 μs
    paths['NC_P2'] = make_flow(s, port_chain([3,4,5]), 'NC_P2', 2,
                               wcet=int(12*C), period=10000,
                               tas_aligned=False, payload=250)
    # NC_P3: telemetry, 4 hops reverse, 200 B, period 10000 μs
    paths['NC_P3'] = make_flow(s, port_chain([5,4,3,2,1]), 'NC_P3', 1,
                               wcet=int(10*C), period=10000,
                               tas_aligned=False, payload=200)

    return s, ports, paths


# ======================================================================
# Additional Topologies
# ======================================================================

def build_tree_topology(sched_cls=FusionSchedulerE2E, tas_w=100,
                        tas_c=500, cqf_c=500, scale=1.0):
    """Tree topology: 7 switches, root SW1, depth 3.

            SW1
           /   \\
         SW2   SW3
        / \\   / \\
      SW4 SW5 SW6 SW7

    Directed links: parent→child and child→parent.
    Flows traverse leaf-to-leaf (max 4 hops) or leaf-to-root (2 hops).
    """
    s = model.System('tree')
    ports = {}
    edges = [(1,2),(2,1),(1,3),(3,1),
             (2,4),(4,2),(2,5),(5,2),
             (3,6),(6,3),(3,7),(7,3)]
    for i, j in edges:
        name = 'SW%d_to_SW%d' % (i, j)
        ports[(i,j)] = make_resource(name, sched_cls, tas_w, tas_c, cqf_c)
        s.bind_resource(ports[(i,j)])

    def pc(sw_list):
        return [ports[(sw_list[k], sw_list[k+1])] for k in range(len(sw_list)-1)]

    C = scale
    paths = {}
    # ST: leaf-to-leaf through root, 4 hops
    paths['ST1'] = make_flow(s, pc([4,2,1,3,6]), 'ST1', 7,
                             wcet=int(10*C), period=500, tas_aligned=True)
    paths['ST2'] = make_flow(s, pc([7,3,1,2,5]), 'ST2', 7,
                             wcet=int(12*C), period=500, tas_aligned=True)
    paths['ST3'] = make_flow(s, pc([5,2,1]), 'ST3', 7,
                             wcet=int(8*C), period=1000, tas_aligned=True)
    paths['ST4'] = make_flow(s, pc([6,3,1]), 'ST4', 7,
                             wcet=int(10*C), period=1000, tas_aligned=True)
    # CQF: leaf-to-sibling, 2 hops
    paths['CQF1'] = make_flow(s, pc([4,2,5]), 'CQF1', 5,
                              wcet=int(15*C), period=1000)
    paths['CQF2'] = make_flow(s, pc([6,3,7]), 'CQF2', 5,
                              wcet=int(12*C), period=1000)
    paths['CQF3'] = make_flow(s, pc([7,3,1]), 'CQF3', 5,
                              wcet=int(10*C), period=500)
    # ATS: leaf-to-root, 2 hops
    paths['ATS1'] = make_flow(s, pc([5,2,1]), 'ATS1', 6,
                              wcet=int(20*C), period=2000, cir=200e6, cbs=24000)
    paths['ATS2'] = make_flow(s, pc([6,3,1]), 'ATS2', 6,
                              wcet=int(15*C), period=2000, cir=150e6, cbs=18000)
    paths['ATS3'] = make_flow(s, pc([4,2,1,3,7]), 'ATS3', 6,
                              wcet=int(12*C), period=2000, cir=100e6, cbs=15000)
    # SP+E: leaf-to-leaf, 4 hops
    paths['NC_E1'] = make_flow(s, pc([5,2,1,3,7]), 'NC_E1', 3,
                               wcet=int(15*C), period=5000, tas_aligned=False)
    paths['NC_E2'] = make_flow(s, pc([7,3,1,2,4]), 'NC_E2', 3,
                               wcet=int(12*C), period=5000, tas_aligned=False)
    # SP+P: leaf-to-root, 2 hops
    paths['NC_P1'] = make_flow(s, pc([4,2,1]), 'NC_P1', 2,
                               wcet=int(15*C), period=10000,
                               tas_aligned=False, payload=300)
    paths['NC_P2'] = make_flow(s, pc([7,3,1]), 'NC_P2', 1,
                               wcet=int(10*C), period=10000,
                               tas_aligned=False, payload=200)
    paths['NC_P3'] = make_flow(s, pc([5,2,1,3,6]), 'NC_P3', 1,
                               wcet=int(10*C), period=10000,
                               tas_aligned=False, payload=200)
    return s, ports, paths


def build_ring_topology(sched_cls=FusionSchedulerE2E, tas_w=100,
                        tas_c=500, cqf_c=500, scale=1.0):
    """Ring topology: 6 switches in a ring.

        SW1 ── SW2 ── SW3
         │                │
        SW6 ── SW5 ── SW4

    Bidirectional links forming a ring.  Flows can take the shorter path.
    """
    s = model.System('ring')
    ports = {}
    ring = [(1,2),(2,3),(3,4),(4,5),(5,6),(6,1)]
    for i, j in ring:
        for a, b in [(i,j),(j,i)]:
            name = 'SW%d_to_SW%d' % (a, b)
            ports[(a,b)] = make_resource(name, sched_cls, tas_w, tas_c, cqf_c)
            s.bind_resource(ports[(a,b)])

    def pc(sw_list):
        return [ports[(sw_list[k], sw_list[k+1])] for k in range(len(sw_list)-1)]

    C = scale
    paths = {}
    # ST: across ring, 3 hops (shorter path)
    paths['ST1'] = make_flow(s, pc([1,2,3,4]), 'ST1', 7,
                             wcet=int(10*C), period=500, tas_aligned=True)
    paths['ST2'] = make_flow(s, pc([4,5,6,1]), 'ST2', 7,
                             wcet=int(12*C), period=500, tas_aligned=True)
    paths['ST3'] = make_flow(s, pc([1,2,3]), 'ST3', 7,
                             wcet=int(8*C), period=1000, tas_aligned=True)
    paths['ST4'] = make_flow(s, pc([4,5,6]), 'ST4', 7,
                             wcet=int(10*C), period=1000, tas_aligned=True)
    # CQF: adjacent, 2 hops
    paths['CQF1'] = make_flow(s, pc([1,2,3]), 'CQF1', 5,
                              wcet=int(15*C), period=1000)
    paths['CQF2'] = make_flow(s, pc([4,5,6]), 'CQF2', 5,
                              wcet=int(12*C), period=1000)
    paths['CQF3'] = make_flow(s, pc([6,1,2]), 'CQF3', 5,
                              wcet=int(10*C), period=500)
    # ATS: 2 hops
    paths['ATS1'] = make_flow(s, pc([2,3,4]), 'ATS1', 6,
                              wcet=int(20*C), period=2000, cir=200e6, cbs=24000)
    paths['ATS2'] = make_flow(s, pc([5,6,1]), 'ATS2', 6,
                              wcet=int(15*C), period=2000, cir=150e6, cbs=18000)
    paths['ATS3'] = make_flow(s, pc([3,4,5,6]), 'ATS3', 6,
                              wcet=int(12*C), period=2000, cir=100e6, cbs=15000)
    # SP+E: half ring, 3 hops
    paths['NC_E1'] = make_flow(s, pc([1,6,5,4]), 'NC_E1', 3,
                               wcet=int(15*C), period=5000, tas_aligned=False)
    paths['NC_E2'] = make_flow(s, pc([4,3,2,1]), 'NC_E2', 3,
                               wcet=int(12*C), period=5000, tas_aligned=False)
    # SP+P: 2 hops
    paths['NC_P1'] = make_flow(s, pc([3,2,1]), 'NC_P1', 2,
                               wcet=int(15*C), period=10000,
                               tas_aligned=False, payload=300)
    paths['NC_P2'] = make_flow(s, pc([6,5,4]), 'NC_P2', 1,
                               wcet=int(10*C), period=10000,
                               tas_aligned=False, payload=200)
    paths['NC_P3'] = make_flow(s, pc([1,6,5,4]), 'NC_P3', 1,
                               wcet=int(10*C), period=10000,
                               tas_aligned=False, payload=200)
    return s, ports, paths


def build_mesh_topology(sched_cls=FusionSchedulerE2E, tas_w=100,
                        tas_c=500, cqf_c=500, scale=1.0):
    """Mesh (grid) topology: 2x3 grid of 6 switches.

        SW1 ── SW2 ── SW3
         │      │      │
        SW4 ── SW5 ── SW6

    Bidirectional horizontal and vertical links.
    """
    s = model.System('mesh')
    ports = {}
    edges = [(1,2),(2,3),(4,5),(5,6),  # horizontal
             (1,4),(2,5),(3,6)]         # vertical
    for i, j in edges:
        for a, b in [(i,j),(j,i)]:
            name = 'SW%d_to_SW%d' % (a, b)
            ports[(a,b)] = make_resource(name, sched_cls, tas_w, tas_c, cqf_c)
            s.bind_resource(ports[(a,b)])

    def pc(sw_list):
        return [ports[(sw_list[k], sw_list[k+1])] for k in range(len(sw_list)-1)]

    C = scale
    paths = {}
    # ST: corner-to-corner, 4 hops
    paths['ST1'] = make_flow(s, pc([1,2,3,6]), 'ST1', 7,
                             wcet=int(10*C), period=500, tas_aligned=True)
    paths['ST2'] = make_flow(s, pc([6,5,4,1]), 'ST2', 7,
                             wcet=int(12*C), period=500, tas_aligned=True)
    paths['ST3'] = make_flow(s, pc([1,2,3]), 'ST3', 7,
                             wcet=int(8*C), period=1000, tas_aligned=True)
    paths['ST4'] = make_flow(s, pc([4,5,6]), 'ST4', 7,
                             wcet=int(10*C), period=1000, tas_aligned=True)
    # CQF: L-shaped, 2 hops
    paths['CQF1'] = make_flow(s, pc([1,4,5]), 'CQF1', 5,
                              wcet=int(15*C), period=1000)
    paths['CQF2'] = make_flow(s, pc([3,2,5]), 'CQF2', 5,
                              wcet=int(12*C), period=1000)
    paths['CQF3'] = make_flow(s, pc([6,5,4]), 'CQF3', 5,
                              wcet=int(10*C), period=500)
    # ATS: vertical + horizontal, 3 hops
    paths['ATS1'] = make_flow(s, pc([1,2,5,6]), 'ATS1', 6,
                              wcet=int(20*C), period=2000, cir=200e6, cbs=24000)
    paths['ATS2'] = make_flow(s, pc([4,5,2,3]), 'ATS2', 6,
                              wcet=int(15*C), period=2000, cir=150e6, cbs=18000)
    paths['ATS3'] = make_flow(s, pc([1,4,5,6]), 'ATS3', 6,
                              wcet=int(12*C), period=2000, cir=100e6, cbs=15000)
    # SP+E: diagonal, 3 hops
    paths['NC_E1'] = make_flow(s, pc([4,1,2,3]), 'NC_E1', 3,
                               wcet=int(15*C), period=5000, tas_aligned=False)
    paths['NC_E2'] = make_flow(s, pc([6,5,4,1]), 'NC_E2', 3,
                               wcet=int(12*C), period=5000, tas_aligned=False)
    # SP+P: short, 2 hops
    paths['NC_P1'] = make_flow(s, pc([6,3,2]), 'NC_P1', 2,
                               wcet=int(15*C), period=10000,
                               tas_aligned=False, payload=300)
    paths['NC_P2'] = make_flow(s, pc([4,5,6]), 'NC_P2', 1,
                               wcet=int(10*C), period=10000,
                               tas_aligned=False, payload=200)
    paths['NC_P3'] = make_flow(s, pc([1,2,3,6]), 'NC_P3', 1,
                               wcet=int(10*C), period=10000,
                               tas_aligned=False, payload=200)
    return s, ports, paths


def e9_multi_topology():
    """E9: Compare E2E improvement across four topologies and three loads."""
    import json
    print('=' * 70)
    print('E9: Multi-Topology E2E Comparison (multi-load)')
    print('=' * 70)

    topos = [
        ('Linear', build_automotive_topology),
        ('Tree',   build_tree_topology),
        ('Ring',   build_ring_topology),
        ('Mesh',   build_mesh_topology),
    ]
    loads = [('Light', 0.5), ('Medium', 1.0), ('Heavy', 1.5)]

    results = []  # list of dicts for plotting

    for topo_name, build_fn in topos:
        for load_label, scale in loads:
            s, _, paths = build_fn(FusionSchedulerE2E, scale=scale)
            tr = analysis.analyze_system(s)
            s_b, _, paths_b = build_fn(FusionScheduler, scale=scale)
            tr_b = analysis.analyze_system(s_b)

            for name in sorted(paths.keys()):
                p, tasks = paths[name]
                p_b, tasks_b = paths_b[name]
                _, e2e = path_analysis.end_to_end_latency(p, tr)
                sum_wcrt = sum(tr_b[t].wcrt for t in tasks_b)
                nhops = len(tasks)
                improv = (sum_wcrt - e2e) / sum_wcrt * 100 if sum_wcrt > 0 else 0
                cls = ('ST' if name.startswith('ST') else
                       'CQF' if name.startswith('CQF') else
                       'ATS' if name.startswith('ATS') else
                       'SP+E' if name.startswith('NC_E') else 'SP+P')
                row = dict(topo=topo_name, load=load_label, flow=name,
                           cls=cls, hops=nhops, sum_wcrt=sum_wcrt,
                           e2e=e2e, improv=improv)
                results.append(row)
                print('%-8s %-6s %-8s %-6s %2d %8.1f %8.1f %6.1f%%' % (
                    topo_name, load_label, name, cls, nhops,
                    sum_wcrt, e2e, improv))

    # Save for plotting
    out = os.path.join(os.path.dirname(__file__), 'e9_multi_topo.json')
    with open(out, 'w') as f:
        json.dump(results, f, indent=2)
    print(f'\nSaved {len(results)} rows to {out}')


def e1_automotive_baseline():
    """E1: Run baseline analysis on automotive topology."""
    print('=' * 70)
    print('E1: Automotive TSN Topology — Baseline Analysis')
    print('=' * 70)

    s, sw, paths = build_automotive_topology()
    tr = analysis.analyze_system(s)

    print('\n%-8s %-6s %4s %8s %8s %8s' % (
        'Flow', 'Type', 'Hops', 'WCRT_last', 'E2E', 'sum_WCRT'))
    print('-' * 50)

    for name in sorted(paths.keys()):
        p, tasks = paths[name]
        lmin, lmax = path_analysis.end_to_end_latency(p, tr)
        sum_wcrt = sum(tr[t].wcrt for t in tasks)
        nhops = len(tasks)
        wcrt_last = tr[tasks[-1]].wcrt
        mech = 'ST' if name.startswith('ST') else (
            'CQF' if name.startswith('CQF') else (
            'ATS' if name.startswith('ATS') else (
            'NC_E' if name.startswith('NC_E') else 'NC_P')))
        print('%-8s %-6s %4d %8.1f %8.1f %8.1f' % (
            name, mech, nhops, wcrt_last, lmax, sum_wcrt))

    print()
    return s, sw, paths, tr


# ======================================================================
# E2: E2E Improvement vs Hop Count
# ======================================================================

def e2_e2e_vs_hops():
    """E2: Measure E2E improvement for 2-7 hop paths."""
    print('=' * 70)
    print('E2: E2E Improvement vs Hop Count')
    print('=' * 70)

    flow_types = {
        'ST':    dict(prio=7, wcet=10, period=500, tas_aligned=True),
        'CQF_E': dict(prio=5, wcet=8, period=1000, tas_aligned=None),
        'NC_E':  dict(prio=3, wcet=15, period=5000, tas_aligned=False),
        'NC_P':  dict(prio=2, wcet=20, period=10000, tas_aligned=False,
                      payload=400),
    }

    print('\n%-8s' % 'Hops', end='')
    for ft in flow_types:
        print('  %8s_sum %8s_e2e %7s_%%' % (ft, ft, ft), end='')
    print()
    print('-' * 130)

    for nhops in range(2, 8):
        print('%-8d' % nhops, end='')
        for ft_name, cfg in flow_types.items():
            results = {}
            for tag, sched_cls in [('basic', FusionScheduler),
                                   ('e2e', FusionSchedulerE2E)]:
                s = model.System()
                tasks = []
                for i in range(nhops):
                    r = make_resource('R%d' % i, sched_cls)
                    s.bind_resource(r)
                    add_background(r, 'bg%d' % i)
                    kw = dict(wcet=cfg['wcet'], bcet=cfg['wcet'],
                              scheduling_parameter=cfg['prio'])
                    if 'payload' in cfg:
                        kw['payload'] = cfg['payload']
                    if cfg['prio'] == 6:
                        kw['CIR'] = 100e6; kw['CBS'] = 12000
                    t = model.Task('%s_%d' % (ft_name, i), **kw)
                    if i == 0:
                        t.in_event_model = model.PJdEventModel(
                            P=cfg['period'], J=0)
                    r.bind_task(t)
                    if i > 0:
                        tasks[-1].link_dependent_task(t)
                    tasks.append(t)
                p = model.Path('path', tasks)
                if cfg['tas_aligned'] is not None:
                    p.tas_aligned = cfg['tas_aligned']
                s.bind_path(p)
                tr = analysis.analyze_system(s)
                _, lmax = path_analysis.end_to_end_latency(p, tr)
                results[tag] = lmax

            s_wcrt = results['basic']
            e2e = results['e2e']
            improv = (s_wcrt - e2e) / s_wcrt * 100 if s_wcrt > 0 else 0
            print('  %12.1f %8.1f %6.1f%%' % (s_wcrt, e2e, improv), end='')
        print()

    print()


# ======================================================================
# E2b: Aligned vs Non-aligned vs No-correction (ST focus)
# ======================================================================

def e2b_alignment_comparison():
    """E2b: Three-way comparison for ST flows: no correction, non-aligned, aligned."""
    print('=' * 70)
    print('E2b: ST Alignment Comparison (no-corr / non-aligned / aligned)')
    print('=' * 70)

    print('\n%-6s %10s %10s %10s %8s %8s' % (
        'Hops', 'sum_WCRT', 'non-align', 'aligned', 'impr_na%', 'impr_al%'))
    print('-' * 62)

    for nhops in range(2, 8):
        results = {}
        for tag, sched_cls, aligned in [
            ('sum',       FusionScheduler,    None),
            ('non-align', FusionSchedulerE2E, False),
            ('aligned',   FusionSchedulerE2E, True),
        ]:
            s = model.System()
            tasks = []
            for i in range(nhops):
                r = make_resource('R%d' % i, sched_cls)
                s.bind_resource(r)
                add_background(r, 'bg%d' % i)
                t = model.Task('ST_%d' % i, wcet=10, bcet=10,
                               scheduling_parameter=7)
                if i == 0:
                    t.in_event_model = model.PJdEventModel(P=500, J=0)
                r.bind_task(t)
                if i > 0:
                    tasks[-1].link_dependent_task(t)
                tasks.append(t)
            p = model.Path('path', tasks)
            if aligned is not None:
                p.tas_aligned = aligned
            s.bind_path(p)
            tr = analysis.analyze_system(s)
            _, lmax = path_analysis.end_to_end_latency(p, tr)
            results[tag] = lmax

        s_w = results['sum']
        na = results['non-align']
        al = results['aligned']
        imp_na = (s_w - na) / s_w * 100 if s_w > 0 else 0
        imp_al = (s_w - al) / s_w * 100 if s_w > 0 else 0
        print('%-6d %10.1f %10.1f %10.1f %7.1f%% %7.1f%%' % (
            nhops, s_w, na, al, imp_na, imp_al))

    print()


# ======================================================================
# E8: ATS Analysis Fidelity — group eligible time & token-bucket effect
# ======================================================================

def e8_ats_fidelity():
    """E8: Show impact of group eligible time and token-bucket limiting.

    Two sub-experiments:
    (a) Group eligible time: 3 same-port ATS flows vs 3 different-port flows.
        Same-port flows share group ET → higher SCH blocking.
        Different-port flows have independent ET → lower SCH but higher SPB.
    (b) Token-bucket limited SPB: diff-port ATS interferers are counted by
        min(arrival_curve, token_bucket). With tight CIR, token limit reduces
        the interferer count and thus the WCRT.
    """
    print('=' * 70)
    print('E8: ATS Analysis Fidelity')
    print('=' * 70)

    # --- (a) Group eligible time effect ---
    print('\n(a) Group eligible time effect on same-port ATS flows')
    print('    3 same-port flows + 2 diff-port flows, with HP express interferers')
    print()

    flow_names_a = ['ATS_a1', 'ATS_a2', 'ATS_a3', 'ATS_b1', 'ATS_b2']
    print('%-25s' % 'Config', end='')
    for fn in flow_names_a:
        print(' %8s' % fn, end='')
    print()
    print('-' * 70)

    for label, use_group in [('With group ET', True), ('Without group ET', False)]:
        s = model.System()
        r = model.TSN_Resource('R', scheduler=FusionSchedulerE2E(),
                               linkspeed=1e9)
        r.priority_mechanism_map = {7: None, 6: 'ATS'}
        r.is_express_by_priority = {7: True, 6: True}
        r.tas_cycle_time = 0
        r.tas_window_time_by_priority = {}
        r.cqf_cycle_time_by_pair = {}
        s.bind_resource(r)

        for i in range(3):
            t_hp = model.Task('HP%d' % i, wcet=12, bcet=12,
                              scheduling_parameter=7)
            t_hp.in_event_model = model.PJdEventModel(P=400, J=0)
            r.bind_task(t_hp)

        flows = {}
        for i, (nm, cir, per) in enumerate([
            ('ATS_a1', 100e6, 500),
            ('ATS_a2', 80e6, 600),
            ('ATS_a3', 60e6, 800),
        ]):
            port = 'A' if use_group else ('A%d' % i)
            t = model.Task(nm, wcet=12, bcet=12, scheduling_parameter=6,
                           CIR=cir, CBS=12000, src_port=port)
            t.in_event_model = model.PJdEventModel(P=per, J=0)
            r.bind_task(t)
            flows[nm] = t

        for i, (nm, cir, per) in enumerate([
            ('ATS_b1', 120e6, 400),
            ('ATS_b2', 50e6, 1000),
        ]):
            port = 'B' if use_group else ('B%d' % i)
            t = model.Task(nm, wcet=10, bcet=10, scheduling_parameter=6,
                           CIR=cir, CBS=10000, src_port=port)
            t.in_event_model = model.PJdEventModel(P=per, J=0)
            r.bind_task(t)
            flows[nm] = t

        tr = analysis.analyze_system(s)
        print('%-25s' % label, end='')
        for fn in flow_names_a:
            print(' %8.1f' % tr[flows[fn]].wcrt, end='')
        print()

    # --- (b) Token-bucket limited SPB effect ---
    print('\n(b) Token-bucket limited SPB: diff-port ATS interferer counting')
    print('    1 flow under analysis + 3 diff-port bursty ATS interferers (P=50, J=40)')
    print('    Comparing actual CIR (token-limited) vs unlimited (arrival-curve only)')
    print()

    print('%-20s %12s %12s %8s' % ('Interferer CIR', 'Token-lim', 'Arrival-only', 'Diff'))
    print('-' * 55)

    for cir_label, cir_val in [('25 Mbps', 25e6),
                                ('100 Mbps', 100e6),
                                ('200 Mbps', 200e6),
                                ('500 Mbps', 500e6)]:
        results = {}
        for tag, effective_cir in [('token', cir_val), ('arrival', 1e12)]:
            s = model.System()
            r = model.TSN_Resource('R', scheduler=FusionSchedulerE2E(),
                                   linkspeed=1e9)
            r.priority_mechanism_map = {6: 'ATS'}
            r.is_express_by_priority = {6: True}
            r.tas_cycle_time = 0
            r.tas_window_time_by_priority = {}
            r.cqf_cycle_time_by_pair = {}
            s.bind_resource(r)

            t_ua = model.Task('f_ua', wcet=12, bcet=12, scheduling_parameter=6,
                              CIR=200e6, CBS=12000, src_port='X')
            t_ua.in_event_model = model.PJdEventModel(P=2000, J=0)
            r.bind_task(t_ua)

            for i in range(3):
                t = model.Task('intf%d' % i, wcet=12, bcet=12,
                               scheduling_parameter=6,
                               CIR=effective_cir, CBS=12000,
                               src_port='P%d' % i)
                t.in_event_model = model.PJdEventModel(P=50, J=40)
                r.bind_task(t)

            tr = analysis.analyze_system(s)
            results[tag] = tr[t_ua].wcrt

        diff = results['arrival'] - results['token']
        print('%-20s %12.1f %12.1f %8.1f' % (
            cir_label, results['token'], results['arrival'], diff))

    print()


# ======================================================================
# E3: Cross-Interference Necessity
# ======================================================================

def e3_cross_interference():
    """E3: Compare fusion analysis vs ignoring TAS gate blocking.

    Shows that ignoring cross-mechanism interference is UNSAFE.
    """
    print('=' * 70)
    print('E3: Cross-Interference Necessity')
    print('=' * 70)

    # Build system with fusion scheduler (correct)
    s_fusion, _, paths_fusion = build_automotive_topology(FusionSchedulerE2E)
    tr_fusion = analysis.analyze_system(s_fusion)

    # Build same system WITHOUT TAS (no gate blocking on non-ST flows)
    # Simulate "ignoring TAS" by setting TAS window to 0
    s_notas, sw_notas, paths_notas = build_automotive_topology(FusionSchedulerE2E,
                                                                tas_w=0)
    # But keep ST flows — they just get window=0 which means no gate blocking
    # Actually, to properly simulate "ignoring cross-interference",
    # we remove TAS from the mechanism map for the no-TAS analysis
    for r in s_notas.resources:
        # Set TAS window to 0 — ST flows still exist but no gate blocking
        r.tas_window_time_by_priority = {7: 0}

    try:
        tr_notas = analysis.analyze_system(s_notas)
    except Exception:
        tr_notas = None

    print('\n%-8s %-6s %10s %10s %10s %6s' % (
        'Flow', 'Type', 'Fusion', 'No_TAS_GB', 'Diff', 'Safe?'))
    print('-' * 60)

    for name in sorted(paths_fusion.keys()):
        if name.startswith('ST'):
            continue  # ST flows are TAS-only, skip
        p_f, tasks_f = paths_fusion[name]
        p_n, tasks_n = paths_notas[name]
        _, lmax_f = path_analysis.end_to_end_latency(p_f, tr_fusion)
        if tr_notas:
            _, lmax_n = path_analysis.end_to_end_latency(p_n, tr_notas)
        else:
            lmax_n = float('nan')
        diff = lmax_f - lmax_n
        safe = 'YES' if lmax_n >= lmax_f else 'NO (unsafe!)'
        print('%-8s %-6s %10.1f %10.1f %10.1f %s' % (
            name, 'CQF' if 'CQF' in name else ('ATS' if 'ATS' in name else 'NC'),
            lmax_f, lmax_n, diff, safe))

    print()


# ======================================================================
# E4: Closed-Loop Configuration vs Traffic Load
# ======================================================================

def e4_config_vs_load():
    """E4: Run closed-loop configuration under light/medium/heavy loads."""
    print('=' * 70)
    print('E4: Closed-Loop Configuration vs Traffic Load')
    print('=' * 70)

    loads = [
        ('Light',  0.5),
        ('Medium', 1.0),
        ('Heavy',  1.5),
        ('Extreme', 2.0),
    ]

    # Deadlines (generous enough for light, tight for heavy)
    deadline_map = {
        'ST1': 600, 'ST2': 600, 'ST3': 400, 'ST4': 400,
        'CQF1': 2500, 'CQF2': 2500, 'CQF3': 1500,
        'ATS1': 3000, 'ATS2': 3000, 'ATS3': 3000,
        'NC_E1': 8000, 'NC_E2': 8000,
        'NC_P1': 5000, 'NC_P2': 5000, 'NC_P3': 8000,
    }

    print('\n%-8s %8s %6s %8s %8s %8s' % (
        'Load', 'Scale', 'Feas?', 'Iters', 'TAS_occ', 'Max_slack'))
    print('-' * 55)

    for label, scale in loads:
        s, sw, paths = build_automotive_topology(
            FusionSchedulerE2E, tas_w=30, tas_c=500, cqf_c=500, scale=scale)

        deadlines = {}
        for name, (p, tasks) in paths.items():
            if name in deadline_map:
                deadlines[p] = deadline_map[name]

        opt = FusionConfigOptimizer(s, deadlines, bw_min=50, tas_step=5,
                                    cqf_candidates=[500, 250, 125])
        result = opt.optimize()

        # Compute TAS occupancy
        tas_occ = 0
        n_res = 0
        for rn, params in result.params.items():
            tc = params.get('tas_cycle_time', 500)
            tw_sum = sum(params.get('tas_window_time_by_priority', {}).values())
            if tc > 0:
                tas_occ += tw_sum / tc
                n_res += 1
        avg_occ = tas_occ / n_res * 100 if n_res > 0 else 0

        # Max slack (min over all paths)
        max_slack = float('inf')
        for pname, e2e_val in result.e2e.items():
            for p, dl in deadlines.items():
                if p.name == pname:
                    slack = dl - e2e_val
                    max_slack = min(max_slack, slack)
        if max_slack == float('inf'):
            max_slack = 0

        print('%-8s %8.1f %6s %8d %7.1f%% %8.1f' % (
            label, scale,
            'Yes' if result.feasible else 'No',
            result.iterations, avg_occ, max_slack))

    print()


def _generic_deadlines(paths):
    """Assign deadlines based on flow class."""
    dl_by_class = {'ST': 600, 'CQF': 2500, 'ATS': 3000,
                   'NC_E': 8000, 'NC_P': 5000}
    deadlines = {}
    for name, (p, tasks) in paths.items():
        for prefix, dl in dl_by_class.items():
            if name.startswith(prefix):
                deadlines[p] = dl
                break
    return deadlines


def e10_config_multi_topo():
    """E10: Closed-loop configuration across four topologies."""
    print('=' * 70)
    print('E10: Multi-Topology Closed-Loop Configuration')
    print('=' * 70)

    topos = [
        ('Linear', build_automotive_topology),
        ('Tree',   build_tree_topology),
        ('Ring',   build_ring_topology),
        ('Mesh',   build_mesh_topology),
    ]
    loads = [('Light', 0.5), ('Medium', 1.0), ('Heavy', 1.5), ('Extreme', 2.0)]

    print('\n%-10s %-8s %6s %6s %8s %8s' % (
        'Topology', 'Load', 'Feas?', 'Iters', 'TAS_occ', 'Min_slk'))
    print('-' * 55)

    for topo_name, build_fn in topos:
        for label, scale in loads:
            s, _, paths = build_fn(
                FusionSchedulerE2E, tas_w=30, tas_c=500, cqf_c=500, scale=scale)
            deadlines = _generic_deadlines(paths)

            opt = FusionConfigOptimizer(s, deadlines, bw_min=50, tas_step=5,
                                        cqf_candidates=[500, 250, 125])
            result = opt.optimize()

            tas_occ = 0
            n_res = 0
            for rn, params in result.params.items():
                tc = params.get('tas_cycle_time', 500)
                tw_sum = sum(params.get('tas_window_time_by_priority', {}).values())
                if tc > 0:
                    tas_occ += tw_sum / tc
                    n_res += 1
            avg_occ = tas_occ / n_res * 100 if n_res > 0 else 0

            min_slack = float('inf')
            for pname, e2e_val in result.e2e.items():
                for p, dl in deadlines.items():
                    if p.name == pname:
                        min_slack = min(min_slack, dl - e2e_val)
            if min_slack == float('inf'):
                min_slack = 0

            print('%-10s %-8s %6s %6d %7.1f%% %8.1f' % (
                topo_name if label == 'Light' else '',
                label,
                'Yes' if result.feasible else 'No',
                result.iterations, avg_occ, min_slack))
        print()

    print()
# ======================================================================
# E5: Configuration Iteration Curves
# ======================================================================

def e5_iteration_curves():
    """E5: Record parameter + E2E at each iteration for plotting."""
    print('=' * 70)
    print('E5: Configuration Iteration Curves (Medium Load)')
    print('=' * 70)

    s, sw, paths = build_automotive_topology(
        FusionSchedulerE2E, tas_w=30, tas_c=500, cqf_c=500, scale=1.0)

    deadline_map = {
        'ST1': 600, 'ST2': 600, 'ST3': 400, 'ST4': 400,
        'CQF1': 2500, 'CQF2': 2500, 'CQF3': 1500,
        'ATS1': 3000, 'ATS2': 3000, 'ATS3': 3000,
        'NC_E1': 8000, 'NC_E2': 8000,
        'NC_P1': 5000, 'NC_P2': 5000, 'NC_P3': 8000,
    }
    deadlines = {}
    for name, (p, tasks) in paths.items():
        if name in deadline_map:
            deadlines[p] = deadline_map[name]

    opt = FusionConfigOptimizer(s, deadlines, bw_min=50, tas_step=5,
                                cqf_candidates=[500, 250, 125])
    result = opt.optimize()

    print('\nFeasible: %s, Iterations: %d' % (result.feasible, result.iterations))

    # Print iteration history (for plotting)
    print('\n%-5s' % 'Iter', end='')
    # Pick representative flows
    rep_flows = ['path_ST1', 'path_CQF1', 'path_ATS1', 'path_NC_E1']
    for f in rep_flows:
        print(' %12s' % f.replace('path_', ''), end='')
    print()
    print('-' * 60)

    for i, h in enumerate(result.history):
        print('%-5d' % (i + 1), end='')
        for f in rep_flows:
            val = h.get(f, float('nan'))
            print(' %12.1f' % val, end='')
        print()

    # Print final parameters
    print('\nFinal parameters:')
    for rn in sorted(result.params.keys()):
        p = result.params[rn]
        print('  %s: TAS_w=%s TAS_c=%s CQF=%s' % (
            rn, p['tas_window_time_by_priority'],
            p['tas_cycle_time'], p['cqf_cycle_time_by_pair']))

    print()


# ======================================================================
# E6: Single-hop WCRT breakdown (per blocking term)
# ======================================================================

def e6_wcrt_breakdown():
    """E6: Show WCRT breakdown by blocking term for each flow type."""
    print('=' * 70)
    print('E6: Single-Hop WCRT Breakdown')
    print('=' * 70)

    s = model.System()
    r = make_resource('SW1', FusionSchedulerE2E)
    s.bind_resource(r)

    # Create one flow of each type
    flows = {}
    # ST
    t = model.Task('ST', wcet=10, bcet=10, scheduling_parameter=7)
    t.in_event_model = model.PJdEventModel(P=500, J=0)
    r.bind_task(t); flows['ST'] = t
    # ST interferer
    t2 = model.Task('ST_i', wcet=8, bcet=8, scheduling_parameter=7)
    t2.in_event_model = model.PJdEventModel(P=500, J=0)
    r.bind_task(t2)
    # ATS+E
    t = model.Task('ATS_E', wcet=12, bcet=12, scheduling_parameter=6,
                    CIR=100e6, CBS=12000, src_port='A')
    t.in_event_model = model.PJdEventModel(P=500, J=0)
    r.bind_task(t); flows['ATS+E'] = t
    # C+E
    t = model.Task('CQF_E', wcet=8, bcet=8, scheduling_parameter=5)
    t.in_event_model = model.PJdEventModel(P=500, J=0)
    r.bind_task(t); flows['C+E'] = t
    # NC+E
    t = model.Task('NC_E', wcet=15, bcet=15, scheduling_parameter=3)
    t.in_event_model = model.PJdEventModel(P=2000, J=0)
    r.bind_task(t); flows['NC+E'] = t
    # NC+P
    t = model.Task('NC_P', wcet=20, bcet=20, scheduling_parameter=2,
                    payload=400)
    t.in_event_model = model.PJdEventModel(P=5000, J=0)
    r.bind_task(t); flows['NC+P'] = t

    tr = analysis.analyze_system(s)

    print('\n%-8s %8s' % ('Flow', 'WCRT'))
    print('-' * 20)
    for name, t in flows.items():
        print('%-8s %8.1f' % (name, tr[t].wcrt))
    print()


# ======================================================================
# E7: Scalability — increasing number of flows
# ======================================================================

def e7_scalability():
    """E7: Analysis time vs number of flows on a single resource."""
    import time

    print('=' * 70)
    print('E7: Scalability — Analysis Time vs Flow Count')
    print('=' * 70)

    print('\n%-10s %8s %8s' % ('Flows', 'Time(ms)', 'Max_WCRT'))
    print('-' * 30)

    for nflows in [4, 8, 16, 32, 64]:
        s = model.System()
        r = make_resource('R', FusionSchedulerE2E)
        s.bind_resource(r)

        for i in range(nflows):
            prio = 7 if i % 4 == 0 else (5 if i % 4 == 1 else (
                3 if i % 4 == 2 else 2))
            kw = dict(wcet=10, bcet=10, scheduling_parameter=prio)
            if prio == 6:
                kw['CIR'] = 100e6; kw['CBS'] = 12000
            if prio == 2:
                kw['payload'] = 300
            t = model.Task('f%d' % i, **kw)
            t.in_event_model = model.PJdEventModel(P=1000, J=0)
            r.bind_task(t)

        t0 = time.time()
        tr = analysis.analyze_system(s)
        elapsed = (time.time() - t0) * 1000

        max_wcrt = max(tr[t].wcrt for t in r.tasks
                       if not model.ForwardingTask.is_forwarding_task(t))
        print('%-10d %8.1f %8.1f' % (nflows, elapsed, max_wcrt))

    print()


# ======================================================================
# Main
# ======================================================================

if __name__ == '__main__':
    e1_automotive_baseline()
    e2_e2e_vs_hops()
    e2b_alignment_comparison()
    e8_ats_fidelity()
    e9_multi_topology()
    e3_cross_interference()
    e6_wcrt_breakdown()
    e7_scalability()
    e4_config_vs_load()
    e10_config_multi_topo()
    e5_iteration_curves()
    print('=' * 70)
    print('All experiments completed.')
    print('=' * 70)
