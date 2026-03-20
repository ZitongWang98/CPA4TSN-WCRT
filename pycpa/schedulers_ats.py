"""
ATS (Asynchronous Traffic Shaper, IEEE 802.1Qcr) Scheduler for TSN networks.

Implements schedulability analysis based on CPA for ATS mechanism,
following thesis Eq.(3.32)-(3.44).

Traffic classes (determined by TSN_Resource priority_mechanism_map):
    ATS:  Shaped by ATS token bucket (has CIR/CBS per flow)
    NATS: Not shaped by ATS, standard strict-priority

Per-flow ATS parameters (set on Task):
    CIR:      Committed Information Rate (bps)
    CBS:      Committed Burst Size (bits)
    src_port: (optional) Source port identifier, auto-derived from
              prev_task.resource if not set explicitly

Authors:
    - Zitong Wang
"""
from __future__ import absolute_import, print_function, unicode_literals, division

import math
import logging

from . import analysis
from . import model

logger = logging.getLogger("pycpa")


# ------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------

def _get_src_port(task):
    """Derive src_port from topology: prev_task's resource.

    Same upstream resource → same scheduler group.
    If no prev_task (source node), use task itself as unique key.
    Explicit src_port on task takes precedence.
    """
    explicit = getattr(task, 'src_port', None)
    if explicit is not None:
        return explicit
    if task.prev_task is not None and task.prev_task.resource is not None:
        return id(task.prev_task.resource)
    return id(task)  # source node, unique group


def _get_linkspeed(resource):
    """Get link speed in bps from resource (default 1 Gbps)."""
    return getattr(resource, 'linkspeed', 1e9)


def _is_ats(task, resource):
    """Check if task is an ATS flow based on resource configuration."""
    if not getattr(resource, 'is_tsn_resource', False):
        return False
    return resource.priority_uses_ats(task.scheduling_parameter)


def _get_interferers(task):
    """Get resource interferers excluding ForwardingTasks."""
    return [ti for ti in task.get_resource_interferers()
            if not model.ForwardingTask.is_forwarding_task(ti)]


def _L_plus_bits(task, resource):
    """Max token consumption per frame (bits) = wcet(us) * linkspeed(bps) * 1e-6."""
    return task.wcet * _get_linkspeed(resource) * 1e-6


def _n_token(w_us, task, resource):
    """Eq.(3.38): max frames sendable under token bucket constraint in w_us.

    n = floor((w * CIR * 1e-6 + CBS) / L_plus_bits)
    """
    L_plus = _L_plus_bits(task, resource)
    if L_plus <= 0:
        return 0
    return math.floor((w_us * task.CIR * 1e-6 + task.CBS) / L_plus)


def _compute_eligible_time_block(task, q, resource):
    """Compute ATS scheduling mechanism blocking for the q-th frame.

    Iteratively tracks token state per Eq.(3.32)-(3.35).
    Returns eT_block in microseconds.

    For q=1: eT_block=0 (tokens=CBS, full bucket, always eligible).
    For q>=2: tokens after q=1 send = CBS - L_plus,
    then recover over inter-frame intervals, capped by CBS.

    Does NOT include group eligible time (handled separately).
    """
    if q <= 1:
        return 0.0

    linkspeed = _get_linkspeed(resource)
    L_plus = _L_plus_bits(task, resource)  # bits
    CIR = task.CIR   # bps
    CBS = task.CBS    # bits

    # Track tokens iteratively from q=1 to q
    # q=1: tokens = CBS (full), send consumes L_plus, remainder = CBS - L_plus
    tokens = CBS - L_plus
    eT = 0.0  # eligible time (absolute from busy period start)

    for n in range(2, q + 1):
        # Eq.(3.33): minimum interval between frame n-1 and frame n
        interval = task.in_event_model.delta_min(n) - task.in_event_model.delta_min(n - 1)
        # Eq.(3.32)/(3.35): recover from previous tokens (0 after first send),
        # add CIR * interval, cap at CBS
        tokens = min(tokens + CIR * interval * 1e-6, CBS)

        delta_n = task.in_event_model.delta_min(n)
        if tokens >= L_plus:
            eT = delta_n  # enough tokens at arrival
            tokens -= L_plus  # consume tokens
        else:
            # Eq.(3.34): wait for tokens to reach L_plus
            wait = (L_plus - tokens) / CIR * 1e6  # us
            eT = delta_n + wait
            tokens = 0.0  # all consumed after sending

    # Eq.(3.37): eT_block = eT - arrival_time
    arrival = task.in_event_model.delta_min(q)
    return max(eT - arrival, 0.0)


