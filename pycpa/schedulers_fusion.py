"""
Fusion Scheduler for TSN networks.

Unified CPA-based schedulability analysis supporting TAS (802.1Qbv),
CQF (802.1Qch), ATS (802.1Qcr), and Frame Preemption (802.1Qbu)
on a single resource.

Based on the fusion architecture in:
    Wang Z. Research on High-Reliability Comprehensive Scheduling Methods
    for In-Vehicle Time-Sensitive Networks [D]. PhD Thesis, 2025.
    (Chapter 3, Section 3.5)

Flow classification (6 types, determined by TSN_Resource + Task attributes):
    ST:     TAS-scheduled, Express (highest priority, gate-controlled)
    ATS+E:  ATS-scheduled, Express
    C+E:    CQF-scheduled, Express
    C+P:    CQF-scheduled, Preemptable
    NC+E:   No special mechanism, Express
    NC+P:   No special mechanism, Preemptable

Key references for sub-flow analysis:
    [Thiele2015] Thiele D, Ernst R, Diemer J. Formal worst-case timing
        analysis of Ethernet TSN's time-aware and peristaltic shapers[C]
        //VNC 2015: 251-258.  (TAS gate-closed blocking)
    [Thiele2016] Thiele D, Ernst R. Formal worst-case performance analysis
        of time-sensitive Ethernet with frame preemption[C]//ETFA 2016.
        (LPB/SPB for preemptable, preemption overhead Eq.3/5/9/10)
    [Luo2023] Luo F, Wang Z, Guo Y, et al. Research on CQF with preemption
        in TSN[J]. IEEE ESL, 2023, 16(2): 110-113.  (CQF+FP analysis)

Authors:
    - Zitong Wang
"""
from __future__ import absolute_import, print_function, unicode_literals, division

import math
import logging

from . import analysis
from . import model

from .schedulers_cqfp import (
    _bytes_to_us, _get_linkspeed, _max_fragment_us, _min_fragment_us,
    _overhead_us, _L_plus, _num_fragments, _cqf_eta_window, _cqf_cycle,
    MAX_NONPREEMPTABLE_FRAGMENT_BYTES, MIN_FRAGMENT_BYTES,
    PREEMPTION_OVERHEAD_BYTES,
)
from .schedulers_ats import (
    _get_src_port, _is_ats, _n_token, _compute_eT_block,
)

logger = logging.getLogger("pycpa")


# ======================================================================
# Helper functions
# ======================================================================

def _get_interferers(task):
    return [ti for ti in task.get_resource_interferers()
            if not model.ForwardingTask.is_forwarding_task(ti)]


def _get_traffic_class(task, resource):
    """Returns (mechanism, is_express). mechanism: 'TAS'/'CQF'/'ATS'/None."""
    is_tsn = getattr(resource, 'is_tsn_resource', False)
    if not is_tsn:
        return (None, True)
    prio = task.scheduling_parameter
    if resource.priority_uses_tas(prio):
        return ('TAS', True)
    if resource.priority_uses_ats(prio):
        is_exp = resource.effective_is_express(prio)
        return ('ATS', is_exp if is_exp is not None else True)
    if resource.priority_uses_cqf(prio):
        is_exp = resource.effective_is_express(prio)
        return ('CQF', is_exp if is_exp is not None else True)
    is_exp = resource.effective_is_express(prio)
    return (None, is_exp if is_exp is not None else True)


def _has_tas_on_resource(resource):
    if not getattr(resource, 'is_tsn_resource', False):
        return False
    if resource.priority_mechanism_map is None:
        return False
    return any(m == 'TAS' for m in resource.priority_mechanism_map.values())


def _tas_gate_closed_duration(resource):
    """Total TAS window duration (sum of all TAS priority windows)."""
    duration = 0
    if resource.priority_mechanism_map is not None:
        for key, mech in resource.priority_mechanism_map.items():
            if mech == 'TAS' and not isinstance(key, tuple):
                duration += resource.effective_tas_window_time(key)
    return duration


