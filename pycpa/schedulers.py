"""
| Copyright (C) 2017 Philip Axer, Jonas Diemer, Johannes Schlatow
| TU Braunschweig, Germany
| All rights reserved.
| See LICENSE file for copyright and license details.

:Authors:
         - Jonas Diemer
         - Philip Axer
         - Johannes Schlatow

Description
-----------

Local analysis functions (schedulers)
"""
from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division

import itertools
import math
import logging

from . import analysis
from . import options
from . import model

logger = logging.getLogger("pycpa")

EPSILON = 1e-9

# priority orderings
prio_high_wins_equal_fifo = lambda a, b : a >= b
prio_low_wins_equal_fifo = lambda a, b : a <= b
prio_high_wins_equal_domination = lambda a, b : a > b
prio_low_wins_equal_domination = lambda a, b : a < b

class RoundRobinScheduler(analysis.Scheduler):
    """ Round-Robin Scheduler

    task.scheduling_parameter is the respective slot size
    """

    def b_plus(self, task, q, details=None, **kwargs):
        w = q * task.wcet
        # print "q=",q
        while True:
            s = 0
            for ti in task.get_resource_interferers():
                # print "sum+=min(",q,",",ti.in_event_model.eta_plus(w)
                # s += min(q, ti.eta_plus(w))
                if hasattr(task, "scheduling_parameter") and task.scheduling_parameter is not None:
                    s += min(int(math.ceil(float(q) * task.wcet / task.scheduling_parameter)) * ti.scheduling_parameter,
                         ti.in_event_model.eta_plus(w) * ti.wcet)
                else:
                    # Assume cooperative round robin
                    s += ti.wcet * min(q, ti.in_event_model.eta_plus(w))

            # print "w=",q,"+",sum, ", eta_plus(w)=", task.in_event_model.eta_plus(q+sum)
            w_new = q * task.wcet + s

            if w == w_new:
                if details is not None:
                    details['q*WCET'] = str(q) + '*' + str(task.wcet) + '=' + str(q * task.wcet)

                    for ti in task.get_resource_interferers():
                        if hasattr(task, "scheduling_parameter") and task.scheduling_parameter is not None:
                            if int(math.ceil(float(q) * task.wcet / task.scheduling_parameter)) * ti.scheduling_parameter < ti.in_event_model.eta_plus(w) * ti.wcet:
                                details[str(ti)] = '%d*%d' % \
                                    (int(math.ceil(float(q) * task.wcet / task.scheduling_parameter)),
                                     ti.scheduling_parameter)
                            else:
                                details[str(ti)] = '%d*%d' % (ti.in_event_model.eta_plus(w), ti.wcet)
                        else:
                            details[str(ti)] = "%d*min(%d,%d)=%d*%d" % \
                                (ti.wcet, q, ti.in_event_model.eta_plus(w),
                                 ti.wcet, min(q, ti.in_event_model.eta_plus(w)))
                return w
            w = w_new


