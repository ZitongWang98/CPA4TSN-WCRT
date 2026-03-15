"""
ATS Scheduler test.

Verifies ATSScheduler against a simple 4-flow scenario
(similar to the old ATSUScheduler test from pycpa-ATSwithQbu).

All flows are ATS, express, single resource.
  T11: prio=7, wcet=1.936us, CIR=19Mbps,  CBS=2000bits, P=100, J=10
  T12: prio=5, wcet=3.536us, CIR=35Mbps,  CBS=4000bits, P=100, J=10
  T13: prio=3, wcet=6.736us, CIR=67Mbps,  CBS=7600bits, P=100, J=10
  T14: prio=1, wcet=12.096us,CIR=25Mbps, CBS=13600bits, P=500, J=50
"""
import sys
sys.path.insert(0, '..')

from pycpa import model
from pycpa import analysis
from pycpa import schedulers_ats as ats
from pycpa import options


def test_ats_basic():
    s = model.System("ATS_test")

    r = model.TSN_Resource("R1", ats.ATSScheduler(),
        priority_mechanism_map={
            7: 'ATS',
            5: 'ATS',
            3: 'ATS',
            1: 'ATS',
        })
    s.bind_resource(r)

    # All from same src_port=0
    t11 = r.bind_task(model.Task("T11", wcet=1.936, bcet=1.936,
        scheduling_parameter=7, src_port=0,
        CIR=19e6, CBS=250*8))
    t12 = r.bind_task(model.Task("T12", wcet=3.536, bcet=3.536,
        scheduling_parameter=5, src_port=0,
        CIR=35e6, CBS=500*8))
    t13 = r.bind_task(model.Task("T13", wcet=6.736, bcet=6.736,
        scheduling_parameter=3, src_port=0,
        CIR=67e6, CBS=950*8))
    t14 = r.bind_task(model.Task("T14", wcet=12.096, bcet=12.096,
        scheduling_parameter=1, src_port=0,
        CIR=25e6, CBS=1700*8))

    t11.in_event_model = model.PJdEventModel(P=100, J=10, dmin=90)
    t12.in_event_model = model.PJdEventModel(P=100, J=10, dmin=90)
    t13.in_event_model = model.PJdEventModel(P=100, J=10, dmin=90)
    t14.in_event_model = model.PJdEventModel(P=500, J=50, dmin=450)

    print("Performing analysis...")
    task_results = analysis.analyze_system(s)

    print("\nResults:")
    for t in [t11, t12, t13, t14]:
        r = task_results[t]
        print(f"  {t.name}: WCRT = {r.wcrt:.3f} us")
        print(f"    details: {r.b_wcrt_str()}")

    # Sanity checks
    # 1. All WCRTs should be positive
    for t in [t11, t12, t13, t14]:
        assert task_results[t].wcrt > 0, f"{t.name} WCRT should be positive"

    # 2. Higher priority may NOT have lower WCRT in ATS
    #    (eT_block depends on per-flow CIR/CBS, not priority)

    # 3. WCRT should be >= wcet
    for t in [t11, t12, t13, t14]:
        assert task_results[t].wcrt >= t.wcet, \
            f"{t.name} WCRT ({task_results[t].wcrt}) < wcet ({t.wcet})"

    print("\nTest PASSED")


def test_ats_with_nats():
    """Test mixed ATS + NATS flows on same resource."""
    s = model.System("ATS_NATS_test")

    r = model.TSN_Resource("R1", ats.ATSScheduler(),
        priority_mechanism_map={
            6: 'ATS',
            4: None,   # NATS
            2: None,   # NATS
        })
    s.bind_resource(r)

    # ATS flow (prio 6)
    t_ats = r.bind_task(model.Task("ATS_flow", wcet=2.0, bcet=2.0,
        scheduling_parameter=6, src_port=0,
        CIR=10e6, CBS=2000))
    t_ats.in_event_model = model.PJdEventModel(P=200, J=0)

    # NATS flow (prio 4, lower than ATS)
    t_nats_lp = r.bind_task(model.Task("NATS_LP", wcet=5.0, bcet=5.0,
        scheduling_parameter=4))
    t_nats_lp.in_event_model = model.PJdEventModel(P=200, J=0)

    # NATS flow (prio 2, lowest)
    t_nats_low = r.bind_task(model.Task("NATS_LOW", wcet=8.0, bcet=8.0,
        scheduling_parameter=2))
    t_nats_low.in_event_model = model.PJdEventModel(P=500, J=0)

    print("\nPerforming mixed ATS+NATS analysis...")
    task_results = analysis.analyze_system(s)

    print("\nResults:")
    for t in [t_ats, t_nats_lp, t_nats_low]:
        r = task_results[t]
        print(f"  {t.name} (prio={t.scheduling_parameter}): WCRT = {r.wcrt:.3f} us")
        print(f"    details: {r.b_wcrt_str()}")

    # ATS flow (highest prio): only LPB possible
    # NATS_LP: HPB from ATS flow (token-constrained)
    # NATS_LOW: HPB from both ATS and NATS_LP

    for t in [t_ats, t_nats_lp, t_nats_low]:
        assert task_results[t].wcrt >= t.wcet
        assert task_results[t].wcrt > 0

    print("\nMixed test PASSED")


if __name__ == "__main__":
    options.init_pycpa()
    test_ats_basic()
    test_ats_with_nats()
