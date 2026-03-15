"""
CQF with Preemption (CQFP) Scheduler for TSN networks.

Implements schedulability analysis for CQF combined with Frame Preemption,
based on:
    Luo F, Wang Z, Guo Y, et al. Research on Cyclic Queuing and Forwarding
    With Preemption in Time-Sensitive Networking[J]. IEEE Embedded Systems
    Letters, 2023.

Traffic classes (determined by TSN_Resource configuration):
    N+E: Non-CQF, Express
    N+P: Non-CQF, Preemptable
    C+E: CQF, Express
    C+P: CQF, Preemptable

Authors:
    - Zitong Wang (original CQFPScheduler)
    - Migrated to new pycpa architecture
"""
from __future__ import absolute_import, print_function, unicode_literals, division

import math
import logging

from . import analysis
from . import model

logger = logging.getLogger("pycpa")

# --------------------------------------------------------------------------
# Preemption constants (IEEE 802.3br / 802.1Qbu)
# Byte sizes are fixed by the standard; time conversions depend on link speed.
# --------------------------------------------------------------------------
MAX_NONPREEMPTABLE_FRAGMENT_BYTES = 143   # Minimum Ethernet frame that cannot be preempted
MIN_FRAGMENT_BYTES = 84                    # Minimum fragment size (64B payload + 20B overhead)
PREEMPTION_OVERHEAD_BYTES = 24             # IPG + preamble overhead per preemption


def _bytes_to_us(nbytes, linkspeed=1e9):
    """Convert bytes to microseconds at given link speed (bps)."""
    return nbytes * 8 / linkspeed * 1e6


def _get_linkspeed(resource):
    """Get link speed in bps from resource (default 1 Gbps)."""
    return getattr(resource, 'linkspeed', 1e9)


def _max_fragment_us(resource):
    """Max non-preemptable fragment time (143B) at resource link speed."""
    return _bytes_to_us(MAX_NONPREEMPTABLE_FRAGMENT_BYTES, _get_linkspeed(resource))


def _min_fragment_us(resource):
    """Min fragment time (84B) at resource link speed."""
    return _bytes_to_us(MIN_FRAGMENT_BYTES, _get_linkspeed(resource))


def _overhead_us(resource):
    """Preemption overhead time (24B) at resource link speed."""
    return _bytes_to_us(PREEMPTION_OVERHEAD_BYTES, _get_linkspeed(resource))


def _get_traffic_class(task, resource):
    """Determine the traffic class of a task based on its resource configuration.

    Returns a tuple (uses_cqf: bool, is_express: bool).
    """
    is_tsn = getattr(resource, 'is_tsn_resource', False)
    if not is_tsn:
        return (False, True)  # Default: N+E

    prio = task.scheduling_parameter
    uses_cqf = resource.priority_uses_cqf(prio)
    is_express_val = resource.effective_is_express(prio)
    is_express = is_express_val if is_express_val is not None else True
    return (uses_cqf, is_express)


def _cqf_cycle(task, resource):
    """Get CQF cycle time for a task from its resource."""
    is_tsn = getattr(resource, 'is_tsn_resource', False)
    if is_tsn:
        return resource.effective_cqf_cycle_time(task.scheduling_parameter)
    return None


def _L_plus(C_plus, resource):
    """Lemma 1 (Luo2023 Eq.2): longest blocking of an express frame
    from a preemptable frame.

    L_i^+ = min(C_i^+, 143 bytes / r_TX)
    """
    return min(C_plus, _max_fragment_us(resource))


def _get_interferers(task):
    """Get resource interferers excluding ForwardingTasks."""
    return [ti for ti in task.get_resource_interferers()
            if not model.ForwardingTask.is_forwarding_task(ti)]


def _num_fragments(payload_bytes):
    """Number of preemption fragments for a frame with given payload.

    F_i^+ = floor((payload - 42) / 60)
    Based on IEEE 802.3br fragment calculation.
    """
    if payload_bytes is None:
        return 0
    return max(0, math.floor((payload_bytes - 42) / 60))


def _cqf_eta_window(w, t_cqf):
    """Compute the CQF-adjusted busy window for eta_plus_closed.

    For CQF streams, interference is maximized at cycle boundaries:
    eta_j^+(ceil(w / t_CQF) * t_CQF)
    """
    if t_cqf is None or t_cqf <= 0:
        return w
    return math.ceil(w / t_cqf) * t_cqf