class SPNPScheduler(analysis.Scheduler):
    """ Static-Priority-Non-Preemptive Scheduler

    Priority is stored in task.scheduling_parameter,
    by default numerically lower numbers have a higher priority

    Policy for equal priority is FCFS (i.e. max. interference).
    """

    def __init__(self, priority_cmp=prio_low_wins_equal_fifo, ctx_switch_overhead=0, cycle_time=EPSILON):
        """
        :param priority_cmp: function to evaluate priority comparison of the form foo(a,b). if foo(a,b) == True, then "a" is more important than "b"
        :param cycle_time: time granularity of the scheduler, see [Bate1998]_ E.q. 4.14
        :param ctx_switch_overhead: context switching overhead (or interframe space for transmission lines)
        """
        analysis.Scheduler.__init__(self)

        # # time granularity of the scheduler
        self.cycle_time = cycle_time

        # # Context-switch overhead
        self.ctx_switch_overhead = ctx_switch_overhead

        # # priority ordering
        self.priority_cmp = priority_cmp

    def _blocker(self, task):
        # find maximum lower priority blocker
        b = 0
        for ti in task.get_resource_interferers():
            if self.priority_cmp(ti.scheduling_parameter, task.scheduling_parameter) == False:
                b = max(b, ti.wcet)
        return b

    def spnp_busy_period(self, task, w):
        """ Calculated the busy period of the current task
        """
        b = self._blocker(task) + self.ctx_switch_overhead
        w = max(b, w)

        while True:
            w_new = b
            for ti in task.get_resource_interferers() | set([task]):
                if self.priority_cmp(ti.scheduling_parameter, task.scheduling_parameter) or (ti == task):
                    w_new += (ti.wcet + self.ctx_switch_overhead) * ti.in_event_model.eta_plus(w)

            if w == w_new:
                break

            w = w_new

        return w

    def stopping_condition(self, task, q, w):
        """ Check if we have looked far enough
            compute the time the resource is busy processing q activations of task
            and activations of all higher priority tasks during that time
            Returns True if stopping-condition is satisfied, False otherwise
        """

        # if there are no new activations when the current busy period has been completed, we terminate
        if task.in_event_model.delta_min(q + 1) >= self.spnp_busy_period(task, w):
            return True
        return False


    def b_plus(self, task, q, details=None, **kwargs):
        """ Return the maximum time required to process q activations
        """
        assert(task.scheduling_parameter != None)
        assert(task.wcet >= 0)

        b = self._blocker(task) + self.ctx_switch_overhead

        w = (q - 1) * (task.wcet + self.ctx_switch_overhead) + b

        while True:
            # logging.debug("w: %d", w)
            # logging.debug("e: %d", q * task.wcet)
            s = 0
            # logging.debug(task.name+" interferers "+ str([i.name for i in task.get_resource_interferers()]))
            for ti in task.get_resource_interferers():
                assert(ti.scheduling_parameter != None)
                assert(ti.resource == task.resource)
                if self.priority_cmp(ti.scheduling_parameter, task.scheduling_parameter):  # equal priority also interferes (FCFS)
                    s += (ti.wcet + self.ctx_switch_overhead) * ti.in_event_model.eta_plus(w + self.cycle_time)
                    # logging.debug("e: %s %d x %d", ti.name, ti.wcet, ti.in_event_model.eta_plus(w))

            w_new = (q - 1) * (task.wcet + self.ctx_switch_overhead) + b + s
            # print ("w_new: ", w_new)
            if w == w_new:

                if details is not None:
                    details['q*WCET'] = str(q) + '*' + str(task.wcet) + '=' + str(q * task.wcet)
                    details['blocker'] = str(b)
                    for ti in task.get_resource_interferers():
                        if self.priority_cmp(ti.scheduling_parameter, task.scheduling_parameter):
                            details[str(ti) + ':eta*WCET'] = str(ti.in_event_model.eta_plus(w + self.cycle_time)) + '*'\
                                + str(ti.wcet) + '=' + str((ti.wcet + self.ctx_switch_overhead) * ti.in_event_model.eta_plus(w + self.cycle_time))
                w += task.wcet
                assert(w >= q * task.wcet)
                return w
            w = w_new


class SPPScheduler(analysis.Scheduler):
    """ Static-Priority-Preemptive Scheduler

    Priority is stored in task.scheduling_parameter,
    by default numerically lower numbers have a higher priority

    Policy for equal priority is FCFS (i.e. max. interference).
    """


    def __init__(self, priority_cmp=prio_low_wins_equal_fifo):
        analysis.Scheduler.__init__(self)

        # # priority ordering
        self.priority_cmp = priority_cmp

    def b_plus(self, task, q, details=None, **kwargs):
        """ This corresponds to Theorem 1 in [Lehoczky1990]_ or Equation 2.3 in [Richter2005]_. """
        assert(task.scheduling_parameter != None)
        assert(task.wcet >= 0)

        w = q * task.wcet

        while True:
            # logging.debug("w: %d", w)
            # logging.debug("e: %d", q * task.wcet)
            s = 0
            # logging.debug(task.name+" interferers "+ str([i.name for i in task.get_resource_interferers()]))
            for ti in task.get_resource_interferers():
                assert(ti.scheduling_parameter != None)
                assert(ti.resource == task.resource)
                if self.priority_cmp(ti.scheduling_parameter, task.scheduling_parameter):  # equal priority also interferes (FCFS)
                    s += ti.wcet * ti.in_event_model.eta_plus(w)
                    # logging.debug("e: %s %d x %d", ti.name, ti.wcet, ti.in_event_model.eta_plus(w))

            w_new = q * task.wcet + s
            # print ("w_new: ", w_new)
            if w == w_new:
                assert(w >= q * task.wcet)
                if details is not None:
                    details['q*WCET'] = str(q) + '*' + str(task.wcet) + '=' + str(q * task.wcet)
                    for ti in task.get_resource_interferers():
                        if self.priority_cmp(ti.scheduling_parameter, task.scheduling_parameter):
                            details[str(ti) + ':eta*WCET'] = str(ti.in_event_model.eta_plus(w)) + '*'\
                                + str(ti.wcet) + '=' + str(ti.wcet * ti.in_event_model.eta_plus(w))
                return w

            w = w_new

