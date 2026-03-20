"""FusionConfigOptimizer: hierarchical closed-loop parameter configuration.

Layers:
  1. Adjust TAS window sizes  → ST flows meet deadlines
  2. Adjust CQF cycle times   → CQF flows meet deadlines
  3. Derive ATS parameters     → from remaining bandwidth
  4. Shrink TAS windows        → minimize TAS occupancy (secondary optimization)
"""

import copy
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from pycpa import analysis, path_analysis, model


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class ConfigResult:
    """Output of the closed-loop configuration."""
    feasible: bool = False
    reason: str = ''
    iterations: int = 0
    # Final parameter snapshot per resource name
    params: Dict[str, dict] = field(default_factory=dict)
    # Final E2E per path name
    e2e: Dict[str, float] = field(default_factory=dict)
    # History of (iteration, {path_name: e2e}) for plotting
    history: List[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tas_priorities(resource):
    """Return list of TAS priorities on a resource."""
    if not getattr(resource, 'priority_mechanism_map', None):
        return []
    return [k for k, v in resource.priority_mechanism_map.items()
            if v == 'TAS' and not isinstance(k, tuple)]


def _cqf_pairs(resource):
    """Return list of CQF (pair, cycle_time) on a resource."""
    if not getattr(resource, 'priority_mechanism_map', None):
        return []
    pairs = []
    for k, v in resource.priority_mechanism_map.items():
        if v == 'CQF' and isinstance(k, tuple):
            ct = resource.effective_cqf_cycle_time(k[0])
            pairs.append((k, ct))
    return pairs


def _total_tas_window(resource):
    """Sum of all TAS window durations on a resource."""
    total = 0
    for p in _tas_priorities(resource):
        tw = resource.effective_tas_window_time(p)
        if tw:
            total += tw
    return total


def _flow_mechanism(task):
    """Return mechanism string for a task, or None."""
    res = task.resource
    if not getattr(res, 'is_tsn_resource', False):
        return None
    prio = task.scheduling_parameter
    if res.priority_uses_tas(prio):
        return 'TAS'
    if res.priority_uses_ats(prio):
        return 'ATS'
    if res.priority_uses_cqf(prio):
        return 'CQF'
    return None


def _path_mechanism(path):
    """Dominant mechanism of a path (from first non-forwarding task)."""
    for t in path.tasks:
        if model.ForwardingTask.is_forwarding_task(t):
            continue
        return _flow_mechanism(t)
    return None


# ---------------------------------------------------------------------------
# Optimizer
# ---------------------------------------------------------------------------

class FusionConfigOptimizer:
    """Hierarchical closed-loop parameter configuration for TSN fusion.

    Parameters
    ----------
    system : model.System
    deadlines : dict
        {path: deadline_value} for paths that have deadline constraints.
    bw_min : float, optional
        Minimum bandwidth (in time units per cycle) for BE/NC traffic.
        Expressed as: required open_time per TAS cycle after subtracting
        TAS windows and guard band.  If None, no bandwidth constraint.
    tas_step : float
        Step size for TAS window adjustment (default 1.0).
    cqf_candidates : list of float, optional
        Candidate CQF cycle times in descending order.
        If None, uses [current, current/2, current/4, ...].
    max_iterations : int
        Maximum iterations per layer (default 100).
    """

    def __init__(self, system, deadlines, bw_min=None, tas_step=1.0,
                 cqf_candidates=None, max_iterations=100,
                 bisection=True):
        self.system = system
        self.deadlines = deadlines  # {path: deadline}
        self.bw_min = bw_min
        self.tas_step = tas_step
        self.cqf_candidates = cqf_candidates
        self.max_iter = max_iterations
        self.bisection = bisection
        self._history = []
        self._total_iters = 0

    # ------------------------------------------------------------------
    # Core: evaluate
    # ------------------------------------------------------------------

    def _evaluate(self):
        """Run WCRT analysis + path E2E.  Returns {path: (lmin, lmax)}.
        Returns None if analysis fails (e.g. non-convergent busy window).
        """
        try:
            task_results = analysis.analyze_system(self.system)
        except (AssertionError, ValueError):
            return None
        e2e = {}
        for p in self.deadlines:
            e2e[p] = path_analysis.end_to_end_latency(p, task_results)
        self._total_iters += 1
        self._history.append({p.name: e2e[p][1] for p in e2e})
        return e2e

    # ------------------------------------------------------------------
    # Constraint checks
    # ------------------------------------------------------------------

    def _violating_paths(self, e2e, mechanism=None):
        """Return list of (path, lmax, deadline, slack) for violated paths."""
        violations = []
        for p, dl in self.deadlines.items():
            if mechanism and _path_mechanism(p) != mechanism:
                continue
            lmax = e2e[p][1]
            if lmax > dl:
                violations.append((p, lmax, dl, lmax - dl))
        return sorted(violations, key=lambda x: -x[3])  # worst first

    def _all_satisfied(self, e2e, mechanism=None):
        return len(self._violating_paths(e2e, mechanism)) == 0

    def _check_bw(self):
        """Check BE bandwidth constraint on all resources."""
        if self.bw_min is None:
            return True, ''
        for r in self.system.resources:
            if not getattr(r, 'is_tsn_resource', False):
                continue
            tc = r.tas_cycle_time
            if not tc or tc <= 0:
                continue
            tw_sum = _total_tas_window(r)
            # guard band estimate: use resource attribute or 0
            gb = getattr(r, 'guard_band', 0) or 0
            open_time = tc - tw_sum - gb
            if open_time < self.bw_min:
                return False, 'BW insufficient on %s: open=%.1f < min=%.1f' % (
                    r.name, open_time, self.bw_min)
        return True, ''

    def _check_cqf_clearable(self, resource, pair):
        """CQF clearable: effective open time per CQF cycle >= max load."""
        t_cqf = resource.effective_cqf_cycle_time(pair[0])
        if not t_cqf or t_cqf <= 0:
            return False
        tc = resource.tas_cycle_time or t_cqf
        tw_sum = _total_tas_window(resource)
        gb = getattr(resource, 'guard_band', 0) or 0
        # How many TAS closures per CQF cycle
        n_closures = max(1, t_cqf / tc) if tc > 0 else 1
        open_per_cqf = t_cqf - n_closures * (tw_sum + gb)
        if open_per_cqf <= 0:
            return False
        # Max CQF load in one cycle
        max_load = 0
        for t in resource.tasks:
            if model.ForwardingTask.is_forwarding_task(t):
                continue
            if resource.priority_uses_cqf(t.scheduling_parameter):
                p = t.scheduling_parameter
                if isinstance(pair, tuple) and p in pair:
                    max_load += t.wcet
        return open_per_cqf >= max_load

    def _check_unschedulable(self, resource=None):
        """Check if current config is fundamentally unschedulable."""
        bw_ok, reason = self._check_bw()
        if not bw_ok:
            return True, reason
        resources = [resource] if resource else self.system.resources
        for r in resources:
            if not getattr(r, 'is_tsn_resource', False):
                continue
            for pair, _ in _cqf_pairs(r):
                if not self._check_cqf_clearable(r, pair):
                    return True, 'CQF not clearable on %s pair %s' % (
                        r.name, pair)
        return False, ''

    # ------------------------------------------------------------------
    # Parameter snapshot / restore
    # ------------------------------------------------------------------

    def _snapshot(self):
        """Save current parameters of all TSN resources and ATS tasks."""
        snap = {}
        for r in self.system.resources:
            if not getattr(r, 'is_tsn_resource', False):
                continue
            snap[r.name] = {
                'tas_cycle_time': r.tas_cycle_time,
                'tas_window_time_by_priority': copy.deepcopy(
                    r.tas_window_time_by_priority),
                'cqf_cycle_time': r.cqf_cycle_time,
                'cqf_cycle_time_by_pair': copy.deepcopy(
                    r.cqf_cycle_time_by_pair),
            }
            # ATS task params
            for t in r.tasks:
                if hasattr(t, 'CIR'):
                    snap[('ats', t.name)] = (t.CIR, getattr(t, 'CBS', None))
        return snap

    def _restore(self, snap):
        """Restore parameters from snapshot."""
        for r in self.system.resources:
            if r.name not in snap:
                continue
            s = snap[r.name]
            r.tas_cycle_time = s['tas_cycle_time']
            r.tas_window_time_by_priority = copy.deepcopy(
                s['tas_window_time_by_priority'])
            r.cqf_cycle_time = s['cqf_cycle_time']
            r.cqf_cycle_time_by_pair = copy.deepcopy(
                s['cqf_cycle_time_by_pair'])
            for t in r.tasks:
                key = ('ats', t.name)
                if key in snap:
                    t.CIR, t.CBS = snap[key]

    # ------------------------------------------------------------------
    # Layer 1: TAS window adjustment
    # ------------------------------------------------------------------

    def _layer1_tas_window(self):
        """Increase TAS windows until all ST flows meet deadlines.

        If ``self.bisection`` is True, uses bisection refinement:
        start with a large step, increase until feasible, back off,
        halve the step, and repeat until the minimum granularity
        ``self.tas_step``.  Otherwise, uses a fixed step size.
        """
        if not self.bisection:
            return self._layer1_fixed_step()

        step = max(self.tas_step, 50)  # start coarse

        while step >= self.tas_step:
            # Increase until feasible or budget exhausted
            for _ in range(self.max_iter):
                e2e = self._evaluate()
                if e2e is None:
                    return None
                violations = self._violating_paths(e2e, mechanism='TAS')
                if not violations:
                    break

                unsched, _ = self._check_unschedulable()
                if unsched:
                    return None

                self._bump_tas_windows(violations[0][0], step)
                self._total_iters += 1
            else:
                return None  # max iterations exhausted

            if step <= self.tas_step:
                break  # finest granularity reached, done

            # Back off one step and refine
            self._bump_tas_windows(violations[0][0] if violations else None,
                                   -step, all_resources=True)
            step = max(step // 2, self.tas_step)

        # Final feasibility check
        e2e = self._evaluate()
        if e2e is None:
            return None
        if self._violating_paths(e2e, mechanism='TAS'):
            return None
        return e2e

    def _bump_tas_windows(self, path, step, all_resources=False):
        """Adjust TAS windows by ``step`` on resources along ``path``.
        If ``all_resources`` is True, adjust all TAS-enabled resources
        (used for uniform back-off after bisection).
        """
        targets = []
        if all_resources:
            for r in self.system.resources:
                if not getattr(r, 'is_tsn_resource', False):
                    continue
                if not r.tas_window_time_by_priority:
                    continue
                for prio in list(r.tas_window_time_by_priority):
                    if r.priority_uses_tas(prio):
                        targets.append((r, prio))
        elif path is not None:
            for task in path.tasks:
                if model.ForwardingTask.is_forwarding_task(task):
                    continue
                r = task.resource
                if not getattr(r, 'is_tsn_resource', False):
                    continue
                prio = task.scheduling_parameter
                if not r.priority_uses_tas(prio):
                    continue
                targets.append((r, prio))

        for r, prio in targets:
            if r.tas_window_time_by_priority is None:
                r.tas_window_time_by_priority = {}
            cur = r.effective_tas_window_time(prio) or 0
            r.tas_window_time_by_priority[prio] = max(0, cur + step)

        self._sync_tas_windows()

    def _layer1_fixed_step(self):
        """Fixed-step Layer 1 (for comparison experiments)."""
        for _ in range(self.max_iter):
            e2e = self._evaluate()
            if e2e is None:
                return None
            violations = self._violating_paths(e2e, mechanism='TAS')
            if not violations:
                return e2e
            unsched, _ = self._check_unschedulable()
            if unsched:
                return None
            self._bump_tas_windows(violations[0][0], self.tas_step)
            self._total_iters += 1
        return None

    def _sync_chain_params(self):
        """Ensure TAS window and CQF cycle consistency across multi-hop chains.

        The E2E analysis (Theorems 4,5) requires uniform parameters along a
        chain.  With port-level resources each port is independent, so we
        synchronize after any parameter change: TAS windows take the max,
        CQF cycles take the min (most aggressive).

        Runs until convergence because shared resources may propagate
        changes across multiple paths.
        """
        for _round in range(20):  # convergence guard
            changed = False
            for path in self.system.paths:
                tsn_tasks = [(t, t.resource) for t in path.tasks
                             if not model.ForwardingTask.is_forwarding_task(t)
                             and getattr(t.resource, 'is_tsn_resource', False)]
                if len(tsn_tasks) < 2:
                    continue

                # TAS window sync (max)
                tas = [(t, r) for t, r in tsn_tasks
                       if r.priority_uses_tas(t.scheduling_parameter)]
                if len(tas) >= 2:
                    prio = tas[0][0].scheduling_parameter
                    max_w = max(r.effective_tas_window_time(prio) or 0
                                for _, r in tas)
                    for _, r in tas:
                        if r.tas_window_time_by_priority is None:
                            r.tas_window_time_by_priority = {}
                        cur = r.effective_tas_window_time(prio) or 0
                        if cur != max_w:
                            r.tas_window_time_by_priority[prio] = max_w
                            changed = True

                # CQF cycle sync (min)
                cqf = [(t, r) for t, r in tsn_tasks
                       if r.priority_uses_cqf(t.scheduling_parameter)]
                if len(cqf) >= 2:
                    prio = cqf[0][0].scheduling_parameter
                    min_c = min(r.effective_cqf_cycle_time(prio)
                                for _, r in cqf)
                    for _, r in cqf:
                        pair = r.get_cqf_pair_for_priority(prio)
                        if pair and r.cqf_cycle_time_by_pair is not None:
                            cur = r.cqf_cycle_time_by_pair.get(pair)
                            if cur != min_c:
                                r.cqf_cycle_time_by_pair[pair] = min_c
                                changed = True
            if not changed:
                break

    # backward compat alias
    _sync_tas_windows = _sync_chain_params

    # ------------------------------------------------------------------
    # Layer 2: CQF cycle adjustment
    # ------------------------------------------------------------------

    def _layer2_cqf_cycle(self, e2e):
        """Decrease CQF cycle times until CQF flows meet deadlines."""
        if e2e is None:
            return None

        for _ in range(self.max_iter):
            violations = self._violating_paths(e2e, mechanism='CQF')
            if not violations:
                return e2e

            # Find resources with CQF along worst path
            worst_path = violations[0][0]
            adjusted = False
            for task in worst_path.tasks:
                if model.ForwardingTask.is_forwarding_task(task):
                    continue
                r = task.resource
                if not getattr(r, 'is_tsn_resource', False):
                    continue
                prio = task.scheduling_parameter
                if not r.priority_uses_cqf(prio):
                    continue

                pair = r.get_cqf_pair_for_priority(prio)
                if pair is None:
                    continue

                cur_cqf = r.effective_cqf_cycle_time(prio)
                candidates = self._get_cqf_candidates(cur_cqf)
                for new_cqf in candidates:
                    if new_cqf >= cur_cqf:
                        continue
                    # Set new CQF cycle
                    if r.cqf_cycle_time_by_pair is None:
                        r.cqf_cycle_time_by_pair = {}
                    r.cqf_cycle_time_by_pair[pair] = new_cqf
                    # Link GCL cycle: T_GCL = M * T_CQF
                    self._link_gcl_cycle(r, new_cqf)
                    # Check clearable
                    if self._check_cqf_clearable(r, pair):
                        adjusted = True
                        break
                    # Revert this candidate
                    r.cqf_cycle_time_by_pair[pair] = cur_cqf
                    self._link_gcl_cycle(r, cur_cqf)

            if not adjusted:
                return e2e  # can't improve further

            self._sync_chain_params()
            e2e = self._evaluate()
            if e2e is None:
                return None

        return e2e

    def _get_cqf_candidates(self, current):
        """Return candidate CQF cycle times smaller than current."""
        if self.cqf_candidates:
            return [c for c in self.cqf_candidates if c < current]
        # Default: halving
        candidates = []
        v = current / 2
        while v >= 1:
            candidates.append(v)
            v /= 2
        return candidates

    def _link_gcl_cycle(self, resource, new_cqf):
        """Adjust GCL cycle so that cqf_cycle / tas_cycle is 1 or even integer.

        Constraint: T_CQF >= T_GCL, and T_CQF / T_GCL ∈ {1, 2, 4, 6, ...}.
        When CQF shrinks below current TAS cycle, TAS cycle must shrink too.
        """
        if not resource.tas_cycle_time or new_cqf <= 0:
            return
        old_tas = resource.tas_cycle_time
        if new_cqf >= old_tas:
            # Check ratio is valid (1 or even integer)
            ratio = new_cqf / old_tas
            if ratio >= 1 and (ratio == int(ratio)) and (int(ratio) == 1 or int(ratio) % 2 == 0):
                return  # already valid
        # Set TAS cycle = CQF cycle (ratio = 1, always valid)
        resource.tas_cycle_time = new_cqf

    # ------------------------------------------------------------------
    # Layer 3: ATS parameter derivation
    # ------------------------------------------------------------------

    def _layer3_ats_params(self, e2e):
        """Derive ATS CIR/CBS from remaining bandwidth.

        CIR (bits/s), CBS (bits). Allocate proportionally to flow demands.
        """
        if e2e is None:
            return None

        for r in self.system.resources:
            if not getattr(r, 'is_tsn_resource', False):
                continue
            tc = r.tas_cycle_time
            if not tc or tc <= 0:
                continue

            tw_sum = _total_tas_window(r)
            gb = getattr(r, 'guard_band', 0) or 0
            open_time = tc - tw_sum - gb
            if open_time <= 0:
                continue

            linkspeed = getattr(r, 'linkspeed', 1e9)
            available_bps = linkspeed * (open_time / tc)

            ats_tasks = []
            total_demand = 0
            for t in r.tasks:
                if model.ForwardingTask.is_forwarding_task(t):
                    continue
                if r.priority_uses_ats(t.scheduling_parameter):
                    em = t.in_event_model
                    period = getattr(em, 'P', None) or getattr(em, 'T', None)
                    # Multi-hop: inherit period from chain source
                    if period is None or period <= 0:
                        src = t
                        while getattr(src, 'prev_task', None):
                            src = src.prev_task
                        if src.in_event_model:
                            period = getattr(src.in_event_model, 'P', None
                                ) or getattr(src.in_event_model, 'T', None)
                    frame_bits = t.wcet * linkspeed * 1e-6
                    demand = frame_bits / (period * 1e-6) if (
                        period and period > 0) else 0
                    ats_tasks.append((t, demand))
                    total_demand += demand

            if not ats_tasks or total_demand <= 0:
                continue

            for t, demand in ats_tasks:
                ratio = demand / total_demand
                cir = max(available_bps * ratio, demand)
                frame_bits = t.wcet * linkspeed * 1e-6
                t.CIR = cir
                t.CBS = max(frame_bits, cir * 1e-3)

        return self._evaluate()

    # ------------------------------------------------------------------
    # Layer 4: TAS window recovery (secondary optimization)
    # ------------------------------------------------------------------

    def _layer4_tas_shrink(self, e2e):
        """Shrink TAS windows while all constraints remain satisfied.

        Uses bisection: start with a large step, shrink until infeasible,
        back off, halve the step, and repeat until minimum granularity.
        Only feasible states are recorded in history.
        """
        if e2e is None:
            return None

        step = max(self.tas_step, 50)  # start coarse

        while step >= self.tas_step:
            for _ in range(self.max_iter):
                saved = self._snapshot()

                shrunk = False
                for r in self.system.resources:
                    if not getattr(r, 'is_tsn_resource', False):
                        continue
                    for prio in _tas_priorities(r):
                        cur = r.effective_tas_window_time(prio)
                        if cur is None or cur <= step:
                            continue
                        if r.tas_window_time_by_priority is None:
                            continue
                        r.tas_window_time_by_priority[prio] = cur - step
                        shrunk = True

                if not shrunk:
                    break

                self._sync_tas_windows()

                # Trial evaluation — only record if feasible
                try:
                    task_results = analysis.analyze_system(self.system)
                except (AssertionError, ValueError):
                    self._restore(saved)
                    break
                trial_e2e = {}
                for p in self.deadlines:
                    trial_e2e[p] = path_analysis.end_to_end_latency(
                        p, task_results)
                self._total_iters += 1

                feasible = all(trial_e2e[p][1] <= dl
                               for p, dl in self.deadlines.items())
                if not feasible:
                    self._restore(saved)
                    break

                # Feasible — commit to history
                self._history.append(
                    {p.name: trial_e2e[p][1] for p in trial_e2e})
                e2e = trial_e2e

            if step <= self.tas_step:
                break
            step = max(step // 2, self.tas_step)

        return e2e

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def optimize(self):
        """Run the full 4-layer closed-loop configuration.

        Returns
        -------
        ConfigResult
        """
        self._history = []
        self._total_iters = 0

        # Layer 1: TAS windows
        e2e = self._layer1_tas_window()
        if e2e is None:
            return ConfigResult(feasible=False,
                                reason='Layer 1: ST unschedulable',
                                iterations=self._total_iters,
                                history=self._history)

        # Layer 2: CQF cycles
        e2e = self._layer2_cqf_cycle(e2e)
        if e2e is None:
            return ConfigResult(feasible=False,
                                reason='Layer 2: CQF unschedulable',
                                iterations=self._total_iters,
                                history=self._history)

        # Layer 3: ATS params
        e2e = self._layer3_ats_params(e2e)

        # Layer 4: TAS shrink
        e2e = self._layer4_tas_shrink(e2e)

        # Check final feasibility
        if e2e is None:
            return ConfigResult(feasible=False,
                                reason='Final evaluation failed',
                                iterations=self._total_iters,
                                history=self._history)

        all_ok = self._all_satisfied(e2e)

        # Build result
        result = ConfigResult(
            feasible=all_ok,
            reason='' if all_ok else 'Some paths still violate deadlines',
            iterations=self._total_iters,
            history=self._history,
        )
        # Record final params
        for r in self.system.resources:
            if not getattr(r, 'is_tsn_resource', False):
                continue
            result.params[r.name] = {
                'tas_cycle_time': r.tas_cycle_time,
                'tas_window_time_by_priority': copy.deepcopy(
                    r.tas_window_time_by_priority),
                'cqf_cycle_time': r.cqf_cycle_time,
                'cqf_cycle_time_by_pair': copy.deepcopy(
                    r.cqf_cycle_time_by_pair),
            }
        # Record final E2E
        for p in e2e:
            result.e2e[p.name] = e2e[p][1]

        return result