class CQFPScheduler(analysis.Scheduler):
    """CQF with Preemption Scheduler.

    Implements Luo2023 schedulability analysis for four traffic classes
    under CQF combined with frame preemption.

    Traffic class is determined from TSN_Resource configuration:
    - CQF: resource.priority_uses_cqf(priority)
    - Express/Preemptable: resource.effective_is_express(priority)

    Required TSN_Resource configuration:
    - priority_mechanism_map with CQF pairs
    - cqf_cycle_time or cqf_cycle_time_by_pair
    - is_express_by_priority (True=express, False=preemptable)

    Task attributes:
    - scheduling_parameter: priority (higher number = higher priority)
    - wcet: worst-case execution (transmission) time
    - payload: frame payload in bytes (needed for preemptable streams)
    """

    def __init__(self):
        analysis.Scheduler.__init__(self)
        self._arrival_time_final = 0

    # ------------------------------------------------------------------
    # Arrival time candidate set (shared by all traffic classes)
    # ------------------------------------------------------------------

    def _build_arrival_set(self, task, q):
        """Build the set of candidate arrival times a_i^q.

        Same-priority interferers whose delta_min falls within
        [delta_min(q), delta_min(q+1)) are candidates.
        """
        a_min = task.in_event_model.delta_min(q)
        a_max = task.in_event_model.delta_min(q + 1)
        aiq = []
        for ti in _get_interferers(task):
            if ti.scheduling_parameter == task.scheduling_parameter:
                for n in range(1, 1000):
                    d = ti.in_event_model.delta_min(n)
                    if d >= a_min and d < a_max:
                        aiq.append(d)
        return aiq if aiq else [a_min]

    # ------------------------------------------------------------------
    # Per-traffic-class busy window computation
    # ------------------------------------------------------------------

    def _w_ne(self, task, q, a, resource):
        """Busy window for N+E stream (Luo2023 Sec.III-A, Eq.1+3).

        w = I_LPB + I_SPB + I_HPB  (no scheduler blocking)
        """
        # --- Lower-priority blocking: max of one LP frame ---
        # LP preemptable: capped by L+ (Lemma 1)
        # LP express or LP non-CQF express: full wcet
        i_lpb = 0
        for ti in _get_interferers(task):
            if ti.scheduling_parameter < task.scheduling_parameter:
                ti_cqf, ti_express = _get_traffic_class(ti, resource)
                if not ti_express:  # preemptable
                    candidate = _L_plus(ti.wcet, resource)
                else:
                    candidate = ti.wcet
                i_lpb = max(i_lpb, candidate)

        # --- Same-priority blocking ---
        i_spb = (q - 1) * task.wcet
        for ti in _get_interferers(task):
            if ti.scheduling_parameter == task.scheduling_parameter:
                i_spb += ti.wcet * ti.in_event_model.eta_plus_closed(a)

        # --- Higher-priority blocking (fix-point iteration) ---
        w = i_lpb + i_spb
        while True:
            i_hpb = 0
            for ti in _get_interferers(task):
                if ti.scheduling_parameter > task.scheduling_parameter:
                    ti_cqf, ti_express = _get_traffic_class(ti, resource)
                    t_cqf_ti = _cqf_cycle(ti, resource)

                    if not ti_cqf and ti_express:       # hp N+E: term (a)
                        i_hpb += ti.wcet * ti.in_event_model.eta_plus_closed(w)
                    elif ti_cqf and ti_express:          # hp C+E: term (b)
                        i_hpb += ti.wcet * ti.in_event_model.eta_plus_closed(
                            _cqf_eta_window(w, t_cqf_ti))
                    elif not ti_cqf and not ti_express:  # hp N+P: term (c)
                        i_hpb += _L_plus(ti.wcet, resource) * ti.in_event_model.eta_plus_closed(w)
                    elif ti_cqf and not ti_express:      # hp C+P: term (d)
                        i_hpb += _L_plus(ti.wcet, resource) * ti.in_event_model.eta_plus_closed(
                            _cqf_eta_window(w, t_cqf_ti))

            w_new = i_lpb + i_spb + i_hpb
            if w == w_new:
                break
            w = w_new
        return w

    def _w_np(self, task, q, a, resource):
        """Busy window for N+P stream (Luo2023 Sec.III-B, Eq.4+5+6).

        w = I_LPB + I_SPB + I_HPB + I_SKD
        Two cases for scheduler blocking; take the one yielding smaller w.
        """
        return self._w_preemptable_common(task, q, a, resource, cqf_offset=0)

    def _w_ce(self, task, q, a, resource):
        """Busy window for C+E stream (Luo2023 Sec.III-C).

        Same as N+E but with CQF initial offset phi = t_CQF.
        w uses (w - phi) for HP interference windows.
        """
        t_cqf = _cqf_cycle(task, resource)
        phi = t_cqf  # worst case: phi = t_CQF (Luo2023 Sec.III-C)

        # --- Lower-priority blocking (same as N+E) ---
        i_lpb = 0
        for ti in _get_interferers(task):
            if ti.scheduling_parameter < task.scheduling_parameter:
                ti_cqf, ti_express = _get_traffic_class(ti, resource)
                if not ti_express:
                    candidate = _L_plus(ti.wcet, resource)
                else:
                    candidate = ti.wcet
                i_lpb = max(i_lpb, candidate)

        # --- Same-priority blocking ---
        i_spb = (q - 1) * task.wcet
        for ti in _get_interferers(task):
            if ti.scheduling_parameter == task.scheduling_parameter:
                i_spb += ti.wcet * ti.in_event_model.eta_plus_closed(a)

        # --- Higher-priority blocking (fix-point, with CQF offset) ---
        w = i_lpb + i_spb + phi
        while True:
            i_hpb = 0
            w_eff = w - phi  # effective window for HP interference
            for ti in _get_interferers(task):
                if ti.scheduling_parameter > task.scheduling_parameter:
                    ti_cqf, ti_express = _get_traffic_class(ti, resource)
                    t_cqf_ti = _cqf_cycle(ti, resource)

                    if not ti_cqf and ti_express:       # hp N+E
                        i_hpb += ti.wcet * ti.in_event_model.eta_plus_closed(w_eff)
                    elif ti_cqf and ti_express:          # hp C+E
                        i_hpb += ti.wcet * ti.in_event_model.eta_plus_closed(
                            _cqf_eta_window(w_eff, t_cqf_ti))
                    elif not ti_cqf and not ti_express:  # hp N+P
                        i_hpb += _L_plus(ti.wcet, resource) * ti.in_event_model.eta_plus_closed(w_eff)
                    elif ti_cqf and not ti_express:      # hp C+P
                        i_hpb += _L_plus(ti.wcet, resource) * ti.in_event_model.eta_plus_closed(
                            _cqf_eta_window(w_eff, t_cqf_ti))

            w_new = i_lpb + i_spb + phi + i_hpb
            if w == w_new:
                break
            w = w_new

        # Scheduler blocking for C+E is just the CQF offset
        # (no preemption overhead for express streams)
        return w

    def _w_cp(self, task, q, a, resource):
        """Busy window for C+P stream (Luo2023 Sec.III-D).

        Same as N+P but with CQF initial offset phi = t_CQF added.
        """
        t_cqf = _cqf_cycle(task, resource)
        phi = t_cqf  # worst case
        return self._w_preemptable_common(task, q, a, resource, cqf_offset=phi)

    def _w_preemptable_common(self, task, q, a, resource, cqf_offset):
        """Common busy window computation for preemptable streams (N+P and C+P).

        Implements Luo2023 Eq.4 (LPB), Eq.5 (HPB), Eq.6 (SKD).
        Two cases for scheduler blocking; result = min(case1, case2).

        :param cqf_offset: 0 for N+P, t_CQF for C+P
        """
        phi = cqf_offset
        overhead = _overhead_us(resource)

        # --- Lower-priority blocking term (a): max LP preemptable frame ---
        lpb_term_a = 0
        for ti in _get_interferers(task):
            if ti.scheduling_parameter < task.scheduling_parameter:
                ti_cqf, ti_express = _get_traffic_class(ti, resource)
                if not ti_express:  # preemptable LP
                    lpb_term_a = max(lpb_term_a, ti.wcet)

        # --- Same-priority blocking ---
        i_spb = 0
        for ti in _get_interferers(task):
            if ti.scheduling_parameter == task.scheduling_parameter:
                i_spb += ti.wcet * ti.in_event_model.eta_plus_closed(a)

        # Base blocking (before HP and SKD): Luo2023 Eq.4 term(a) + SPB
        # For preemptable: response includes -min_fragment offset
        min_frag = _min_fragment_us(resource)
        base = q * task.wcet + lpb_term_a - min_frag + i_spb + phi

        # ============================================================
        # Case 1: preemption overhead < express frame blocking
        #   SKD uses terms (a)+(b)+(c) from Eq.6
        # ============================================================
        w1 = base
        while True:
            # LP blocking terms (b) and (c) from Eq.4
            lpb_bc = 0
            for ti in _get_interferers(task):
                if ti.scheduling_parameter < task.scheduling_parameter:
                    ti_cqf, ti_express = _get_traffic_class(ti, resource)
                    t_cqf_ti = _cqf_cycle(ti, resource)
                    w_eff = w1 - phi if phi > 0 else w1
                    if not ti_cqf and ti_express:       # LP N+E: Eq.4 term(b)
                        lpb_bc += ti.wcet * ti.in_event_model.eta_plus_closed(w_eff)
                    elif ti_cqf and ti_express:          # LP C+E: Eq.4 term(c)
                        lpb_bc += ti.wcet * ti.in_event_model.eta_plus_closed(
                            _cqf_eta_window(w_eff, t_cqf_ti))

            # HP blocking: Eq.5
            i_hpb = 0
            for ti in _get_interferers(task):
                if ti.scheduling_parameter > task.scheduling_parameter:
                    ti_cqf, ti_express = _get_traffic_class(ti, resource)
                    t_cqf_ti = _cqf_cycle(ti, resource)
                    w_eff = w1 - phi if phi > 0 else w1
                    if not ti_cqf:  # N+E or N+P
                        i_hpb += ti.wcet * ti.in_event_model.eta_plus_closed(w_eff)
                    else:           # C+E or C+P
                        i_hpb += ti.wcet * ti.in_event_model.eta_plus_closed(
                            _cqf_eta_window(w_eff, t_cqf_ti))

            # SKD Case 1: terms (a)+(b)+(c) from Eq.6
            skd_abc = 0
            # term (a): express frames from non-CQF
            for ti in _get_interferers(task):
                if ti.scheduling_parameter != task.scheduling_parameter:
                    ti_cqf, ti_express = _get_traffic_class(ti, resource)
                    t_cqf_ti = _cqf_cycle(ti, resource)
                    w_eff = w1 - phi if phi > 0 else w1
                    if not ti_cqf and ti_express:
                        skd_abc += overhead * ti.in_event_model.eta_plus_closed(w_eff)
                    elif ti_cqf and ti_express:
                        skd_abc += overhead * min(
                            math.ceil(w_eff / t_cqf_ti) if t_cqf_ti else 0,
                            ti.in_event_model.eta_plus_closed(
                                _cqf_eta_window(w_eff, t_cqf_ti)))

            w1_new = base + lpb_bc + i_hpb + skd_abc
            if w1 == w1_new:
                break
            w1 = w1_new

        # ============================================================
        # Case 2: preemption overhead >= express frame blocking
        #   SKD uses term (d) from Eq.6
        # ============================================================

        # SKD term (d) fixed parts: fragment counts
        skd_fixed_lp = 0  # term (a) of Eq.6: max LP preemptable fragment count
        for ti in _get_interferers(task):
            if ti.scheduling_parameter < task.scheduling_parameter:
                ti_cqf, ti_express = _get_traffic_class(ti, resource)
                if not ti_express:
                    payload = getattr(ti, 'payload', None)
                    skd_fixed_lp = max(skd_fixed_lp, _num_fragments(payload))

        skd_fixed_sp = 0  # term (b) of Eq.6: same-priority fragment counts
        for ti in _get_interferers(task):
            if ti.scheduling_parameter == task.scheduling_parameter:
                payload = getattr(ti, 'payload', None)
                skd_fixed_sp += _num_fragments(payload) * ti.in_event_model.eta_plus_closed(a)

        task_payload = getattr(task, 'payload', None)
        task_fragments = _num_fragments(task_payload)
        skd_self = q * task_fragments - 1  # term (b) self part

        skd_d_fixed = overhead * (skd_fixed_lp + max(0, skd_self) + skd_fixed_sp)

        w2 = base + skd_d_fixed
        while True:
            lpb_bc = 0
            for ti in _get_interferers(task):
                if ti.scheduling_parameter < task.scheduling_parameter:
                    ti_cqf, ti_express = _get_traffic_class(ti, resource)
                    t_cqf_ti = _cqf_cycle(ti, resource)
                    w_eff = w2 - phi if phi > 0 else w2
                    if not ti_cqf and ti_express:
                        lpb_bc += ti.wcet * ti.in_event_model.eta_plus_closed(w_eff)
                    elif ti_cqf and ti_express:
                        lpb_bc += ti.wcet * ti.in_event_model.eta_plus_closed(
                            _cqf_eta_window(w_eff, t_cqf_ti))

            i_hpb = 0
            for ti in _get_interferers(task):
                if ti.scheduling_parameter > task.scheduling_parameter:
                    ti_cqf, ti_express = _get_traffic_class(ti, resource)
                    t_cqf_ti = _cqf_cycle(ti, resource)
                    w_eff = w2 - phi if phi > 0 else w2
                    if not ti_cqf:
                        i_hpb += ti.wcet * ti.in_event_model.eta_plus_closed(w_eff)
                    else:
                        i_hpb += ti.wcet * ti.in_event_model.eta_plus_closed(
                            _cqf_eta_window(w_eff, t_cqf_ti))

            # SKD term (c) of Eq.6: HP preemptable fragment counts (w-dependent)
            skd_hp = 0
            for ti in _get_interferers(task):
                if ti.scheduling_parameter > task.scheduling_parameter:
                    ti_cqf, ti_express = _get_traffic_class(ti, resource)
                    if not ti_express:
                        t_cqf_ti = _cqf_cycle(ti, resource)
                        payload = getattr(ti, 'payload', None)
                        f = _num_fragments(payload)
                        w_eff = w2 - phi if phi > 0 else w2
                        if not ti_cqf:
                            skd_hp += f * ti.in_event_model.eta_plus_closed(w_eff)
                        else:
                            skd_hp += f * ti.in_event_model.eta_plus_closed(
                                _cqf_eta_window(w_eff, t_cqf_ti))

            w2_new = base + lpb_bc + i_hpb + skd_d_fixed + overhead * skd_hp
            if w2 == w2_new:
                break
            w2 = w2_new

        # Take the minimum of the two cases (tighter bound)
        return min(w1, w2)

    # ------------------------------------------------------------------
    # Public interface: b_plus and response_time
    # ------------------------------------------------------------------

    def b_plus(self, task, q, details=None, **kwargs):
        """Return the maximum busy time for q activations.

        Returns w + C_last where C_last is:
        - wcet for express streams
        - _min_fragment_us(resource) for preemptable streams
        This ensures b_plus(q) - b_plus(q-1) >= wcet (framework invariant).

        For forwarding tasks: returns q * wcet directly (no blocking).

        Dispatches to the appropriate traffic-class-specific method
        based on TSN_Resource configuration.
        """
        assert task.scheduling_parameter is not None
        assert task.wcet >= 0

        # Forwarding tasks: no blocking, simple busy window
        if model.ForwardingTask.is_forwarding_task(task):
            return q * task.wcet

        resource = task.resource
        uses_cqf, is_express = _get_traffic_class(task, resource)

        aiq = self._build_arrival_set(task, q)

        r_final = 0
        w_final = 0

        for a in aiq:
            if not uses_cqf and is_express:
                w = self._w_ne(task, q, a, resource)
            elif not uses_cqf and not is_express:
                w = self._w_np(task, q, a, resource)
            elif uses_cqf and is_express:
                w = self._w_ce(task, q, a, resource)
            else:  # uses_cqf and not is_express
                w = self._w_cp(task, q, a, resource)

            # Response time = w + C_last - a
            if is_express:
                c_last = task.wcet
            else:
                c_last = _min_fragment_us(resource)
            r = w + c_last - a

            if r > r_final:
                r_final = r
                w_final = w + c_last
                self._arrival_time_final = a

        return w_final

    def response_time(self, task, q, w, details=None, **kwargs):
        """Return the response time for q activations.

        R = w - arrival_time_final
        (w already includes C_last from b_plus)
        """
        return w - self._arrival_time_final