class SPPSchedulerActivationOffsets(SPPScheduler):
    """ Static-Priority-Preemptive Scheduler which considers activation offsets assuming
        all tasks are activated synchronously with the given offsets/phases (phi).

        Assumptions:
            * implicit or constrained deadlines

        We exclude/shift interferers whose phase is larger than the task under analysis iff the interferers period is
        equal or smaller.
    """


    def __init__(self, priority_cmp=prio_low_wins_equal_fifo):
        SPPScheduler.__init__(self, priority_cmp)

    def b_plus(self, task, q, details=None, **kwargs):
        """ This corresponds to Theorem 1 in [Lehoczky1990]_ or Equation 2.3 in [Richter2005]_. """
        assert(task.scheduling_parameter != None)
        assert(task.wcet >= 0)

        w = q * task.wcet

        while True:
            s = 0
            for ti in task.get_resource_interferers():
                assert(ti.scheduling_parameter != None)
                assert(ti.resource == task.resource)
                if self.priority_cmp(ti.scheduling_parameter, task.scheduling_parameter):  # equal priority also interferes (FCFS)
                    if hasattr(ti.in_event_model, 'P') and hasattr(task.in_event_model, 'P') and \
                        ti.in_event_model.P <= task.in_event_model.P and \
                        task.in_event_model.P % ti.in_event_model.P == 0:
                            diff = task.in_event_model.phi - ti.in_event_model.phi
                    else:
                        diff = ti.in_event_model.J

                    s += ti.wcet * ti.in_event_model.eta_plus(w + diff)

            w_new = q * task.wcet + s
            if w == w_new:
                assert(w >= q * task.wcet)
                if details is not None:
                    details['q*WCET'] = str(q) + '*' + str(task.wcet) + '=' + str(q * task.wcet)
                    for ti in task.get_resource_interferers():
                        if self.priority_cmp(ti.scheduling_parameter, task.scheduling_parameter):
                            if hasattr(ti.in_event_model, 'P') and hasattr(task.in_event_model, 'P') and \
                                ti.in_event_model.P <= task.in_event_model.P and \
                                task.in_event_model.P % ti.in_event_model.P == 0:
                                    diff = task.in_event_model.phi - ti.in_event_model.phi
                            else:
                                diff = ti.in_event_model.J

                            details[str(ti) + ':eta*WCET'] = str(ti.in_event_model.eta_plus(w+diff)) + '*'\
                                + str(ti.wcet) + '=' + str(ti.wcet * ti.in_event_model.eta_plus(w+diff))
                return w

            if q > 1:
                logger.warning("Using SPPSchedulerActivationOffset() with deadline > period (task %s)." % (task))

            w = w_new

class CorrelatedDeltaMin(model.EventModel):
    """ Computes the correlated event model :math:`\delta^-_j` from Lemma 2 in [Rox2010]_.
    """
    def __init__(self, em, m, offset):
        model.EventModel.__init__(self, 'tmp')

        self.em = em
        self.m = m
        self.offset = offset

    def deltamin_func(self, n):
        if n <= self.m:
            return self.em.deltamin_func(n)
        elif n == self.m + 1:
            return max(self.em.deltamin_func(n), self.offset)
        else:
            return max(self.em.deltamin_func(n), self.offset + self.em.deltamin_func(n - self.m))

    def deltaplus_func(self, n):
        return self.em.deltaplus_func(n)

