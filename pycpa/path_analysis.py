""" Compositional Performance Analysis Algorithms for Path Latencies

| Copyright (C) 2007-2017 Jonas Diemer, Philip Axer, Johannes Schlatow
| TU Braunschweig, Germany
| All rights reserved.
| See LICENSE file for copyright and license details.

:Authors:
         - Jonas Diemer
         - Philip Axer
         - Johannes Schlatow

Description
-----------

This module contains methods for the ananlysis of path latencies.
It should be imported in scripts that do the analysis.
"""

from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division

from . import options
from . import model
from . import util

import math


def _is_tas_path(path_tasks, task_results):
    """Return True iff every task in path_tasks is on a TSN resource with TAS for its priority.

    Checks that each task:
        - is a model.Task instance
        - exists in task_results
        - has a resource that is a TSN resource (is_tsn_resource=True)
        - uses TAS scheduling for its priority (priority_uses_tas returns True)
    """
    for t in path_tasks:
        if not isinstance(t, model.Task) or t not in task_results:
            return False
        res = getattr(t, 'resource', None)
        if res is None or not getattr(res, 'is_tsn_resource', False):
            return False
        if not res.priority_uses_tas(t.scheduling_parameter):
            return False
    return True


def _is_tas_e2e_path(path_tasks, task_results):
    """Return True iff every task in path_tasks uses TASSchedulerE2E scheduler.

    Checks that each task:
        - is a model.Task instance
        - exists in task_results
        - has a resource with a scheduler that is an instance of TASSchedulerE2E
    """
    from . import schedulers
    for t in path_tasks:
        if not isinstance(t, model.Task) or t not in task_results:
            return False
        res = getattr(t, 'resource', None)
        if res is None:
            return False
        sched = getattr(res, 'scheduler', None)
        if not isinstance(sched, schedulers.TASSchedulerE2E):
            return False
    return True


def _compute_tas_k_first(path, task_results, tas_aligned, path_tasks):
    """Compute the base gate-closed blocking count along the path.

    This function computes the initial K_actual value before accounting for
    additional blockings from cumulative non-gate-closed delays.

    Base K_actual:
        - If tas_aligned=True: 0 (first hop has no gate-closed blocking)
        - If tas_aligned=False: 1 (first hop has one gate-closed blocking)

    The final K_actual in _apply_tas_e2e_correction is:
        K_final = K_base + floor(sum_non_gate_closed / tas_window)

    where sum_non_gate_closed is the total of non-gate-closed delays across all hops.
    """
    N = len(path_tasks)
    if N == 0:
        return 0
    K_actual = 0
    if tas_aligned:
        K_actual = 0
    else:
        K_actual = 1
    return K_actual