def _tas_guard_band(task, resource):
    """Guard band: max(min_non_preemptable_frame, max_express_NST_wcet)."""
    gb = _max_fragment_us(resource)
    for ti in _get_interferers(task):
        mech_ti, exp_ti = _get_traffic_class(ti, resource)
        if mech_ti != 'TAS' and exp_ti:
            gb = max(gb, ti.wcet)
    return gb


# ======================================================================
# FusionScheduler
# ======================================================================

class FusionScheduler(analysis.Scheduler):
    """Unified CPA scheduler fusing TAS, CQF, ATS, and Frame Preemption.

    Dispatches b_plus based on target flow type per thesis Fig.3.27.
    Priority convention: higher number = higher priority (TSN).
    """

    def __init__(self):
        analysis.Scheduler.__init__(self)
        self._arrival_time_final = 0
        self._last_gate_closed_blocking = 0

    # ------------------------------------------------------------------
    # Arrival time candidate set
    # ------------------------------------------------------------------

    def _build_arrival_set(self, task, q):
        a_min = task.in_event_model.delta_min(q)
        a_max = task.in_event_model.delta_min(q + 1)
        aiq = []
        for ti in _get_interferers(task):
            if ti.scheduling_parameter == task.scheduling_parameter:
                for n in range(1, 1000):
                    d = ti.in_event_model.delta_min(n)
                    if d >= a_max:
                        break
                    if d >= a_min:
                        aiq.append(d)
        return aiq if aiq else [a_min]

    # ------------------------------------------------------------------
    # Mechanism-aware interferer count (Fig.3.25 logic)
    # ------------------------------------------------------------------

    def _interferer_count(self, ti, delta_t, resource):
        """Frames from ti in interval delta_t, accounting for mechanism.

        Uses eta_plus_closed (closed interval [t, t+Δt]) for time-window-based
        counting (HPB, LPB express, SKD).  This is equivalent to
        eta_plus(Δt + ε) used in pycpa's SPNP scheduler and avoids the
        spurious fixed-point at w=0 where eta_plus(0)=0 would miss
        simultaneous higher-priority arrivals.
        """
        mech_ti, _ = _get_traffic_class(ti, resource)
        if mech_ti == 'CQF':
            t_cqf_ti = _cqf_cycle(ti, resource)
            return ti.in_event_model.eta_plus_closed(
                _cqf_eta_window(delta_t, t_cqf_ti))
        elif mech_ti == 'ATS':
            return min(ti.in_event_model.eta_plus_closed(delta_t),
                       _n_token(delta_t, ti, resource))
        else:
            return ti.in_event_model.eta_plus_closed(delta_t)

    # ------------------------------------------------------------------
    # TAS gate-closed blocking (Eq.3.22, shared)
    # ------------------------------------------------------------------

    def _tas_gate_blocking(self, task, q, spb, resource):
        """TAS gate-closed blocking Eq.(3.22) for non-TAS flows.

        The load that must fit in open windows is (spb + task.wcet).
        """
        tas_window_total = _tas_gate_closed_duration(resource)
        tas_cycle = resource.effective_tas_cycle_time()
        guard_band = _tas_guard_band(task, resource)
        open_time = tas_cycle - tas_window_total - guard_band
        if open_time <= 0:
            return 0
        load = spb + task.wcet
        gb = math.ceil(load / open_time) * (tas_window_total + guard_band)
        self._last_gate_closed_blocking = gb
        return gb

    # ------------------------------------------------------------------
    # ST flow (Fig.3.27 top branch)
    # ------------------------------------------------------------------

    def _w_st(self, task, q, a, resource):
        """ST: SPB(Eq.3.10) + SCH(Eq.3.22)."""
        spb = (q - 1) * task.wcet
        max_st_wcet = task.wcet
        for ti in _get_interferers(task):
            if ti.scheduling_parameter == task.scheduling_parameter:
                spb += ti.wcet * ti.in_event_model.eta_plus_closed(a)
                max_st_wcet = max(max_st_wcet, ti.wcet)

        tas_cycle = resource.effective_tas_cycle_time(task.scheduling_parameter)
        tas_window = resource.effective_tas_window_time(task.scheduling_parameter)
        gate_closed = tas_cycle - tas_window + max_st_wcet
        if (tas_window - max_st_wcet) > 0:
            schb = math.ceil(
                (spb + task.wcet) / (tas_window - max_st_wcet)) * gate_closed
        else:
            schb = 0
        self._last_gate_closed_blocking = schb
        return spb + schb

    # ------------------------------------------------------------------
    # Non-ST Express flows (ATS+E, C+E, NC+E)
    # ------------------------------------------------------------------

    def _w_express(self, task, q, a, resource, mech_task):
        """Busy window for express non-ST flows."""
        # LPB: max LP frame (preemptable capped by L+)
        lpb = 0
        for ti in _get_interferers(task):
            if ti.scheduling_parameter >= task.scheduling_parameter:
                continue
            _, exp_ti = _get_traffic_class(ti, resource)
            if not exp_ti:
                lpb = max(lpb, _L_plus(ti.wcet, resource))
            else:
                lpb = max(lpb, ti.wcet)

        # SPB
        if mech_task == 'ATS':
            spb_fixed = 0.0
            src_port = _get_src_port(task)
            same_port_max = {}
            diff_port_flows = []
            for ti in _get_interferers(task):
                if ti.scheduling_parameter != task.scheduling_parameter:
                    continue
                ti_port = _get_src_port(ti)
                if ti_port == src_port and ti_port is not None:
                    same_port_max[ti_port] = max(
                        same_port_max.get(ti_port, 0), ti.wcet)
                else:
                    diff_port_flows.append(ti)
            spb_fixed += sum(same_port_max.values())
            spb = spb_fixed  # initial estimate for tas_gb calculation
        else:
            spb = (q - 1) * task.wcet
            for ti in _get_interferers(task):
                if ti.scheduling_parameter == task.scheduling_parameter:
                    spb += ti.wcet * ti.in_event_model.eta_plus_closed(a)

        has_tas = _has_tas_on_resource(resource)
        # TAS gate blocking: fixed, based on load (spb + wcet)
        tas_gb = 0
        if has_tas:
            tas_gb = self._tas_gate_blocking(task, q, spb, resource)

        if mech_task == 'ATS':
            eT_block = _compute_eT_block(task, q, resource)
            w_tilde = lpb + spb_fixed
            for _ in range(1000):
                spb_diff = 0
                for ti in diff_port_flows:
                    n = min(ti.in_event_model.eta_plus_closed(w_tilde),
                            _n_token(w_tilde, ti, resource))
                    spb_diff += n * ti.wcet

                hpb = 0
                for ti in _get_interferers(task):
                    if ti.scheduling_parameter <= task.scheduling_parameter:
                        continue
                    mech_ti, exp_ti = _get_traffic_class(ti, resource)
                    if mech_ti == 'TAS':
                        continue
                    n = self._interferer_count(ti, w_tilde, resource)
                    hpb += n * (ti.wcet if exp_ti
                                else _L_plus(ti.wcet, resource))
                w_tilde_new = lpb + spb_fixed + spb_diff + hpb + tas_gb
                if w_tilde == w_tilde_new:
                    break
                w_tilde = w_tilde_new
            return a + eT_block + w_tilde
        else:
            phi = 0
            if mech_task == 'CQF':
                t_cqf = _cqf_cycle(task, resource)
                phi = t_cqf if t_cqf else 0

            w = lpb + spb + phi + tas_gb
            for _ in range(1000):
                delta_t = max(w - phi, 0) if phi > 0 else w

                hpb = 0
                for ti in _get_interferers(task):
                    if ti.scheduling_parameter <= task.scheduling_parameter:
                        continue
                    mech_ti, exp_ti = _get_traffic_class(ti, resource)
                    if mech_ti == 'TAS':
                        continue
                    n = self._interferer_count(ti, delta_t, resource)
                    hpb += n * (ti.wcet if exp_ti
                                else _L_plus(ti.wcet, resource))

                w_new = lpb + spb + phi + hpb + tas_gb
                if w == w_new:
                    break
                w = w_new
            return w

    # ------------------------------------------------------------------
    # Non-ST Preemptable flows (C+P, NC+P)
    # Structure follows CQFPScheduler._w_preemptable_common
    # ------------------------------------------------------------------

    def _w_preemptable(self, task, q, a, resource, mech_task):
        """Busy window for preemptable non-ST flows.

        Two cases for preemption overhead (Luo2023 Eq.6), take min.
        """
        min_frag = _min_fragment_us(resource)
        overhead = _overhead_us(resource)

        # LPB term (a): max LP preemptable frame
        lpb_a = 0
        for ti in _get_interferers(task):
            if ti.scheduling_parameter >= task.scheduling_parameter:
                continue
            mech_ti, exp_ti = _get_traffic_class(ti, resource)
            if not exp_ti:
                if mech_task == 'CQF' and mech_ti == 'CQF':
                    continue
                lpb_a = max(lpb_a, ti.wcet)

        # SPB (same-prio interferers)
        spb = 0
        diff_port_flows = []
        if mech_task == 'ATS':
            # Eq.(3.41): same-port max + diff-port iterative
            src_port = _get_src_port(task)
            same_port_max = {}
            for ti in _get_interferers(task):
                if ti.scheduling_parameter != task.scheduling_parameter:
                    continue
                ti_port = _get_src_port(ti)
                if ti_port == src_port and ti_port is not None:
                    same_port_max[ti_port] = max(
                        same_port_max.get(ti_port, 0), ti.wcet)
                else:
                    diff_port_flows.append(ti)
            spb_fixed = sum(same_port_max.values())
            spb = spb_fixed
        else:
            spb_fixed = 0
            for ti in _get_interferers(task):
                if ti.scheduling_parameter == task.scheduling_parameter:
                    spb_fixed += ti.wcet * ti.in_event_model.eta_plus_closed(a)
            spb = spb_fixed

        phi = 0
        if mech_task == 'CQF':
            t_cqf = _cqf_cycle(task, resource)
            phi = t_cqf if t_cqf else 0

        base = q * task.wcet + lpb_a - min_frag + spb + phi
        has_tas = _has_tas_on_resource(resource)
        tas_gb = 0
        if has_tas:
            # load for gate blocking = q*wcet + sum_sp(eta*C+)
            # for ATS: spb is same_port_max (no q*wcet term)
            # for non-ATS: spb is sum_sp(eta*C+), need (q-1)*wcet + spb
            spb_for_gb = spb if mech_task == 'ATS' else (q - 1) * task.wcet + spb
            tas_gb = self._tas_gate_blocking(task, q, spb_for_gb, resource)

        # --- SKD Case 2 fixed parts: fragment counts (Luo2023 Eq.6 term d) ---
        skd_lp_frag = 0
        for ti in _get_interferers(task):
            if ti.scheduling_parameter < task.scheduling_parameter:
                _, exp_ti = _get_traffic_class(ti, resource)
                if not exp_ti:
                    skd_lp_frag = max(skd_lp_frag,
                                      _num_fragments(getattr(ti, 'payload', None)))
        skd_sp_frag = 0
        for ti in _get_interferers(task):
            if ti.scheduling_parameter == task.scheduling_parameter:
                skd_sp_frag += (_num_fragments(getattr(ti, 'payload', None))
                                * ti.in_event_model.eta_plus_closed(a))
        self_frag = max(0, q * _num_fragments(
            getattr(task, 'payload', None)) - 1)
        skd_d_fixed = overhead * (skd_lp_frag + skd_sp_frag + self_frag)

        def _iterate(case2):
            w = base + (skd_d_fixed if case2 else 0)
            for _ in range(1000):
                delta_t = max(w - phi, 0) if phi > 0 else w
                if mech_task == 'ATS':
                    delta_t = max(w - _compute_eT_block(task, q, resource), 0)

                lpb_bc = 0
                for ti in _get_interferers(task):
                    if ti.scheduling_parameter >= task.scheduling_parameter:
                        continue
                    _, exp_ti = _get_traffic_class(ti, resource)
                    if exp_ti:
                        n = self._interferer_count(ti, delta_t, resource)
                        lpb_bc += n * ti.wcet

                hpb = 0
                for ti in _get_interferers(task):
                    if ti.scheduling_parameter <= task.scheduling_parameter:
                        continue
                    mech_ti, _ = _get_traffic_class(ti, resource)
                    if mech_ti == 'TAS':
                        continue
                    n = self._interferer_count(ti, delta_t, resource)
                    hpb += n * ti.wcet

                schb = tas_gb
                if mech_task == 'ATS':
                    schb += _compute_eT_block(task, q, resource)

                if case2:
                    # Case 2: SKD = fixed fragments + HP preemptable fragments
                    skd_hp = 0
                    for ti in _get_interferers(task):
                        if ti.scheduling_parameter <= task.scheduling_parameter:
                            continue
                        mech_ti, exp_ti = _get_traffic_class(ti, resource)
                        if not exp_ti and mech_ti != 'TAS':
                            f = _num_fragments(getattr(ti, 'payload', None))
                            skd_hp += f * self._interferer_count(
                                ti, delta_t, resource)
                    skd = skd_d_fixed + overhead * skd_hp
                else:
                    # Case 1: SKD = sum of express frame overheads
                    # (Luo2023 Eq.6 terms a+b+c)
                    skd = 0
                    for ti in _get_interferers(task):
                        if ti.scheduling_parameter == task.scheduling_parameter:
                            continue
                        mech_ti, exp_ti = _get_traffic_class(ti, resource)
                        if not exp_ti:
                            continue
                        if mech_ti == 'TAS':
                            tc = resource.effective_tas_cycle_time()
                            if tc > 0:
                                skd += overhead * math.floor(delta_t / tc)
                            continue
                        if mech_ti == 'CQF':
                            t_cqf_ti = _cqf_cycle(ti, resource)
                            if t_cqf_ti and t_cqf_ti > 0:
                                skd += overhead * min(
                                    math.ceil(delta_t / t_cqf_ti),
                                    ti.in_event_model.eta_plus_closed(
                                        _cqf_eta_window(delta_t, t_cqf_ti)))
                        else:
                            skd += overhead * self._interferer_count(ti, delta_t, resource)

                w_new = base + lpb_bc + hpb + schb + skd
                if diff_port_flows:
                    spb_diff = 0
                    for ti in diff_port_flows:
                        n = min(ti.in_event_model.eta_plus_closed(delta_t),
                                _n_token(delta_t, ti, resource))
                        spb_diff += n * ti.wcet
                    w_new += spb_diff
                if w == w_new:
                    break
                w = w_new
            return w

        return min(_iterate(False), _iterate(True))

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def b_plus(self, task, q, details=None, **kwargs):
        assert task.scheduling_parameter is not None
        assert task.wcet >= 0

        if model.ForwardingTask.is_forwarding_task(task):
            return q * task.wcet

        resource = task.resource
        mech_task, exp_task = _get_traffic_class(task, resource)

        if mech_task == 'ATS':
            for attr in ('CIR', 'CBS'):
                if not hasattr(task, attr):
                    raise ValueError(
                        f"ATS task '{task.name}' missing '{attr}'.")

        aiq = self._build_arrival_set(task, q)
        r_final = 0
        w_final = 0
        gcb_final = 0

        for a in aiq:
            self._last_gate_closed_blocking = 0
            if mech_task == 'TAS':
                w = self._w_st(task, q, a, resource)
            elif exp_task:
                w = self._w_express(task, q, a, resource, mech_task)
            else:
                w = self._w_preemptable(task, q, a, resource, mech_task)

            c_last = task.wcet if exp_task else _min_fragment_us(resource)
            r = w + c_last - a
            if r > r_final:
                r_final = r
                w_final = w + c_last
                self._arrival_time_final = a
                gcb_final = self._last_gate_closed_blocking

        self._last_gate_closed_blocking = gcb_final
        return w_final

    def response_time(self, task, q, w, details=None, **kwargs):
        return w - self._arrival_time_final

    def stopping_condition(self, task, q, w):
        resource = task.resource
        mech_task, _ = _get_traffic_class(task, resource)

        if mech_task == 'TAS' or mech_task == 'CQF':
            return True  # q=1 only

        if mech_task == 'ATS':
            w_next = self.b_plus(task, q + 1)
            rt_cur = w - task.in_event_model.delta_min(q)
            rt_next = w_next - task.in_event_model.delta_min(q + 1)
            return rt_next <= rt_cur

        # NC: standard busy period
        if task.in_event_model.delta_min(q + 1) >= w:
            return True
        return False