class SPPSchedulerCorrelatedRox(SPPScheduler):
    """ SPP scheduler with dmin correlation.
        Computes the approximate response time bound as presented in [Rox2010]_.
    """

    def get_dependent_tasks(self, task):
        return task.get_resource_interferers()

    def b_plus_idle(self, task, q, details=None, task_results=None):
        """ Implements Case 2 in [Rox2010]_.
        """
        assert(task.scheduling_parameter != None)
        assert(task.wcet >= 0)

        w = q * task.wcet
        while True:
            details.clear()
            details['q*WCET'] = str(q) + '*' + str(task.wcet) + '=' + str(q * task.wcet)

            idle_intrf = 0
            idle_details = dict()

            for ti in task.get_resource_interferers():
                assert(ti.scheduling_parameter != None)
                assert(ti.resource == task.resource)
                if self.priority_cmp(ti.scheduling_parameter, task.scheduling_parameter):  # equal priority also interferes (FCFS)

                    idle_intrf += ti.wcet * ti.in_event_model.eta_plus(w-ti.in_event_model.correlated_dmin(task))
                    idle_details[str(ti)+':eta*WCET'] = str(ti.in_event_model.eta_plus(w-ti.in_event_model.correlated_dmin(task))) + '*' +\
                            str(ti.wcet) + '=' + str(ti.wcet * ti.in_event_model.eta_plus(w-ti.in_event_model.correlated_dmin(task)))

            w_new = q * task.wcet + idle_intrf
            for d in idle_details.keys():
                details[d] = idle_details[d]

            if w == w_new:
                break
            w = w_new

        assert(w >= q * task.wcet)
        return w

    def b_plus_busy(self, task, q, details=None, task_results=None):
        """ Implements Case 1 in [Rox2010]_.
        """
        assert(task.scheduling_parameter != None)
        assert(task.wcet >= 0)

        w = q * task.wcet
        while True:
            details.clear()
            details['q*WCET'] = str(q) + '*' + str(task.wcet) + '=' + str(q * task.wcet)

            busy_intrf = 0
            busy_details = dict()

            interferers = set()
            for ti in task.get_resource_interferers():
                assert(ti.scheduling_parameter != None)
                assert(ti.resource == task.resource)
                if self.priority_cmp(ti.scheduling_parameter, task.scheduling_parameter):  # equal priority also interferes (FCFS)
                    interferers.add(ti)

            for ti in interferers:

                # ti starts busy window -> iterate candidates of task's first arrival
                qmax = len(task_results[ti].busy_times)
                for q in range(1, qmax):
                    intrf = 0
                    intrf_details = dict()
                    a0 = ti.in_event_model.delta_min(q) + task.in_event_model.correlated_dmin(ti)

                    for tj in interferers:
                        if tj is ti:
                            mj = q
                        else:
                            mj = tj.in_event_model.eta_plus(a0 - task.in_event_model.correlated_dmin(ti))

                        em = CorrelatedDeltaMin(tj.in_event_model, mj, a0 + tj.in_event_model.correlated_dmin(task))
                        intrf += tj.wcet * em.eta_plus(w + a0)
                        intrf_details[str(tj)+':eta*WCET'] = str(em.eta_plus(w+a0)) + '+' + str(tj.wcet) +\
                                '=' + str(tj.wcet * em.eta_plus(w + a0))

                    intrf -= a0
                    intrf_details[str(ti)+':offset'] = str(a0)

                    if intrf > busy_intrf:
                        busy_intrf = intrf
                        busy_details = intrf_details

            w_new = q * task.wcet + busy_intrf
            for d in busy_details.keys():
                details[d] = busy_details[d]

            if w == w_new:
                break
            w = w_new

        assert(w >= q * task.wcet)
        return w

    def b_plus(self, task, q, details=None, task_results=None):
        assert(task.scheduling_parameter != None)
        assert(task.wcet >= 0)

        idle_details     = dict()
        idle_intrf = self.b_plus_idle(task, q, idle_details, task_results)

        busy_details     = dict()
        busy_intrf = self.b_plus_busy(task, q, busy_details, task_results)

        if idle_intrf > busy_intrf:
            w = idle_intrf
            if details is not None:
                for d in idle_details.keys():
                    details[d] = idle_details[d]
        else:
            w = busy_intrf
            if details is not None:
                for d in busy_details.keys():
                    details[d] = busy_details[d]

        return w