def _apply_tas_e2e_correction(path, task_results, tasks, sum_wcrt):
    """Apply TAS E2E correction for end-to-end latency analysis.

    E2E correction is only supported with TASSchedulerE2E scheduler.
    TASScheduler does not support E2E correction or tas_aligned alignment configuration.

    Requirements for E2E correction:
        - Path must use TASSchedulerE2E scheduler (not TASScheduler)
        - path.tas_aligned must be set to True or False
        - All path tasks must have non_gate_closed and gate_closed_duration attributes

    The corrected E2E formula is:
        E2E = sum(non_gate_closed) + K_actual * G_duration

    where:
        - non_gate_closed = response_time_final + arrival_time_final - gate_closed_blocking
          (the portion of WCRT excluding gate-closed blocking)
        - G_duration = tas_cycle - tas_window (duration of one gate-closed period)
        - K_actual = K_base + floor(sum_non_gate_closed / tas_window)
        - K_base = 0 if tas_aligned=True, else 1

    This formula accounts for aligned gate-closed periods across hops, where the
    total gate-closed blocking is computed based on how many full gate-closed
    periods the cumulative non-gate-closed delay spans.

    Returns:
        Corrected E2E latency if using TASSchedulerE2E with proper configuration,
        otherwise returns sum_wcrt unchanged.
    """
    if not isinstance(path, model.Path):
        return sum_wcrt
    path_tasks = [t for t in tasks if isinstance(t, model.Task) and t in task_results]
    if not path_tasks:
        return sum_wcrt

    # Separate regular tasks from forwarding tasks.
    # TAS path/scheduler checks only apply to regular tasks; forwarding tasks
    # use a reserved negative scheduling_parameter that would fail those checks.
    regular_tasks = [t for t in path_tasks
                     if not model.ForwardingTask.is_forwarding_task(t)]
    forwarding_tasks = [t for t in path_tasks
                        if model.ForwardingTask.is_forwarding_task(t)]

    if not regular_tasks:
        return sum_wcrt

    # Check if path uses TASSchedulerE2E (required for E2E correction)
    if not _is_tas_e2e_path(regular_tasks, task_results):
        # Not using TASSchedulerE2E, no E2E correction
        return sum_wcrt

    # Check if tas_aligned is set (required for E2E correction)
    tas_aligned = getattr(path, 'tas_aligned', None)
    if tas_aligned is None:
        return sum_wcrt
    if not all(getattr(task_results[t], 'non_gate_closed', None) is not None for t in path_tasks):
        return sum_wcrt
    t0 = regular_tasks[0]
    G_duration = getattr(task_results[t0], 'gate_closed_duration', None)
    if G_duration is None or G_duration <= 0:
        return sum_wcrt

    # K_actual: actual number of gate-closed blockings along the path
    K_actual = _compute_tas_k_first(path, task_results, tas_aligned, regular_tasks)

    # Sum of non-gate-closed delay components for all hops.
    # Regular tasks contribute (WCRT - gate_closed_blocking).
    # Forwarding tasks contribute their full WCRT (no gate blocking).
    # Forwarding delay must be included because it shifts frame arrival
    # at the next hop and can cause additional gate-closed blockings.
    sum_non_gate_closed = 0
    for t in regular_tasks:
        sum_non_gate_closed += task_results[t].non_gate_closed
    for t in forwarding_tasks:
        sum_non_gate_closed += task_results[t].wcrt
    t_last = regular_tasks[-1]
    tas_window = getattr(task_results[t_last], 'tas_available_window', None)
    if tas_window is None or tas_window <= 0:
        return sum_wcrt
    K_actual += int(math.floor(sum_non_gate_closed / tas_window))
    # Corrected E2E = sum(non-gate-closed of all tasks) + K_actual * G_duration
    corrected_sum = sum_non_gate_closed + K_actual * G_duration

    return corrected_sum


def _apply_cqf_e2e_correction(path, task_results, tasks, sum_wcrt):
    """Apply CQF multi-hop E2E correction.

    For CQF streams, the packet passes through N cycle boundaries before
    the last-hop gate opens.  After the gate opens, only the local queuing
    delay (SPB + HPB + C, i.e. WCRT_last - T_CQF) remains.

    Based on Thesis Eq.(3.29)-(3.31):

        E2E = N * T_CQF + (WCRT_last - T_CQF)

    which is mathematically equivalent to (N-1)*T_CQF + WCRT_last.

    Requirements:
        - Path must be a model.Path
        - All regular (non-forwarding) tasks must use CQFPSchedulerE2E
        - All regular tasks must have cqf_cycle_time recorded in task_results

    Returns sum_wcrt unchanged when requirements are not met.
    """
    if not isinstance(path, model.Path):
        return sum_wcrt

    from . import schedulers_cqfp

    path_tasks = [t for t in tasks if isinstance(t, model.Task) and t in task_results]
    if not path_tasks:
        return sum_wcrt

    regular_tasks = [t for t in path_tasks
                     if not model.ForwardingTask.is_forwarding_task(t)]
    forwarding_tasks = [t for t in path_tasks
                        if model.ForwardingTask.is_forwarding_task(t)]

    if len(regular_tasks) < 2:
        return sum_wcrt

    # All regular tasks must use CQFPSchedulerE2E and have cqf_cycle_time
    for t in regular_tasks:
        sched = getattr(getattr(t, 'resource', None), 'scheduler', None)
        if not isinstance(sched, schedulers_cqfp.CQFPSchedulerE2E):
            return sum_wcrt
        if getattr(task_results[t], 'cqf_cycle_time', None) is None:
            return sum_wcrt

    t_cqf = task_results[regular_tasks[0]].cqf_cycle_time
    N = len(regular_tasks)
    last_hop_wcrt = task_results[regular_tasks[-1]].wcrt

    # Eq.(3.29)-(3.31): E2E = N * T_CQF + (WCRT_last - T_CQF)
    # Forwarding delay is NOT added: CQF cycle time already covers it.
    w_last_after_gate = last_hop_wcrt - t_cqf
    corrected = N * t_cqf + w_last_after_gate

    return min(sum_wcrt, corrected)