def _compute_group_eligible_time(task, q, resource):
    """Compute group eligible time for the q-th frame of task.

    Eq.(3.36): max eligible time among same scheduler group flows
    (same src_port, same priority, ATS flows) whose frames arrive
    before task's q-th frame.

    Returns absolute group ET (from busy period start).
    """
    src_port = _get_src_port(task)

    arrival_q = task.in_event_model.delta_min(q)
    group_eT = 0.0

    for ti in _get_interferers(task):
        if not _is_ats(ti, resource):
            continue
        if _get_src_port(ti) != src_port:
            continue
        if ti.scheduling_parameter != task.scheduling_parameter:
            continue

        linkspeed = _get_linkspeed(resource)
        L_plus_ti = ti.wcet * linkspeed * 1e-6
        CIR_ti = ti.CIR
        CBS_ti = ti.CBS

        # Find all frames of ti that arrive before arrival_q
        # q=1: tokens = CBS (full bucket), then consumed to 0 after send
        tokens_ti = CBS_ti
        for n_ti in range(1, 1000):
            delta_ti = ti.in_event_model.delta_min(n_ti)
            if delta_ti > arrival_q:
                break

            if n_ti == 1:
                tokens_ti = CBS_ti
            else:
                interval = ti.in_event_model.delta_min(n_ti) - ti.in_event_model.delta_min(n_ti - 1)
                tokens_ti = min(tokens_ti + CIR_ti * interval * 1e-6, CBS_ti)

            if tokens_ti >= L_plus_ti:
                eT_ti = delta_ti
                tokens_ti -= L_plus_ti
            else:
                eT_ti = delta_ti + (L_plus_ti - tokens_ti) / CIR_ti * 1e6
                tokens_ti = 0.0

            group_eT = max(group_eT, eT_ti)

    return group_eT


def _compute_eT_block(task, q, resource):
    """Full eligible time blocking: max(individual eT, group eT) - arrival.

    Eq.(3.37) with Eq.(3.36) group ET consideration.
    """
    arrival = task.in_event_model.delta_min(q)

    # Individual eT (absolute)
    indiv_block = _compute_eligible_time_block(task, q, resource)
    indiv_eT = arrival + indiv_block

    # Group eT (absolute)
    group_eT = _compute_group_eligible_time(task, q, resource)

    # Eq.(3.36)+(3.37): take max, subtract arrival
    return max(indiv_eT, group_eT) - arrival


def _compute_eT_block_naive(task, q, resource):
    """Naive eligible time blocking: bucket-empty model.

    Assumes the token bucket is empty at the start of the busy window.
    Every frame incurs a fixed blocking of L_plus / CIR.
    No group eligible time.
    """
    L_plus = _L_plus_bits(task, resource)
    CIR = task.CIR
    if CIR <= 0:
        return 0.0
    return L_plus / CIR * 1e6


# ------------------------------------------------------------------
# ATS Scheduler
# ------------------------------------------------------------------