class SPPSchedulerCorrelatedRoxExact(SPPScheduler):
    """ SPP scheduler with dmin correlation based on [Rox2010]_.
        This is the exact version which performs an extensive search of busy window candidates.
    """

    def calculate_w(self, task, sequence, details=None):
        w = 0
        q_cur = 0
        a0 = 0
        for ti, a in sequence:
            w += ti.wcet

            if details is not None:
                details[str(ti)+':'+str(a)] = str(ti.wcet)

            if ti is task:
                q_cur += 1
                if q_cur == 1:
                    a0 = a

        return w, a0, q_cur

    def find_candidates_recursive(self, task, q, interferers, sequence):

        w, a0, q_cur = self.calculate_w(task, sequence)

        if q > q_cur:
            interferers.add(task)
        elif task in interferers:
            interferers.remove(task)

        worst_sequence = sequence
        if q > q_cur:
            worst_rt = 0
        else:
            worst_rt = w - a0

        # place further activations and find maximum w
        for ti in interferers:
            w_new = 0
            new_sequence = list(sequence)
            if len(new_sequence):
                last_t, last_a = new_sequence[-1]
                d_i = last_a + ti.in_event_model.correlated_dmin(last_t)
                dmin = last_a

                k = 0
                for (tj, a) in new_sequence:
                    if tj is ti:
                        if k == 0:
                            first_a = a

                        dmin = first_a + ti.in_event_model.delta_min(2 + k)
                        k += 1

                next_a = max(dmin, d_i)
                if next_a <= w:
                    new_sequence.append( (ti, next_a) )
                    new_sequence = self.find_candidates_recursive(task, q, set(interferers), new_sequence)
            else:
                new_sequence.append((ti, 0))
                new_sequence = self.find_candidates_recursive(task, q, set(interferers), new_sequence)

            w_new, a0, q_cur = self.calculate_w(task, new_sequence)
            if w_new - a0 >= worst_rt and q == q_cur:
                worst_rt = w_new - a0
                worst_sequence = new_sequence

        return worst_sequence

    def b_plus_exact(self, task, q, details=None, task_results=None):
        assert(task.scheduling_parameter != None)
        assert(task.wcet >= 0)

        interferers = set()
        for ti in task.get_resource_interferers():
            assert(ti.scheduling_parameter != None)
            assert(ti.resource == task.resource)
            if self.priority_cmp(ti.scheduling_parameter, task.scheduling_parameter):  # equal priority also interferes (FCFS)
                interferers.add(ti)

        sequence = self.find_candidates_recursive(task, q, interferers, list())
        w, a0, q_cur = self.calculate_w(task, sequence, details)

        assert(q == q_cur)
        return w - a0

    def b_plus(self, task, q, details=None, task_results=None):
        assert(task.scheduling_parameter != None)
        assert(task.wcet >= 0)

        busy_details     = dict()
        busy_intrf = self.b_plus_exact(task, q, busy_details, task_results)

        w = busy_intrf
        if details is not None:
            for d in busy_details.keys():
                details[d] = busy_details[d]

#        classic_details  = dict()
#        classic_intrf = SPPScheduler.b_plus(self, task, q, classic_details)
#        if classic_intrf < w:
#            w = classic_intrf
#            if details is not None:
#                for d in classic_details.keys():
#                    details[d] = classic_details[d]

        assert(w >= q * task.wcet)
        return w


class SPPSchedulerRoundRobin(SPPScheduler):
    """ SPP scheduler with non-preemptive round-robin policy for equal priorities
    """

    def b_plus(self, task, q, details=None, **kwargs):
        assert(task.scheduling_parameter != None)
        assert(task.wcet >= 0)

        w = q * task.wcet
        while True:
            # logging.debug("w: %d", w)
            # logging.debug("e: %d", q * task.wcet)
            s = 0
            # logging.debug(task.name+" interferers "+ str([i.name for i in task.get_resource_interferers()]))
            for ti in task.get_resource_interferers():
                assert(ti.scheduling_parameter != None)
                assert(ti.resource == task.resource)
                if ti.scheduling_parameter == task.scheduling_parameter:  # equal priority -> round robin
                    # assume cooperative round-robin
                    s += ti.wcet * min(q, ti.in_event_model.eta_plus(w))
                elif self.priority_cmp(ti.scheduling_parameter, task.scheduling_parameter):  # lower priority number -> block
                    s += ti.wcet * ti.in_event_model.eta_plus(w)
                    # logging.debug("e: %s %d x %d", ti.name, ti.wcet, ti.in_event_model.eta_plus(w))


            w_new = q * task.wcet + s
            # print ("w_new: ", w_new)
            if w == w_new:
                break
            w = w_new

        assert(w >= q * task.wcet)
        return w