def end_to_end_latency(path, task_results, n=1 , task_overhead=0,
                       path_overhead=0, **kwargs):
    """ Computes the worst-/best-case e2e latency for n tokens to pass the path.
    The constant path.overhead is added to the best- and worst-case latencies.

    :param path: the path
    :type path: model.Path
    :param n:  amount of events
    :type n: integer
    :param task_overhead: A constant task_overhead is added once per task to both min and max latency
    :type task_overhead: integer
    :param path_overhead:  A constant path_overhead is added once per path to both min and max latency
    :type path_overhead: integer
    :rtype: tuple (best-case latency, worst-case latency)
    """

    if options.get_opt('e2e_improved') == True:
        (lmin, lmax) = end_to_end_latency_improved(path, task_results,
                                                   n, **kwargs)
    else:
        (lmin, lmax) = end_to_end_latency_classic(path, task_results,
                                                  n, **kwargs)

    for t in path.tasks:
        # implcitly check if t is a junction
        if t in task_results:
            # add per-task overheads
            lmin += task_overhead
            lmax += task_overhead

    # add per-path overhead
    lmin += path_overhead + path.overhead
    lmax += path_overhead + path.overhead

    return (lmin, lmax)

def end_to_end_latency_classic(path, task_results, n=1, injection_rate='max', **kwargs):
    """ Computes the worst-/best-case end-to-end latency
    Assumes that all tasks in the system have successfully been analyzed.
    Assumes that events enter the path at maximum/minumum rate.
    The end-to-end latency is the sum of the individual task's
    worst-case response times.

    This corresponds to Definition 7.3 in [Richter2005]_.

    :param path: the path
    :type path: model.Path
    :param n:  amount of events
    :type n: integer
    :param injection_rate: assumed injection rate is maximum or minimum
    :type injection_rate: string 'max' or 'min'
    :rtype: tuple (best case latency, worst case latency)
    """

    lmax = 0
    lmin = 0

    # check if path is a list of Tasks or a Path object
    tasks = path
    if isinstance(path, model.Path):
        tasks = path.tasks

    for t in tasks:
        # implcitly check if t is a junction
        if t in task_results:
            # sum up best- and worst-case response times
            lmax += task_results[t].wcrt
            lmin += task_results[t].bcrt
        elif isinstance(t, model.Junction):
            # add sampling delay induced by the junction (if available)
            prev_task = tasks[tasks.index(t)-1]
            if prev_task in t.analysis_results:
                lmin += t.analysis_results[prev_task].bcrt
                lmax += t.analysis_results[prev_task].wcrt
        else:
            print("Warning: no task_results for task %s" % t.name)

    # TAS E2E correction: replace sum(WCRT) with sum(WCRT) - (N - K) * G when applicable
    lmax = _apply_tas_e2e_correction(path, task_results, tasks, lmax)

    # CQF E2E correction: replace sum(WCRT) with (N-1)*T_CQF + WCRT_last when applicable
    lmax = _apply_cqf_e2e_correction(path, task_results, tasks, lmax)

    if injection_rate == 'max':
        # add the eastliest possible release of event n
        lmax += tasks[0].in_event_model.delta_min(n)

    elif injection_rate == 'min':
        # add the latest possible release of event n
        lmax += tasks[0].in_event_model.delta_plus(n)

    # add the earliest possible release of event n
    lmin += tasks[0].in_event_model.delta_min(n)

    return lmin, lmax