class ATSScheduler(analysis.Scheduler):
    """Naive CPA-based scheduler for ATS (802.1Qcr) mechanism.

    Models the ATS shaper as a pure token bucket: assumes the bucket
    is empty at the start of each busy window (worst case), so every
    frame incurs a fixed SCH blocking of L_plus / CIR.  No group
    eligible time, no token-limited interference counting.
    """

    def __init__(self):
        analysis.Scheduler.__init__(self)

    def b_plus(self, task, q, details=None, **kwargs):
        assert task.scheduling_parameter is not None
        assert task.wcet >= 0

        if model.ForwardingTask.is_forwarding_task(task):
            return q * task.wcet

        resource = task.resource
        is_ats = _is_ats(task, resource)

        if is_ats:
            for attr in ('CIR', 'CBS'):
                if not hasattr(task, attr):
                    raise ValueError(
                        f"ATS task '{task.name}' missing required parameter '{attr}'. "
                        f"Set via Task(..., {attr}=value)")

        aiq = [task.in_event_model.delta_min(q)]
        r_final = 0
        w_final = 0

        for a in aiq:
            if is_ats:
                w = self._w_ats_naive(task, q, a, resource, details, **kwargs)
            else:
                w = self._w_nats_naive(task, q, a, resource, details, **kwargs)
            r = w + task.wcet - a
            if r > r_final:
                r_final = r
                w_final = w + task.wcet

        return w_final

    def _w_ats_naive(self, task, q, a, resource, details=None, **kwargs):
        """Naive ATS: bucket-empty model, SCH = L_plus/CIR per frame."""
        L_plus = _L_plus_bits(task, resource)
        CIR = task.CIR
        # Every frame: bucket empty → wait L_plus/CIR
        eT_block = L_plus / CIR * 1e6 if CIR > 0 else 0.0
        eT_abs = a + eT_block

        lpb = 0.0
        for ti in _get_interferers(task):
            if ti.scheduling_parameter < task.scheduling_parameter:
                lpb = max(lpb, ti.wcet)

        # SPB: no token-limited count, use eta_plus only
        spb_fixed = 0.0
        src_port = _get_src_port(task)
        diff_port_flows = []
        same_port_max = {}
        for ti in _get_interferers(task):
            if ti.scheduling_parameter != task.scheduling_parameter:
                continue
            ti_port = _get_src_port(ti)
            if ti_port == src_port and ti_port is not None:
                same_port_max[ti_port] = max(same_port_max.get(ti_port, 0), ti.wcet)
            else:
                diff_port_flows.append(ti)
        spb_fixed += sum(same_port_max.values())

        w_tilde = lpb + spb_fixed
        for _ in range(1000):
            spb_diff = 0.0
            for ti in diff_port_flows:
                spb_diff += ti.in_event_model.eta_plus_closed(w_tilde) * ti.wcet

            hpb = 0.0
            for ti in _get_interferers(task):
                if ti.scheduling_parameter <= task.scheduling_parameter:
                    continue
                hpb += ti.in_event_model.eta_plus_closed(w_tilde) * ti.wcet

            w_tilde_new = lpb + spb_fixed + spb_diff + hpb
            if w_tilde == w_tilde_new:
                break
            w_tilde = w_tilde_new

        w = eT_abs + w_tilde
        if details is not None:
            details['eT_block+LPB+SPB+HPB'] = (
                f'{eT_block:.3f}+{lpb:.3f}+{spb_fixed + spb_diff:.3f}+{hpb:.3f}={w:.3f}')
        return w

    def _w_nats_naive(self, task, q, a, resource, details=None, **kwargs):
        """NATS flow: no token-limited HPB counting."""
        lpb = 0.0
        for ti in _get_interferers(task):
            if ti.scheduling_parameter < task.scheduling_parameter:
                lpb = max(lpb, ti.wcet)

        w = (q - 1) * task.wcet + lpb
        for _ in range(1000):
            spb = 0.0
            for ti in _get_interferers(task):
                if ti.scheduling_parameter == task.scheduling_parameter:
                    spb += ti.wcet * ti.in_event_model.eta_plus_closed(w)
            hpb = 0.0
            for ti in _get_interferers(task):
                if ti.scheduling_parameter <= task.scheduling_parameter:
                    continue
                hpb += ti.in_event_model.eta_plus_closed(w) * ti.wcet
            w_new = (q - 1) * task.wcet + lpb + spb + hpb
            if w == w_new:
                break
            w = w_new
        return w