class TDMAScheduler(analysis.Scheduler):
    """ TDMA scheduler
        task.scheduling_parameter is the slot size of the respective task
    """

    def b_plus(self, task, q, details=None, **kwargs):
        assert(task.scheduling_parameter != None)
        assert(task.wcet >= 0)

        t_tdma = task.scheduling_parameter
        for tj in task.get_resource_interferers():
            t_tdma += tj.scheduling_parameter

        w = q * task.wcet + math.ceil(float(q * task.wcet) / task.scheduling_parameter) * (t_tdma - task.scheduling_parameter)
        w = int(w)

        assert(w >= q * task.wcet)

        if details is not None:
            details['q*WCET'] = str(q) + '*' + str(task.wcet) + '=' + str(q * task.wcet)
            for tj in task.get_resource_interferers():
                details["%s.TDMASlot" % (tj)] = str(tj.scheduling_parameter)
            details['I_TDMA'] = '%d*%d=%d' % (math.ceil(float(q * task.wcet) / task.scheduling_parameter),
                                      t_tdma - task.scheduling_parameter,
                                      math.ceil(float(q * task.wcet) / task.scheduling_parameter) * (t_tdma - task.scheduling_parameter))
        return w

class TASScheduler(analysis.Scheduler):
    """ TAS (Time-Aware Shaper) Scheduler

    TAS is defined in IEEE 802.1Qbv for Ethernet TSN networks.
    It uses gate control lists (GCL) to transmit frames during defined time windows.

    The analysis method is based on:
    THIELE D, ERNST R, DIEMER J. Formal worst-case timing analysis of
    Ethernet TSN's time-aware and peristaltic shapers[C]//2015 IEEE
    Vehicular Networking Conference (VNC). Kyoto, Japan: IEEE, 2015: 251-258.

    task.scheduling_parameter stores the TAS configuration parameters
    """

    def __init__(self, priority_cmp=prio_high_wins_equal_domination):
        """ Initialize TAS scheduler with gate control list parameters
        """
        analysis.Scheduler.__init__(self)

        # priority ordering
        self.priority_cmp = priority_cmp

        self.arrival_time_final = 0

    def b_plus(self, task, q, details=None, **kwargs):
        """ Return the maximum time required to process q activations under TAS scheduling

        :param task: Task to analyze
        :param q: Number of job activations
        :param details: Dictionary for detailed analysis output
        :param kwargs: Additional arguments
        :return: Worst-case response time bound for q activations
        """
        assert(task.scheduling_parameter != None)
        assert(task.wcet >= 0)

        arrival_time_min = task.in_event_model.delta_min(q)
        arrival_time_max = task.in_event_model.delta_min(q+1)
        arrival_time_set = []
        response_time = 0
        response_time_final = 0
        worst_case_queuing_time_final = 0

        for ti in task.get_resource_interferers():
            assert (ti.scheduling_parameter != None)
            assert (ti.resource == task.resource)
            if ti.scheduling_parameter == task.scheduling_parameter:  # same priority
                for n in range(1, 1000):
                    if (ti.in_event_model.delta_min(n) >= arrival_time_min) and (ti.in_event_model.delta_min(n) < arrival_time_max):
                        arrival_time_set.append(ti.in_event_model.delta_min(n))

        if arrival_time_set == []:
            arrival_time_set = [arrival_time_min]

        for arrival_time in arrival_time_set:  # Iterating through each arrival time in aiq
            # ST flow - handled by TAS scheduler
            resource = task.resource
            _is_tsn = getattr(resource, 'is_tsn_resource', False)
            _task_uses_tas = _is_tsn and resource.priority_uses_tas(task.scheduling_parameter)

            if _task_uses_tas:
                worst_case_queuing_time = 0
                same_priority_interference = 0
                same_priority_blocking = 0
                gate_closed_blocking = 0
                gate_closed_duration = 0

                # same-priority blocking
                for ti in task.get_resource_interferers():
                    assert (ti.scheduling_parameter != None)
                    assert (ti.resource == task.resource)
                    if (ti.scheduling_parameter == task.scheduling_parameter):
                        same_priority_interference += ti.wcet * ti.in_event_model.eta_plus_closed(arrival_time)
                same_priority_blocking = (q - 1) * task.wcet + same_priority_interference

                tas_cycle = resource.effective_tas_cycle_time(task.scheduling_parameter)
                tas_window = resource.effective_tas_window_time(task.scheduling_parameter)

                # gate-closed time for once
                gate_closed_duration = tas_cycle - tas_window + task.wcet

                # gate-closed blocking
                gate_closed_blocking = math.ceil((same_priority_blocking + task.wcet) / (tas_window - task.wcet)) * gate_closed_duration
                
                worst_case_queuing_time = same_priority_blocking + gate_closed_blocking
            # NST flow - not handled by TAS scheduler
            else:
                lower_priority_blocking = 0
                same_priority_interference = 0
                same_priority_blocking = 0
                guard_band = 0
                gate_closed_blocking = 0
                gate_closed_duration = 0
                tas_cycle_time = 0

                # lower-priority blocking
                for ti in task.get_resource_interferers():
                    assert (ti.scheduling_parameter != None)
                    assert (ti.resource == task.resource)
                    if (ti.scheduling_parameter < task.scheduling_parameter):
                        if lower_priority_blocking < ti.wcet:
                            lower_priority_blocking = ti.wcet

                # same-priority blocking
                for ti in task.get_resource_interferers():
                    assert (ti.scheduling_parameter != None)
                    assert (ti.resource == task.resource)
                    if (ti.scheduling_parameter == task.scheduling_parameter):
                        same_priority_interference += ti.wcet * ti.in_event_model.eta_plus_closed(arrival_time)
                    same_priority_blocking = (q - 1)*task.wcet + same_priority_interference
                
                # calculate the guard band
                for ti in task.get_resource_interferers():
                    assert (ti.scheduling_parameter != None)
                    assert (ti.resource == task.resource)
                    if not _task_uses_tas:
                        if guard_band < ti.wcet:
                            guard_band = ti.wcet

                # gate-closed time for once — sum window times over TAS priorities on this resource
                if _is_tsn and resource.priority_mechanism_map is not None:
                    for key, mech in resource.priority_mechanism_map.items():
                        if mech == 'TAS' and not isinstance(key, tuple):
                            gate_closed_duration += resource.effective_tas_window_time(key)
                    tas_cycle_time = resource.effective_tas_cycle_time()

                # gate-closed blocking
                gate_closed_blocking = math.ceil((same_priority_blocking + task.wcet) / (tas_cycle_time - gate_closed_duration - guard_band)) * (gate_closed_duration + guard_band)

                worst_case_queuing_time = lower_priority_blocking + same_priority_blocking + gate_closed_blocking
                # Fix-point iteration
                while True:
                    high_priority_blocking = 0

                    # higher-priority blocking
                    for ti in task.get_resource_interferers():
                        assert (ti.scheduling_parameter != None)
                        assert (ti.resource == task.resource)
                        ti_uses_tas = _is_tsn and resource.priority_uses_tas(ti.scheduling_parameter)
                        if (ti.scheduling_parameter > task.scheduling_parameter) and not ti_uses_tas:
                            high_priority_blocking += ti.wcet * ti.in_event_model.eta_plus(worst_case_queuing_time)
                    
                    worst_case_queuing_time_new = lower_priority_blocking + same_priority_blocking + gate_closed_blocking + high_priority_blocking
                    if worst_case_queuing_time == worst_case_queuing_time_new:
                        assert (worst_case_queuing_time >= (q - 1) * task.wcet)
                        break
                    worst_case_queuing_time = worst_case_queuing_time_new
            
            response_time = worst_case_queuing_time + task.wcet - arrival_time

            if response_time > response_time_final:
                response_time_final = response_time
                worst_case_queuing_time_final = worst_case_queuing_time
                self.arrival_time_final = arrival_time
        return worst_case_queuing_time_final

    def response_time(self, task, q, w, details=None, **kwargs):
        return w + task.wcet - self.arrival_time_final



# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