def _event_arrival_path(path, n, e_0=0):
    """ Returns the latest arrival time of the n-th event
    with respect to an event 0 of task 0 (first task in path)

    This is :math:`e_0(n)` from Lemma 1 in [Schliecker2009recursive]_.
    """
    # if e_0 is None:
        # the entry time of the first event

    if n > 0:
        e = e_0 + path.tasks[0].in_event_model.delta_plus(n + 1)
    elif n < 0:
        e = e_0 - path.tasks[0].in_event_model.delta_min(-n + 1)
    else:
        e = 0  # same event, so the difference is 0

    return e


def _event_exit_path(path, task_results, i, n, e_0=0):
    """ Returns the latest exit time of the n-th event
    relative to the arrival of an event 0
    (cf. Lemma 2 in [Schliecker2009recursive]_)
    In contrast to Lemma 2, k_max is set so that all busy times
    are taken into account.
    """

    # logger.debug("calculating exit for task %d, n=%d" % (i, n))

    if i == -1:
        # The exit of task -1 is the arrival of task 0.
        e = _event_arrival_path(path, n, e_0)
    elif path.tasks[i] not in task_results:
        # skip task if there are no results for this
        # (this may happen if, e.g., a chain analysis has been performed)
        return _event_exit_path(path, task_results, i-1, n, e_0)
    else:
        e = float('-inf')
        k_max = len(task_results[path.tasks[i]].busy_times)
        # print("k_max:",k_max)
        for k in range(1, k_max):
            e_k = _event_exit_path(path, task_results, i - 1, n - k + 1, e_0) + \
                    task_results[path.tasks[i]].busy_times[k]

            # print("e_k:",e_k)
            if e_k > e:
                # print("task %d, n=%d k=%d, new e=%d" % (i, n, k, e_k))
                e = e_k

    # print("exit for task %d, n=%d is %d" % (i, n, e))
    return e


def end_to_end_latency_improved(path, task_results, n=1, e_0=0, **kwargs):
    """ Performs the path analysis presented in [Schliecker2009recursive]_,
    which improves results compared to end_to_end_latency() for
    n>1 and bursty event models.
    lat(n)
    """
    lmax = 0
    lmin = 0
    lmax = _event_exit_path(path, task_results, len(path.tasks) - 1, n - 1, e_0) - e_0
    lmax = _apply_tas_e2e_correction(path, task_results, path.tasks, lmax)

    for t in path.tasks:
        if isinstance(t, model.Task) and t in task_results:
            # sum up best-case response times
            lmin += task_results[t].bcrt
        elif isinstance(t, model.Junction):
            print("Error: path contains junctions")
        else:
            print("Warning: no task_results for task %s" % t.name)

    # add the earliest possible release of event n
    # TODO: Can lmin be improved?
    lmin += path.tasks[0].in_event_model.delta_min(n)

    return lmin, lmax

def cause_effect_chain_data_age(chain, task_results, details=None):
    """ computes the data age of the given cause effect chain
    :param chain: model.EffectChain
    :param task_results: dict of analysis.TaskResult
    """
    return cause_effect_chain(chain, task_results, details, 'data-age')

def cause_effect_chain_reaction_time(chain, task_results, details=None):
    """ computes the data age of the given cause effect chain
    :param chain: model.EffectChain
    :param task_results: dict of analysis.TaskResult
    """
    return cause_effect_chain(chain, task_results, details, 'reaction-time')

def cause_effect_chain(chain, task_results, details=None, semantics='data-age'):
    """ computes the data age of the given cause effect chain
    :param chain: model.EffectChain
    :param task_results: dict of analysis.TaskResult
    """

    sequence = chain.task_sequence(writers_only=True)

    if details is None:
        details = dict()

    periods = [_period(t) for t in sequence]
    if util.GCD(periods) != min(periods):
        print("Error: cause-effect chain analysis requires harmonic periods")

    l_max = _phi(sequence[0]) + _jitter(sequence[0])
    details[sequence[0].name+'-PHI+J'] = l_max
    for i in range(len(sequence)):
        # add write-to-read delay for all but the last task
        if i < len(sequence)-1:
            if semantics == 'data-age':
                # add write to read delay
                delay = _calculate_backward_distance(sequence[i], sequence[i+1], task_results, 
                        details=details)
            elif semantics == 'reaction-time':
                delay = _calculate_forward_distance(sequence[i], sequence[i+1], task_results, 
                        details=details)
            else:
                raise NotImplementedException()

            l_max += delay

        # add read-to-write delay (response time) for all tasks
        delay = task_results[sequence[i]].wcrt
        details[sequence[i].name+'-WCRT'] = delay
        l_max += delay

    return l_max