class CQFPSchedulerE2E(CQFPScheduler):
    """CQF with Preemption Scheduler, E2E-optimized version.

    Same per-hop WCRT computation as CQFPScheduler.  Additionally records
    ``cqf_cycle_time`` into ``task_results`` for CQF streams so that
    ``path_analysis`` can apply the multi-hop CQF correction:

        E2E = (N-1) * T_CQF + WCRT_last_hop

    based on Thesis Eq.(3.31): in CQF, intermediate hops contribute exactly
    one cycle time each; only the last hop needs the full local analysis.

    For non-CQF streams (N+E, N+P), behaviour is identical to CQFPScheduler.

    Usage::

        r = TSN_Resource("SW", schedulers_cqfp.CQFPSchedulerE2E(), ...)
    """

    def b_plus(self, task, q, details=None, **kwargs):
        w = CQFPScheduler.b_plus(self, task, q, details=details, **kwargs)

        # Record CQF cycle time for path_analysis E2E correction
        task_results = kwargs.get('task_results')
        if task_results is not None and task in task_results and details is not None:
            resource = task.resource
            uses_cqf, _ = _get_traffic_class(task, resource)
            if uses_cqf:
                t_cqf = _cqf_cycle(task, resource)
                task_results[task].cqf_cycle_time = t_cqf
        return w