class ATSSchedulerOpt(analysis.Scheduler):
    """Optimized CPA-based scheduler for ATS (802.1Qcr) mechanism.

    Compared with ATSScheduler (naive bucket-empty model), this version:
    1. Tracks per-frame token state to compute tighter eligible time blocking.
    2. Models group eligible time for same-port ATS flows.
    3. Uses token-limited interference counting: min(eta_plus, n_token).
    """

    def __init__(self):
        analysis.Scheduler.__init__(self)

    def b_plus(self, task, q, details=None, **kwargs):
        assert task.scheduling_parameter is not None
        assert task.wcet >= 0

        if model.ForwardingTask.is_forwarding_task(task):
            return q * task.wcet

        resource = task.resource
        is_ats = _is_ats(task, resource)

        if is_ats:
            for attr in ('CIR', 'CBS'):
                if not hasattr(task, attr):
                    raise ValueError(
                        f"ATS task '{task.name}' missing required parameter '{attr}'. "
                        f"Set via Task(..., {attr}=value)")

        # Build candidate arrival offsets (for same-prio interferers)
        aiq = [task.in_event_model.delta_min(q)]

        r_final = 0
        w_final = 0

        for a in aiq:
            if is_ats:
                w = self._w_ats(task, q, a, resource, details, **kwargs)
            else:
                w = self._w_nats(task, q, a, resource, details, **kwargs)

            r = w + task.wcet - a
            if r > r_final:
                r_final = r
                w_final = w + task.wcet

        return w_final

    def _w_ats(self, task, q, a, resource, details=None, **kwargs):
        """ATS flow busy window for q activations: Eq.(3.42).

        Returns w = time from busy period start to when q-th frame starts sending.

        For ATS, the eligible time blocking is per-frame. The total busy window
        is driven by the q-th frame's eligible time (absolute) plus blocking
        from other flows after the eligible time.

        w = eT_q (absolute) + LPB + SPB + HPB(w - eT_q)
        where eT_q is the absolute eligible time of the q-th frame.
        """
        eT_block = _compute_eT_block(task, q, resource)

        # eT_q absolute = arrival + eT_block
        eT_abs = a + eT_block

        # Eq.(3.9): LPB = max low-prio frame
        lpb = 0.0
        for ti in _get_interferers(task):
            if ti.scheduling_parameter < task.scheduling_parameter:
                lpb = max(lpb, ti.wcet)

        # Eq.(3.41): SPB — split into fixed (same-port) and dynamic (diff-port)
        spb_fixed = 0.0
        same_port_max = {}  # port → max wcet
        src_port = _get_src_port(task)
        diff_port_flows = []
        for ti in _get_interferers(task):
            if ti.scheduling_parameter != task.scheduling_parameter:
                continue
            ti_port = _get_src_port(ti)
            if ti_port == src_port and ti_port is not None:
                same_port_max[ti_port] = max(same_port_max.get(ti_port, 0), ti.wcet)
            else:
                diff_port_flows.append(ti)
        spb_fixed += sum(same_port_max.values())

        # HPB + dynamic SPB iteration: Eq.(3.39)-(3.41)
        # w̃ = LPB + spb_fixed + spb_diff(w̃) + HPB(w̃), then w = eT_abs + w̃
        w_tilde = lpb + spb_fixed
        for _ in range(1000):
            spb_diff = 0.0
            for ti in diff_port_flows:
                n = min(ti.in_event_model.eta_plus_closed(w_tilde),
                        _n_token(w_tilde, ti, resource))
                spb_diff += n * ti.wcet

            hpb = 0.0
            for ti in _get_interferers(task):
                if ti.scheduling_parameter <= task.scheduling_parameter:
                    continue
                if _is_ats(ti, resource):
                    n = min(ti.in_event_model.eta_plus_closed(w_tilde),
                            _n_token(w_tilde, ti, resource))
                else:
                    n = ti.in_event_model.eta_plus_closed(w_tilde)
                hpb += n * ti.wcet

            w_tilde_new = lpb + spb_fixed + spb_diff + hpb
            if w_tilde == w_tilde_new:
                break
            w_tilde = w_tilde_new

        w = eT_abs + w_tilde

        if details is not None:
            details['eT_block+LPB+SPB+HPB'] = (
                f'{eT_block:.3f}+{lpb:.3f}+{spb_fixed + spb_diff:.3f}+{hpb:.3f}={w:.3f}')
            details['q'] = str(q)

        return w

    def _w_nats(self, task, q, a, resource, details=None, **kwargs):
        """NATS flow WCRT: Eq.(3.44).

        w = LPB + SPB(w) + HPB(w)
        Standard SP with ATS-aware HPB.
        """
        # Eq.(3.9): LPB
        lpb = 0.0
        for ti in _get_interferers(task):
            if ti.scheduling_parameter < task.scheduling_parameter:
                lpb = max(lpb, ti.wcet)

        # Eq.(3.10): SPB — standard SP same-prio
        # SPB depends on w, included in iteration

        w = (q - 1) * task.wcet + lpb
        for _ in range(1000):
            spb = 0.0
            for ti in _get_interferers(task):
                if ti.scheduling_parameter == task.scheduling_parameter:
                    spb += ti.wcet * ti.in_event_model.eta_plus_closed(w)

            # Eq.(3.43): HPB with ATS token constraint
            hpb = 0.0
            for ti in _get_interferers(task):
                if ti.scheduling_parameter <= task.scheduling_parameter:
                    continue
                if _is_ats(ti, resource):
                    n = min(ti.in_event_model.eta_plus_closed(w),
                            _n_token(w, ti, resource))
                else:
                    n = ti.in_event_model.eta_plus_closed(w)
                hpb += n * ti.wcet

            w_new = (q - 1) * task.wcet + lpb + spb + hpb
            if w == w_new:
                break
            w = w_new

        if details is not None:
            details['LPB+SPB+HPB'] = f'{lpb:.3f}+{spb:.3f}+{hpb:.3f}={w:.3f}'
            details['q'] = str(q)

        return w

    def stopping_condition(self, task, q, w):
        # Per-q independent analysis: stop when response_time stops growing.
        # response_time(q) = b_plus(q) - delta_min(q)
        w_next = self.b_plus(task, q + 1)
        rt_cur = w - task.in_event_model.delta_min(q)
        rt_next = w_next - task.in_event_model.delta_min(q + 1)
        return rt_next <= rt_cur