def _phi(task):
    if hasattr(task.in_event_model, 'phi'):
        return task.in_event_model.phi
    else:
        return 0

def _period(task):
    return task.in_event_model.P

def _jitter(task):
    if hasattr(task.in_event_model, 'J'):
        return task.in_event_model.J
    else:
        return 0

def _calculate_backward_distance(writer, reader, task_results, details):
    """ computes backward distance (for data age)
    """

    if _period(reader) < _period(writer): # oversampling 

        candidates = set()

        if _period(writer) % _period(reader) != 0:
            candidates.add(_period(writer) + task_results[writer].wcrt - task_results[writer].bcrt)
        else:

            for n in range(int(math.ceil(_period(writer)/_period(reader)))):
                candidates.add(_rplus(reader, task_results, n) - _wmin(writer, task_results, 0))

                # include previous cycle?
                if _wplus(writer, task_results) > _rmin(reader, task_results, n):
                    candidates.add(_rplus(reader, task_results, n) - _wmin(writer, task_results, -1))

        result = max(candidates)

    else: # undersampling or same period

        candidates = set()
        candidates.add(_period(writer) + task_results[writer].wcrt - task_results[writer].bcrt)

        if _period(reader) % _period(writer) == 0:

            # include previous cycle?
            if _wplus(writer, task_results) > _rmin(reader, task_results):
                candidates.add(_rplus(reader, task_results) - _wmin(writer, task_results, -1))

            # include all other possible writers
            for n in range(int(math.ceil(_period(reader)/_period(writer)))):
                if _wplus(writer, task_results, n) <= _rplus(reader, task_results):
                    candidates.add(_rplus(reader, task_results) - _wmin(writer, task_results, n))

        result = min([c for c in candidates if c >= 0])

    details[writer.name+'-'+reader.name+'-delay'] = result
    return result

def _calculate_forward_distance(writer, reader, task_results, details):
    """ computes forward distance (for reaction time)
    """

    if _period(reader) < _period(writer): # oversampling 

        candidates = set()
        candidates.add(_period(reader))

        if _period(writer) % _period(reader) == 0:

            for n in range(int(math.ceil(_period(writer)/_period(reader)))):
                if _rmin(reader, task_results, n) >= _wplus(writer, task_results, 0):
                    candidates.add(_rplus(reader, task_results, n) - _wmin(writer, task_results, 0))

                # include previous cycle?
                if _wplus(writer, task_results) > _rmin(reader, task_results, n):
                    candidates.add(_rplus(reader, task_results, n) - _wmin(writer, task_results, -1))

        result = min([c for c in candidates if c >= 0])

    else: # undersampling or same period

        candidates = set()

        if _period(reader) % _period(writer) != 0:
            candidates.add(_period(reader))
        else:

            # include all possible writers
            for n in range(int(math.ceil(_period(reader)/_period(writer)))):
                candidates.add(_rplus(reader, task_results) - _wmin(writer, task_results, n))

                # if write time can be earlier than read time, add distance to next reader
                if _wplus(writer, task_results, n) > _rmin(reader, task_results):
                    candidates.add(_rplus(reader, task_results, 1) - _wmin(writer, task_results, n))

        result = max(candidates)

    details[writer.name+'-'+reader.name+'-delay'] = result
    return result

def _wplus(writer, task_results, n=0):
    return n*_period(writer) + _phi(writer) + task_results[writer].wcrt + _jitter(writer)

def _wmin(writer, task_results, n=0):
    return n*_period(writer) + _phi(writer) + task_results[writer].bcrt - _jitter(writer)

def _rplus(reader, task_results, n=0):
    return _wplus(reader, task_results, n) - task_results[reader].bcrt

def _rmin(reader, task_results, n=0):
    return n*_period(reader) + _phi(reader) - _jitter(reader)

# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
