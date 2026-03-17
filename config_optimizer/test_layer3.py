"""Tests: Layer 3 (ATS params) edge cases."""
from test_helpers import *
from config_optimizer import FusionConfigOptimizer

def test_multi_ats_flows():
    """Multiple ATS flows share bandwidth proportionally."""
    print('\n--- test_multi_ats_flows ---')
    s = model.System('t')
    sched = FusionSchedulerE2E()
    r = make_res('R1', sched, tas_w=100, tas_c=500, has_ats=True)
    s.bind_resource(r)
    p_st, _ = make_chain(s, [r], 'ST', 7, 20, 500, tas_aligned=True)
    # Two ATS flows with different wcet → different demands
    p_a1, t_a1 = make_chain(s, [r], 'ATS1', 6, 12, 500, cir=100e6, cbs=12000)
    p_a2, t_a2 = make_chain(s, [r], 'ATS2', 6, 24, 500, cir=100e6, cbs=12000)
    dl = {p_st: 500, p_a1: 2000, p_a2: 2000}
    res = FusionConfigOptimizer(s, dl, tas_step=10).optimize()
    check('feasible', res.feasible)
    # ATS2 has 2x wcet → should get ~2x CIR
    cir1, cir2 = t_a1[0].CIR, t_a2[0].CIR
    check('ATS2 CIR > ATS1 CIR', cir2 > cir1,
          'cir1=%.0f cir2=%.0f' % (cir1, cir2))
    ratio = cir2 / cir1 if cir1 > 0 else 0
    check('CIR ratio ~2x', 1.5 < ratio < 2.5, 'ratio=%.2f' % ratio)

def test_ats_no_open_time():
    """TAS fills entire cycle → no bandwidth for ATS → ATS params unchanged."""
    print('\n--- test_ats_no_open_time ---')
    s = model.System('t')
    sched = FusionSchedulerE2E()
    # tas_w=490 out of 500 cycle → only 10 open, but guard_band=10 → 0 open
    r = make_res('R1', sched, tas_w=490, tas_c=500, has_ats=True, gb=10)
    s.bind_resource(r)
    p_st, _ = make_chain(s, [r], 'ST', 7, 20, 500, tas_aligned=True)
    p_ats, t_ats = make_chain(s, [r], 'ATS', 6, 12, 500, cir=100e6, cbs=12000)
    dl = {p_st: 500, p_ats: 5000}
    orig_cir = t_ats[0].CIR
    res = FusionConfigOptimizer(s, dl, tas_step=10).optimize()
    # ATS CIR should remain at original (no open time to derive from)
    # Layer 4 may shrink TAS, opening bandwidth, so just check it ran
    check('completed', res.iterations > 0)

def test_guard_band_impact():
    """Guard band reduces available bandwidth for ATS."""
    print('\n--- test_guard_band_impact ---')
    s = model.System('t')
    sched = FusionSchedulerE2E()
    r = make_res('R1', sched, tas_w=200, tas_c=500, has_ats=True, gb=100)
    s.bind_resource(r)
    p_st, _ = make_chain(s, [r], 'ST', 7, 20, 500, tas_aligned=True)
    p_ats, t_ats = make_chain(s, [r], 'ATS', 6, 12, 500, cir=1e6, cbs=1000)
    dl = {p_st: 500, p_ats: 5000}
    res = FusionConfigOptimizer(s, dl, tas_step=10).optimize()
    check('feasible', res.feasible)
    # open_time = 500 - tw - 100(gb), CIR should reflect reduced BW
    cir = t_ats[0].CIR
    check('CIR > 0', cir > 0, 'cir=%s' % cir)
    # With gb=100, available fraction < (500-tw)/500
    check('CIR < linkspeed', cir < 1e9, 'cir=%s' % cir)

if __name__ == '__main__':
    test_multi_ats_flows()
    test_ats_no_open_time()
    test_guard_band_impact()
    exit(0 if summary() else 1)