class FusionSchedulerE2E(FusionScheduler):
    """Fusion scheduler with E2E multi-hop correction support.

    Same per-hop WCRT as FusionScheduler.  Additionally records attributes
    into task_results so that path_analysis can apply E2E corrections:

    - ST flows: TAS E2E correction (same as TASSchedulerE2E)
    - CQF flows (C+E, C+P): CQF E2E correction = (N-1)*T_CQF + WCRT_last
    - Other NST flows (ATS+E, NC+E, NC+P): TAS gate-closed E2E correction
      (treated as NST in TASSchedulerE2E)
    """

    def b_plus(self, task, q, details=None, **kwargs):
        w = FusionScheduler.b_plus(self, task, q, details=details, **kwargs)

        task_results = kwargs.get('task_results')
        if task_results is None or task not in task_results or details is None:
            return w

        if model.ForwardingTask.is_forwarding_task(task):
            task_results[task].gate_closed_duration = 0
            task_results[task].non_gate_closed = task.wcet
            return w

        resource = task.resource
        mech_task, _ = _get_traffic_class(task, resource)

        if mech_task == 'CQF':
            # CQF E2E: record cycle time for path_analysis
            task_results[task].cqf_cycle_time = _cqf_cycle(task, resource)
            return w

        # ST and NST flows: TAS gate-closed E2E correction
        gcb = self._last_gate_closed_blocking
        task_results[task].non_gate_closed = w - gcb

        if mech_task == 'TAS':
            tas_cycle = resource.effective_tas_cycle_time(task.scheduling_parameter)
            tas_window = resource.effective_tas_window_time(task.scheduling_parameter)
            # For ST: max_st_wcet as guard band (same logic as _w_st)
            max_st_wcet = task.wcet
            for ti in _get_interferers(task):
                if ti.scheduling_parameter == task.scheduling_parameter:
                    max_st_wcet = max(max_st_wcet, ti.wcet)
            task_results[task].gate_closed_duration = tas_cycle - tas_window + max_st_wcet
            task_results[task].tas_available_window = tas_window
        else:
            # NST (ATS+E, NC+E, NC+P): gate_closed = sum(TAS windows) + guard_band
            tw_sum = _tas_gate_closed_duration(resource)
            guard_band = _tas_guard_band(task, resource)
            task_results[task].gate_closed_duration = tw_sum + guard_band
            tc = resource.effective_tas_cycle_time()
            task_results[task].tas_available_window = tc - tw_sum - guard_band

        return w

    def response_time(self, task, q, w, details=None, **kwargs):
        if model.ForwardingTask.is_forwarding_task(task):
            return task.wcet
        return FusionScheduler.response_time(self, task, q, w,
                                             details=details, **kwargs)
