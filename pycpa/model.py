"""
| Copyright (C) 2007-2017 Jonas Diemer, Philip Axer, Daniel Thiele, Johannes Schlatow
| TU Braunschweig, Germany
| All rights reserved.
| See LICENSE file for copyright and license details.

:Authors:
         - Jonas Diemer
         - Philip Axer
         - Johannes Schlatow

Description
-----------

It should be imported in scripts that do the analysis.
We model systems composed of resources and tasks.
Tasks are activated by events, modeled as event models.
The general System Model is described in Section 3.6.1 in [Jersak2005]_
or Section 3.1 in [Henia2005]_.
"""

from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division

import math
import logging
import copy
import warnings

from . import options
from . import util

INFINITY = float('inf')

logger = logging.getLogger(__name__)


def _warn_float(value, reason=""):
    """ Prints a warning with reason if value is float.
    """
    if type(value) == float:
        warnings.warn("You are using floats, " +
                      "this may yield non-pessimistic results (" +
                      reason + ")", UserWarning)


class ConstraintsManager(object):
    """ This class manages all system-wide constraints such as deadlines,
    buffersizes and more.
    """

    def __init__(self):
        # # local task deadlines
        self._wcrt_constraints = dict()

        # # latency contraints
        self._path_constraints = dict()

        # # buffer size constraints
        self._backlog_constraints = dict()

        # # resource load constraints
        self._load_constraints = dict()

    def add_wcrt_constraint(self, task, deadline):
        """ adds a local task deadline constraint
        wcrt must be less or equal than deadline
        """
        self._wcrt_constraints[task] = deadline

    def add_path_constraint(self, path, deadline, n=1):
        """ adds a path latency constraint
        latency for n events must be less or equal than deadline
        """
        self._path_constraints[path] = (deadline, n)

    def add_backlog_constraint(self, task, size):
        """ adds a buffer size constraint
        backlog must be less or equal than size
        """
        self._backlog_constraints[task] = size

    def add_load_constraint(self, resource, load):
        """ adds a resource load constraint
        actual load on the specified resource must be less or equal than load
        """
        self._load_constraints[resource] = load


class EventModel (object):
    """ The event model describing the activation of tasks as described
    in [Jersak2005]_, [Richter2005]_, [Henia2005]_.
    Internally, we use :math:`\delta^-(n)` and  :math:`\delta^+(n)`,
    which represent the minimum/maximum time window containing n events.
    They can be transformed into
    :math:`\eta^+(\Delta t)` and :math:`\eta^-(\Delta t)`
    which represent the maximum/minimum number of events arriving within
    :math:`\Delta t`.
    """

    def __init__(self, name='min', container=dict(), **kwargs):
        """ CTOR
        If called without parameters, a maximal event model (unbounded amount
        of activations) is created
        """

        # # Enables or disables caching
        self.en_caching = not options.get_opt('nocaching')

        # # Cache to speedup busy window calculations
        self.delta_min_cache = dict()
        self.delta_plus_cache = dict()

        self.eta_min_cache = dict()
        self.eta_plus_cache = dict()

        self.eta_min_closed_cache = dict()
        self.eta_plus_closed_cache = dict()

        # # Takes arbitrary objects that will be propagated along
        # with the event model. 
        # Remark: propagation stops at junctions (for now)
        self.container = container

        # # String description of event model
        self.__description__ = name

        # After all mandatory attributes have been initialized above, load
        # those set in kwargs
        for key in kwargs:
            setattr(self, key, kwargs[key])

    def deltamin_func(self, n):
        # # Event model delta function (internal)
        # maximal model: unlimited activations
        return 0

    def deltaplus_func(self, n):
        # # Event model delta function (internal)
        # minimal model: no activation
        return float("inf")

    @staticmethod
    def delta_min_from_eta_plus(etaplus_func):
        """ Delta-minus Function
            Return the minimum time window containing n activations.
            The delta_minus-function is derived from the eta_plus-function.
            This function is rarely needed, as EventModels are represented
            by delta-functions internally.
            Equation 3.7 from [Schliecker2011]_.
        """
        def delta_min(n):
            if n < 2:
                return 0
            if n == INFINITY:
                return float('NaN')

            hi = 10
            lo = 0
            
            # search an upper bound
            while etaplus_func(hi) < n:
                lo = hi
                hi *= 10

            # apply binary search
            while lo < hi:
                mid = (lo + hi) // 2
                midval = etaplus_func(mid)
                if midval < n:
                    lo = mid + 1
                else:
                    hi = mid
            hi -= 1

            if hi >= 0:
                assert etaplus_func(hi) < n
                assert etaplus_func(hi + 1) >= n

            return  int(math.floor(hi))
        return delta_min

    @staticmethod
    def delta_plus_from_eta_min(etamin_func):
        """ Delta-plus Function
            Return the maximum time window containing n activations.
            The delta_plus-function is derived from the eta_minus-function.
            This function is rarely needed, as EventModels are represented
            by delta-functions internally.
            Equation 3.8 from [Schliecker2011]_.
        """
        def delta_plus(n):
            if n < 2:
                return 0
            if n == INFINITY:
                return float('NaN')

            hi = 10
            lo = 0
            
            # search an upper bound
            while etamin_func(hi) <  n - 1:
                lo = hi
                hi *= 10

            # apply binary search
            while lo < hi:
                mid = (lo + hi) // 2
                midval = etamin_func(mid)
                if midval < n - 1:
                    lo = mid + 1
                else:
                    hi = mid
            hi -= 1

            if hi >= 0:
                assert etamin_func(hi) < n - 1
                assert etamin_func(hi + 1) >= n - 1

            return  int(math.floor(hi+1))
        return delta_plus

    def eta_plus(self, w):
        """ Eta-plus Function
            Return the maximum number of events in a time window w.
            Derived from Equation 3.5 from [Schliecker2011]_,
            but assuming half-open intervals for w
            as defined in [Richter2005]_.
        """
        n = self.eta_plus_cache.get(w, None)
        if n is not None:
            return n

        # the window for 0 activations is 0
        if w <= 0:
            return 0
        # if the window does not include 2 activations, assume that one has
        # occured
        if self.delta_min(2) > w:
            return 1
        # if delta_min is constant zero, eta_plus is always infinity
        if self.delta_min(INFINITY) == 0:
            return INFINITY
        hi = 10
        lo = 2

        # search an upper bound
        while self.delta_min(hi) < w:
            lo = hi
            hi *= 2


        # apply binary search
        while lo < hi:
            mid = (lo + hi) // 2
            midval = self.delta_min(mid)
            if midval < w:
                lo = mid + 1
            else:
                hi = mid
        hi -= 1

        assert self.delta_min(hi) < w
        assert self.delta_min(hi + 1) >= w

        if self.en_caching:
            self.eta_plus_cache[w] = hi

        return hi

    def eta_plus_closed(self, w):
        """ Eta-plus Function
            Return the maximum number of events in a time window w.
            Derived from Equation 3.5 from [Schliecker2011]_,
            but assuming CLOSED intervals for w
            as defined in [Richter2005]_.

            This is technically identical to eta_plus(w + EPSILON),
            but the use of epsilon has issues with float precision,
            as w+EPSILON == w for large w and small Epsilon
            (e.g. 40000000+1e-9)
        """
        n = self.eta_plus_closed_cache.get(w, None)
        if n is not None:
            return n

        # if the window does not include 2 activations, assume that one has
        # occured
        if self.delta_min(2) > w:
            return 1
        # if delta_min is constant zero, eta_plus is always infinity
        if self.delta_min(INFINITY) == 0:
            return INFINITY
        hi = 10
        lo = 2

        # search an upper bound
        while self.delta_min(hi) <= w:
            lo = hi
            hi *= 2

        # apply binary search
        while lo < hi:
            mid = (lo + hi) // 2
            midval = self.delta_min(mid)
            if midval <= w:
                lo = mid + 1
            else:
                hi = mid
        hi -= 1

        assert self.delta_min(hi) <= w
        assert self.delta_min(hi + 1) > w

        if self.en_caching:
            self.eta_plus_closed_cache[w] = hi

        return hi

    def eta_min(self, w):
        """ Eta-minus Function
            Return the minimum number of events in a time window w.
            Derived from Equation 3.6 from [Schliecker2011]_,
            but different, as Eq. 3.6 is wrong.
        """
        n = self.eta_min_cache.get(w, None)
        if n is not None:
            return n

        if w < 0:
            w = 0

        MAX_EVENTS = 10000
        hi = 10
        lo = 2

        # search an upper bound
        while self.delta_plus(hi) <= w:
            if(hi > MAX_EVENTS):
                logger.error("w=%f" % w + " n=%d" % hi +
                             "deltaplus(n)=%d" % self.delta_plus(hi))
                return hi
            lo = hi
            hi *= 10

        # apply binary search
        while lo < hi:
            mid = (lo + hi) // 2
            midval = self.delta_plus(mid)
            if midval <= w:
                lo = mid + 1
            else:
                hi = mid
        hi -= 1

        if (self.delta_plus(hi) > w):
            print ("delta_plus(" + str(hi) + ") = " + str(self.delta_plus(hi)) + " > " + str(w))
        assert self.delta_plus(hi) <= w
        assert self.delta_plus(hi + 1) > w

        if self.en_caching:
            self.eta_min_cache[w] = hi-1

        return hi-1
   
    
    def eta_min_closed(self, w):
        """ Eta-minus Function
            Return the minimum number of events in a time window w.
            Using CLOSED intevals
        """
        n = self.eta_min_closed_cache.get(w, None)
        if n is not None:
            return n

        if w < 0:
            w = 0

        MAX_EVENTS = 10000
        hi = 10
        lo = 2

        # search an upper bound
        while self.delta_plus(hi) < w:
            if(hi > MAX_EVENTS):
                logger.error("w=%f" % w + " n=%d" % hi +
                             "deltaplus(n)=%d" % self.delta_plus(hi))
                return hi
            lo = hi
            hi *= 10

        # apply binary search
        while lo < hi:
            mid = (lo + hi) // 2
            midval = self.delta_plus(mid)
            if midval < w:
                lo = mid + 1
            else:
                hi = mid
        hi -= 1

        assert self.delta_plus(hi) < w
        assert self.delta_plus(hi + 1) >= w

        if self.en_caching:
            self.eta_min_closed_cache[w] = hi-1

        return hi-1


    def delta_min(self, n):
        """ Delta-minus Function
            Return the minimum time interval between
            the first and the last event
            of any series of n events.
            This is actually a wrapper to allow caching of delta functions.
        """
        if n < 2:
            return 0

        # # Caching is activated
        if self.en_caching == True:
            d = self.delta_min_cache.get(n, None)
            if d == None:
                d = self.deltamin_func(n)
                self.delta_min_cache[n] = d
            return d

        # # default policy
        return self.deltamin_func(n)


    def delta_plus(self, n):
        """ Delta-plus Function
            Return the maximum time interval between
            the first and the last event
            of any series of n events.
            This is actually a wrapper to allow caching of delta functions.
        """
        if n < 2:
            return 0

        # # Caching is activated
        if self.en_caching == True:
            d = self.delta_plus_cache.get(n, None)
            if d == None:
                d = self.deltaplus_func(n)
                self.delta_plus_cache[n] = d
            return d

        # # default policy
        return self.deltaplus_func(n)


    def load(self, accuracy=1000):
        """ Returns the asymptotic load,
        i.e. the avg. number of events per time
        """
        # print "load = ", float(self.eta_plus(accuracy)),"/",accuracy
        # return float(self.eta_plus(accuracy)) / accuracy
        if self.delta_min(accuracy) == 0:
            return float("inf")
        else:
            return float(accuracy) / self.delta_min(accuracy)

    def flush_cache(self):
        self.delta_min_cache = dict()
        self.delta_plus_cache = dict()

        self.eta_min_cache = dict()
        self.eta_plus_cache = dict()

        self.eta_min_closed_cache = dict()
        self.eta_plus_closed_cache = dict()

    def __repr__(self):
        """ Return a description of the Event-Model"""
        return self.__description__

class PJdEventModel (EventModel):
    """ A periodic, jitter, min-distance event model.
    """

    def __init__(self, P=0, J=0, dmin=0, phi=0, name='min', **kwargs):
        """ Periodic, Jitter, min. distance event model. Offset can be supplied
        but is not evaluated by all analyses.
        """
        EventModel.__init__(self, name, **kwargs)

        # setup event model
        self.set_PJd(P, J, dmin, phi)


    def set_PJd(self, P, J=0, dmin=0, phi=0, early_arrival=False):
        """ Sets the event model to a periodic activation
        with jitter and minimum distance.
        Equations 1 and 2 from [Schliecker2008]_.
        """
        _warn_float(P, "Period")
        _warn_float(J, "Jitter")
        _warn_float(dmin, "dmin")

        # save away the properties in case a local analysis uses them directly
        self.P = P
        self.J = J
        self.dmin = dmin

        # offset for some context sensitive analyses
        self.phi = phi

        if self.phi > 0:
            self.__description__ = "P={} J={} d={} phi={}".format(P, J, dmin, phi)
        else:
            self.__description__ = "P={} J={} d={}".format(P, J, dmin)
        if early_arrival:
            raise(NotImplementedError)

    def deltaplus_func(self, n):
        return (n - 1) * self.P + self.J

    def deltamin_func(self, n):
        return max((n - 1) * self.dmin, (n - 1) * self.P - self.J)


class CTEventModel (EventModel):
    """ c events every T time event model.
    """
    def __init__(self, c, T, dmin=1, name='min', **kwargs):

        EventModel.__init__(self, name, kwargs)

        self.set_c_in_T(c, T, dmin)

    def set_c_in_T(self, c, T, dmin=1):
        """ Sets the event-model to a periodic Task
         with period T and c activations per period.
         No minimum arrival rate is assumed (delta_plus = infinity)!
         Cf. Equation 1 in [Diemer2010]_.
        """
        assert c*dmin <= T
        self.__description__ = "%d every %d, dmin=%d" % (c, T, dmin)
        self.c = c
        self.T = T
        self.dmin = dmin

    def deltamin_func(self, n):
        if self.c == 0 or self.T >= INFINITY:
            return 0
        if n == INFINITY:
            return INFINITY
        else:
            return (n - 1) * self.dmin + int(math.floor(float(n - 1) / self.c)
                    * (self.T - self.c * self.dmin))

    def deltaplus_func(self, n):
        return INFINITY


class LimitedDeltaEventModel(EventModel):
    """ User supplied event model on a limited delta domain.
    """
    def __init__(self,
            limited_delta_min_func=None,
            limited_delta_plus_func=None,
            limit_q_min=float('inf'),
            limit_q_plus=float('inf'),
            min_additive=util.recursive_min_additive,
            max_additive=util.recursive_max_additive,
            name='min',
            **kwargs):

        EventModel.__init__(self, name, kwargs)

        self.set_limited_delta(limited_delta_min_func, limited_delta_plus_func, limit_q_min, limit_q_plus, min_additive, max_additive)


    def set_limited_delta(self,
            limited_delta_min_func,
            limited_delta_plus_func,
            limit_q_min=float('inf'),
            limit_q_plus=float('inf'),
            min_additive=util.recursive_min_additive,
            max_additive=util.recursive_max_additive):
        """ Sets the event model to an arbitrary function specified
        by limited_delta_min_func and limited_delta_plus_func.
        Contrary to directly setting deltamin_func and deltaplus_func,
        the given functions are only valid in a limited domain [0, limit_q_min]
        and [0, limit_q_plus] respectively.
        For values of q beyond this range, a conservative extension
        (additive extension) is used.
        You can also supply a list() object to this function by using
        lambda x: limited_delta_min_list[x]
        """
        self.__description__ = "ltd. direct"
        self.max_additive = max_additive
        self.min_additive = min_additive
        self.limited_delta_min_func = limited_delta_min_func
        self.limited_delta_plus_func = limited_delta_plus_func
        self.limit_q_min = limit_q_min
        self.limit_q_plus = limit_q_plus

    def deltamin_func(self, n):
        if n == float("inf"):
            return float("inf")
        elif n > self.limit_q_min:  # return additive extension  if necessary
            q_max = self.limit_q_min - 1
            ret = self.max_additive(lambda x: self.delta_min(x + 1),
                    n - 1, q_max, self.delta_min_cache)
            return ret
        else:
            return self.limited_delta_min_func(n)

    def deltaplus_func(self, n):
        if n == float("inf"):
            return float("inf")
        elif n > self.limit_q_plus:  # return additive extension  if necessary
            q_max = self.limit_q_plus - 1
            ret = self.min_additive(lambda x: self.delta_plus(x + 1),
                    n - 1, q_max, self.delta_plus_cache)
            return ret
        else:
            return self.limited_delta_plus_func(n)




class TraceEventModel (LimitedDeltaEventModel):
    def __init__(self, trace_points=[], min_sample_size=20,
                 min_additive=util.recursive_min_additive,
                 max_additive=util.recursive_max_additive,
                 name='min',
                 **kwargs):
        LimitedDeltaEventModel.__init__(self, name=name, **kwargs)

        self.trace_points = trace_points
        self.min_sample_size = min_sample_size
        self.min_addititive = min_additive
        self.max_additive = max_additive

        self.set_limited_trace(trace_points, min_sample_size, min_additive, max_additive)

    def set_limited_trace(self,
            trace_points,
            min_sample_size=20,
            min_additive=util.recursive_min_additive,
            max_additive=util.recursive_max_additive):
        """ Compute a pseudo-conservative event model from a given trace
        (e.g. from SymTA/S TraceAnalyzer or similar).
        trace_points must be a list of integers encoding the arrival time
        of an event. The algorithm will compute delta_min and delta_plus based
        on the trace by evaluating all candidates.
        min_sample_size is the minimum amount of candidates that must
        be available to derive a representative deltamin/deltaplus
        """

        for p in set(trace_points):
            if type(p) == float:
                warnings.warn("You are using floats in your timestamps,"
                             " this may yield non-pessimistic results"
                             " consider using time conversion from pycpa.util")
                break


        trace = trace_points
        q_max  = len(trace_points)
        try:
            import numpy
            nptrace = numpy.array(trace)
            
            def raw_deltamin_func(n):
                a = nptrace[0:q_max-n+1]
                b = nptrace[(n-1):q_max]
                d = numpy.amin(b-a)
                return d

            def raw_deltaplus_func(n):
                a = nptrace[0:q_max-n+1]
                b = nptrace[(n-1):q_max]
                d = numpy.amin(b-a)
                return d
                
        except ImportError:
            def raw_deltamin_func(n):
                """ raw trace deltamin_func, only valid in the interval [0,q_max]
                """
                assert n >= 0
                assert n <= q_max
                d = min(trace[q + n - 1] - trace[q] for q in range(0, q_max - n + 1))
                return d

            def raw_deltaplus_func(n):
                """ raw trace deltaplus_func, only valid in the interval [0,q_max]
                """
                assert n >= 0
                assert n <= q_max
                d = max(trace[q + n - 1] - trace[q] for q in range(0, q_max - n + 1))
                return d

        # set the trace as a limited delta function and let pycpa extrapolate
        limit_q_max = max(2, q_max - min_sample_size)
        # print("q_max", q_max, "trace_size", trace.size, limit_q_max)
        self.set_limited_delta(raw_deltamin_func, raw_deltaplus_func,
                limit_q_max, limit_q_max, min_additive, max_additive)

        self.__description__ = "trace-based"
        

class Junction (object):
    """ A junction combines multiple event models into one output event model
        This is used to model multi-input tasks.
        Typical semantics are "and" and "or" strategies.
        See Chapter 4 in [Jersak2005]_ for definitions and details.
    """

    def __init__(self, name="unknown", strategy=None):
        """ CTOR """
        # # Name
        self.name = name

        # # Strategy for the model propagation
        self.strategy = strategy

        # # Set of input tasks
        self.prev_tasks = set()

        # # Output event model
        self.out_event_model = None

        # # Link to next Tasks or Junctions,
        # i.e. where to supply event model to
        self.next_tasks = set()

        self.in_event_models = dict()

        # # store analysis results of sampling delay
        self.analysis_results = dict()

        # # at some point Junction looks like a task
        # i.e. provide wcet, bcet for duck-typing
        self.bcet = 0
        self.wcet = 0

        # # create a task to id mapping
        self.mapping = dict()

    def map_task(self, src_task, identifier):
        """ maps an identifier to src_task """
        self.mapping[src_task] = identifier

    @property
    def mode(self):
        return str(self.strategy)

    def invalidate_event_model_cache(self):
        for t in self.next_tasks:
            t.invalidate_event_model_cache()

    def link_dependent_task(self, task):
        task.prev_task = self
        self.next_tasks.add(task)

    def clean(self):
        """ mark event models as invalid """
        self.out_event_model = None
        self.in_event_models.clear()

    def __repr__(self):
        return self.name + " " + str(self.strategy) + " junction"


class Task (object):
    """ A Task is an entity which is mapped on a resource and consumes service.
    Tasks are activated by events, which are described by EventModel.
    Events are queued in FIFO order at the input of the task,
    see Section 3.6.1 in [Jersak2005]_ or Section 3.1 in [Henia2005]_.
    """

    def __init__(self, name, *args, **kwargs):
        """ CTOR """
        # # Descriptive string
        self.name = name

        # # Link to Resource to which Task is mapped
        self.resource = None

        # # Link the Path if the task takes part in chained communication
        # FIXME: A task can be part of more than one path! Is this used anywhere?
        self.path = None

        # # Link to Mutex to which Task is mapped
        self.mutex = None

        # # Link to next Tasks, i.e. where to supply event model to
        # # Multiple tasks possible (fork semantic)
        self.next_tasks = set()

        # Link to previous Task, i.e. the one which supplies our in_event_model
        self.prev_task = None

        # # Worst-case execution time
        self.wcet = 0

        # # Best-case execution time
        self.bcet = 0

        # # Event model activating the Task
        self.in_event_model = None

        # # Omit analysis
        self.skip_analysis = False

        # # Set event model propagation
        from . import propagation
        if not 'OutEventModelClass' in kwargs:
            self.OutEventModelClass = propagation.default_propagation_method()

        self.analysis_results = None

        # compatability to the old call semantics (name, bcet, wcet,
        # scheduling_parameter)
        if len(args) == 3:
            self.bcet = args[0]
            self.wcet = args[1]
            self.scheduling_parameter = args[2]

        # After all mandatory attributes have been initialized above, load
        # those set in kwargs
        for key in kwargs:
            setattr(self, key, kwargs[key])

        assert(self.bcet <= self.wcet)

    def __repr__(self):
        """ Returns string representation of Task """
        return self.name

    def load(self, accuracy=100):
        """ Returns the load generated by this task """
        return self.in_event_model.load(accuracy) * float(self.wcet)

    def bind_resource(self, r):
        """ Bind a Task t to a Resource/Mutex r """
        self.resource = r
        r.tasks.add(self)
        for t in r.tasks:
            assert t.resource == r

    def unbind_resource(self):
        """ Remove a task from its resource """
        if self.resource and self in self.resource.tasks:
            self.resource.tasks.remove(self)
        self.resource = None

    def bind_mutex(self, m):
        """ Bind a Task t to a Mutex r """
        self.mutex = m
        m.tasks.add(self)

    def unbind_mutex(self):
        """ Remove a task fromk its mutex """
        if self.mutex and self in self.mutex.tasks:
            self.mutex.tasks.remove(self)
        self.mutex = None

    def link_dependent_task(self, t):
        """ Link a dependent task t to the task
        The dependent task t is activated by the completion of the task.

        This method returns the t argument, which enables elegant task 
        linking. E.g. to link t0 -> t1 -> t2, call:
        t0.link_dependent_task(t1).link_dependent_task(t2)
        """
        self.next_tasks.add(t)
        if isinstance(t, Task):
            t.prev_task = self
        else:
            t.prev_tasks.add(self)

        return t

    def get_resource_interferers(self):
        """ returns the set of tasks sharing the same Resource as Task ti
            excluding ti itself
        """
        if self.resource is None:
            return []
        interfering_tasks = copy.copy(self.resource.tasks)
        interfering_tasks.remove(self)
        return interfering_tasks

    def get_mutex_interferers(self):
        """ returns the set of tasks sharing the same Mutex as Task ti
            excluding ti itself
        """
        if self.mutex is None:
            return []
        interfering_tasks = copy.copy(self.mutex.tasks)
        interfering_tasks.remove(self)
        return interfering_tasks

    def invalidate_event_model_cache(self):
        if self.in_event_model is not None:
            self.in_event_model.flush_cache()

    def clean(self):
        """ Cleans all intermediate analysis results """

        # invalidate downstream junctions
        for n in self.next_tasks:
            if isinstance(n, Junction):
                n.clean()

        # if this task is activated by another task, we discard the event model
        if self.prev_task:
            self.in_event_model = None
        else:
            self.in_event_model.flush_cache()

        if self.analysis_results is not None:
            self.analysis_results.clean()

    def update_execution_time(self, task_results=None):
        return


class Resource (object):
    """ A Resource provides service to tasks. """

    def __init__(self, name=None, scheduler=None, **kwargs):
        """ CTOR """

        # # Set of tasks mapped to this Resource
        self.tasks = set()

        # # Resource identifier
        self.name = name

        # # Analysis function
        self.scheduler = scheduler

        # After all mandatory attributes have been initialized above, load
        # those set in kwargs
        for key in kwargs:
            setattr(self, key, kwargs[key])

    def __repr__(self):
        """ Return string representation of Resource """
        s = str(self.name)
        return s

    def load(self, accuracy=10000):
        """ returns the asymptotic load """
        l = 0
        for t in self.tasks:
            try:
                l += t.load(accuracy)
            except TypeError:
                logger.warn("cannot compute load for %s, skipping load "
                    "analysis for this resource" % (self.name))
                return 0.
            assert l < float('inf'), "Load on resource {} is infinity"\
                    .format(self.name)
            assert l >= 0., "Load should be non-negative"
        return l

    def bind_task(self, t):
        """ Bind task t to resource
        Returns t """
        t.bind_resource(self)
        for task in self.tasks:
            assert task.resource == self
        return t

    def unmap_tasks(self):
        """ unmap all tasks from this resource """
        for task in self.tasks:
            task.resource = None
        self.tasks = set()

    def get_task_by_name(self, name):
        for t in self.tasks:
            if t.name == name:
                return t
        return None


class StandardForkStrategy(object):
    """ Standard fork strategy: propagates unmodified output event model to all tasks. """
    def __init__(self):
        self.name = "Standard"

    def output_event_model(self, fork, dst_task=None, task_results=None):
        """
        This strategy does not distinguish between destination tasks.

        :param fork:      Fork from which to take the output event model.
        :type fork:       model.Fork
        :param dst_task:  destination task
        :type fork:       model.Task
        """
        return fork.out_event_model


class Fork (Task):
    """ A Fork allows the modification (determined by the assigned strategy)
        of output event models dependent on the destination task. 
    """

    def __init__(self, name, strategy=StandardForkStrategy(), *args, **kwargs):
        # # set default fork strategy
        self.strategy = strategy
        
        # # call Task CTOR
        Task.__init__(self, name, *args, **kwargs)

        # # store the output event model (used by the fork strategy)
        self.out_event_model = None

        # # create a task to id mapping
        self.mapping = dict()

    def clean(self):
        Task.clean(self)
        self.out_event_model = None
        
    def map_task(self, dst_task, identifier):
        """ maps an identifier to dst_task """
        self.mapping[dst_task] = identifier

    def get_mapping(self, dst_task):
        """ returns the identifier mapped to dst_task (or raises KeyError) """
        return self.mapping[dst_task]


class ForwardingTask(Task):
    """ Represents switch forwarding delay between hops.

    A ForwardingTask models the processing and transmission delay that occurs
    when a packet is forwarded through a switch. Key characteristics:
        - Not affected by gate control (no gate-closed blocking)
        - No same-priority blocking (no other forwarding tasks interfere)
        - WCRT = BCET = configured forwarding delay
        - in_event_model comes from upstream task (chained dependency)
        - out_event_model feeds into downstream task

    Forwarding tasks use reserved scheduling_parameter range to distinguish
    from regular tasks. Only TASSchedulerE2E recognizes and handles
    forwarding tasks specially.

    Note: This functionality is based on:
    Luo F, Zhu L, Wang Z, et al. Schedulability analysis of time aware shaper
    with preemption supported in time-sensitive networks[J]. Computer Networks,
    2025, 269: 111424.
    """

    # Reserved scheduling parameter range for forwarding tasks
    FORWARDING_PRIO_MIN = -100
    FORWARDING_PRIO_MAX = -1

    def __init__(self, name, bcet, wcet, scheduling_parameter=-1, **kwargs):
        """ Initialize a forwarding task.

        :param name: Task name
        :param bcet: Best case execution time (forwarding delay)
        :param wcet: Worst case execution time (forwarding delay)
        :param scheduling_parameter: Reserved priority (default -1, must be in FORWARDING_PRIO_* range)
        """
        # Validate scheduling parameter is in reserved range
        if not (self.FORWARDING_PRIO_MIN <= scheduling_parameter <= self.FORWARDING_PRIO_MAX):
            raise ValueError(
                "ForwardingTask scheduling_parameter must be in range [%d, %d], got %d" %
                (self.FORWARDING_PRIO_MIN, self.FORWARDING_PRIO_MAX, scheduling_parameter)
            )
        super(ForwardingTask, self).__init__(name, bcet, wcet, scheduling_parameter, **kwargs)
        # Mark this as a forwarding task for quick identification
        self._is_forwarding_task = True

    @classmethod
    def is_forwarding_task(cls, task):
        """ Check if a task is a forwarding task.

        :param task: Task to check
        :return: True if task is a forwarding task, False otherwise
        """
        if isinstance(task, ForwardingTask):
            return True
        if hasattr(task, '_is_forwarding_task'):
            return task._is_forwarding_task
        if hasattr(task, 'scheduling_parameter'):
            return cls.FORWARDING_PRIO_MIN <= task.scheduling_parameter <= cls.FORWARDING_PRIO_MAX
        return False


def add_forwarding_delay_to_path(path, switch_resource, delay_us, name=None):
    """ Add a forwarding delay task to a path for a specific switch.

    This function inserts a ForwardingTask into the path after the last task
    that is bound to the specified switch resource.

    :param path: The Path object to modify
    :param switch_resource: The Resource representing the switch
    :param delay_us: Forwarding delay in microseconds. Can be a single value
                     (wcet = bcet = delay_us) or a tuple (bcet, wcet).
    :param name: Optional name for the forwarding task (default: "FD_<switch_name>")
    :return: The created ForwardingTask
    """
    if name is None:
        name = "FD_" + str(switch_resource.name)

    if isinstance(delay_us, (tuple, list)):
        bcet, wcet = delay_us
    else:
        bcet, wcet = delay_us, delay_us

    fd_task = ForwardingTask(
        name=name,
        bcet=bcet,
        wcet=wcet,
        scheduling_parameter=-1
    )

    # Find the insertion point: after the last task bound to this switch
    insert_index = 0
    for i, task in enumerate(path.tasks):
        if hasattr(task, 'resource') and task.resource == switch_resource:
            insert_index = i + 1

    # Insert forwarding task at the correct position
    path.tasks.insert(insert_index, fd_task)

    # Bind forwarding task to the switch resource
    switch_resource.bind_task(fd_task)

    # Link output model: forwarding task outputs to next task's input
    # This makes the forwarding task part of the analysis chain
    # Note: The input event model of forwarding task will be inherited
    # from the task it depends on through the chain

    # Link dependencies:
    # - The task at insert_index - 1 should link to forwarding task
    # - The forwarding task should link to the task at insert_index + 1
    # This ensures: upstream task out_event_model -> fd in_event_model -> fd out_event_model -> downstream in_event_model
    if insert_index > 0:
        prev_task = path.tasks[insert_index - 1]
        prev_task.link_dependent_task(fd_task)

    if insert_index < len(path.tasks) - 1:
        next_task = path.tasks[insert_index + 1]
        fd_task.link_dependent_task(next_task)

    return fd_task


def add_forwarding_delays_for_path(path, switch_forwarding_delays=None):
    """ Automatically add forwarding delay tasks to a path for all switches.

    For each switch resource that has tasks on the path, adds a forwarding
    delay task if the switch has a configured delay.

    :param path: The Path object
    :param switch_forwarding_delays: Dict mapping Resource to delay (us).
                                     Values can be a single number (bcet=wcet)
                                     or a tuple (bcet, wcet).
                                     If None, uses resource.forwarding_delay parameter.
    :return: List of created ForwardingTask objects
    """
    forwarding_tasks = []

    # Collect all switch resources on the path (resources that have tasks bound)
    switches_on_path = set()
    for task in path.tasks:
        if hasattr(task, 'resource'):
            switches_on_path.add(task.resource)

    # Add forwarding delay for each switch
    for switch in switches_on_path:
        # Determine delay
        delay = None
        if switch_forwarding_delays and switch in switch_forwarding_delays:
            delay = switch_forwarding_delays[switch]
        elif hasattr(switch, 'forwarding_delay'):
            delay = switch.forwarding_delay

        # Normalize and check: delay can be a number or (bcet, wcet) tuple
        if delay is not None:
            if isinstance(delay, (tuple, list)):
                bcet, wcet = delay
                if wcet > 0:
                    fd_task = add_forwarding_delay_to_path(path, switch, (bcet, wcet))
                    forwarding_tasks.append(fd_task)
            elif delay > 0:
                fd_task = add_forwarding_delay_to_path(path, switch, delay)
                forwarding_tasks.append(fd_task)

    return forwarding_tasks


def auto_add_forwarding_delays(system, latency_by_resource=None, default_latency=0):
    """ Automatically add forwarding delay tasks to all paths in a system.

    For each regular task with a TSN_Resource, adds a forwarding delay task
    after it if the resource has a forwarding_delay configured.

    :param system: System object containing paths and resources
    :param latency_by_resource: Dict mapping resource names to latency values (us).
                                Values can be a single number (bcet=wcet) or a tuple (bcet, wcet).
    :param default_latency: Default forwarding delay for resources not in dict (us).
                            Can be a single number or a tuple (bcet, wcet).
    :return: Dict mapping (path_name, task_name) -> (forwarding_task, latency)
    """
    result = {}

    def _latency_is_positive(lat):
        """Check if a latency value (number or tuple) represents a positive delay."""
        if isinstance(lat, (tuple, list)):
            return lat[1] > 0  # check wcet
        return lat > 0

    for path in system.paths:
        # Collect tasks with potential forwarding delays
        tasks_to_add = []
        for i, task in enumerate(path.tasks):
            if ForwardingTask.is_forwarding_task(task):
                continue
            res = getattr(task, 'resource', None)
            if res and getattr(res, 'is_tsn_resource', False):
                if latency_by_resource and res.name in latency_by_resource:
                    latency = latency_by_resource[res.name]
                elif hasattr(res, 'forwarding_delay') and _latency_is_positive(res.forwarding_delay):
                    latency = res.forwarding_delay
                else:
                    latency = default_latency
                if _latency_is_positive(latency):
                    tasks_to_add.append((i, task, latency))

        # Build switch -> delay mapping
        switch_forwarding_delays = {}
        for task_index, original_task, latency in tasks_to_add:
            res = getattr(original_task, 'resource', None)
            if res:
                if res not in switch_forwarding_delays:
                    switch_forwarding_delays[res] = latency

        # Add forwarding delays for each unique switch
        added_fds = add_forwarding_delays_for_path(path, switch_forwarding_delays)

        # Record results
        for fd in added_fds:
            # Find the original task that this FD follows
            fd_index = path.tasks.index(fd)
            if fd_index > 0:
                original_task = path.tasks[fd_index - 1]
                if not ForwardingTask.is_forwarding_task(original_task):
                    result[(path.name, original_task.name)] = (fd, fd.wcet)

    return result


class TSN_Resource(Resource):
    """ A TSN_Resource extends Resource with TSN (Time-Sensitive Networking) port-level parameters.

    In real TSN networks, scheduling parameters like TAS gate control and CQF cycle
    are configured per device port (i.e. per resource), not per individual flow/task.

    Constructor Parameters:
    -----------------------
    name : str
        Resource name/identifier (same as Resource)

    scheduler : object
        Scheduler for this resource (same as Resource)

    Priority-Mechanism Mapping (optional):
    --------------------------------------
    priority_mechanism_map : dict
        Maps priorities to TSN scheduling mechanisms on this port.
        - Single-priority mechanisms (TAS, CBS, ATS): use int key
        - CQF: use tuple of exactly 2 ints as key (a pair of priority queues)
        - Value: 'TAS', 'CQF', 'CBS', 'ATS', or None (no mechanism)
        A task's TSN mechanism is determined by looking up its scheduling_parameter
        (priority) in this mapping.

        Example::

            priority_mechanism_map = {
                7: 'TAS',
                6: 'TAS',
                (5, 4): 'CQF',
                (3, 2): 'CQF',
                1: 'CBS',
                0: None,
            }

    TSN Port-Level Parameters (optional):
    --------------------------------------
    TAS (Time-Aware Shaper):
        tas_cycle_time : int/float
            The cycle time (period) of the TAS Gate Control List (GCL) on this port.
            Shared by all TAS priorities on this resource.
        tas_window_time : int/float
            Default gate open window duration for TAS on this port.
            Used when no per-priority mapping is provided.
        tas_window_time_by_priority : dict
            Per-priority mapping of TAS gate window durations.
            Keys are scheduling_parameter (priority) values, values are window durations.
            Example: {7: 100, 6: 200}
        guard_band : int/float
            Default guard band duration for this port.
            Used when analyzing TAS/NST co-scheduled flows with TASSchedulerE2E.
            If set, overrides default guard band behavior.
            If not set, for TAS flows: guard_band = task.wcet (default),
                        for NST flows: guard_band is computed as max(wcet of lower-priority flows).
        guard_band_by_priority : dict
            Per-priority guard band mapping. Keys are priorities, values are durations.
            Example: {7: 10, 5: 8}
            If set for a priority, overrides both guard_band and default behavior.

    CBS (Credit-Based Shaper):
        idleslope : int/float
            Default idleSlope parameter in bits per second.
        idleslope_by_priority : dict
            Per-priority idleSlope mapping. Example: {1: 5000000}

    CQF (Cyclic Queuing and Forwarding):
        cqf_cycle_time : int/float
            Default cycle time (rotate period) for CQF queues.
        cqf_cycle_time_by_pair : dict
            Per-CQF-pair cycle time mapping. Keys are tuples matching those in
            priority_mechanism_map. Example: {(5, 4): 500, (3, 2): 1000}

    Frame Preemption:
        is_express : bool
            Default preemption classification for frames on this port.
        is_express_by_priority : dict
            Per-priority preemption classification. Example: {7: True, 1: False}

    ATS (Asynchronous Traffic Shaping):
        ats_cir / ats_cbs / ats_eir / ats_ebs / ats_scheduler_group :
            Default ATS parameters for this port.
        ats_params_by_priority : dict
            Per-priority ATS parameter mapping. Each value is a dict with keys:
            'cir', 'cbs', 'eir', 'ebs', 'scheduler_group'.
            Example: {4: {'cir': 2000000, 'cbs': 10000, 'eir': 500000,
                          'ebs': 5000, 'scheduler_group': 1}}

    Example usage:
    --------------
        # Full priority-mechanism mapping with per-priority parameters
        r = TSN_Resource("Switch_Port1", schedulers.TASScheduler(),
            priority_mechanism_map={
                7: 'TAS',
                6: 'TAS',
                (5, 4): 'CQF',
                1: 'CBS',
                0: None,
            },
            tas_cycle_time=1000,
            tas_window_time_by_priority={7: 100, 6: 200},
            cqf_cycle_time_by_pair={(5, 4): 500},
            idleslope_by_priority={1: 5000000},
        )

        # Use plain Task — TSN behavior is derived from the resource
        t1 = Task('Flow_P7', 1, 12, 7)
        r.bind_task(t1)
        r.priority_uses_tas(7)  # True — derived from resource map
        r.effective_tas_window_time(7)  # 100

        # Simple TAS-enabled resource
        r = TSN_Resource("Switch_Port2", schedulers.TASScheduler(),
                         tas_cycle_time=1000,
                         tas_window_time_by_priority={7: 100, 6: 200})

        # CQF-enabled resource
        r = TSN_Resource("Switch_Port3", schedulers.SPPScheduler(),
                         cqf_cycle_time=500000)
    """

    is_tsn_resource = True

    # Valid mechanism names in priority_mechanism_map
    VALID_MECHANISMS = {'TAS', 'CQF', 'CBS', 'ATS', None}

    # Mechanism name to FLAG bit mapping
    MECHANISM_TO_FLAG = {
        'TAS': 1 << 1,   # FLAG_TAS
        'CQF': 1 << 2,   # FLAG_CQF
        'CBS': 1 << 0,   # FLAG_CBS
        'ATS': 1 << 4,   # FLAG_ATS
        None: 0,
    }

    def __init__(self, name=None, scheduler=None, **kwargs):
        """ CTOR """
        Resource.__init__(self, name, scheduler)

        # Priority-mechanism mapping
        self.priority_mechanism_map = None

        # TAS parameters
        self.tas_cycle_time = None
        self.tas_window_time = None
        self.tas_window_time_by_priority = None
        self.guard_band = None
        self.guard_band_by_priority = None

        # CBS parameters
        self.idleslope = None
        self.idleslope_by_priority = None

        # CQF parameters
        self.cqf_cycle_time = None
        self.cqf_cycle_time_by_pair = None

        # Frame Preemption parameters
        self.is_express = None
        self.is_express_by_priority = None

        # ATS parameters
        self.ats_cir = None
        self.ats_cbs = None
        self.ats_eir = None
        self.ats_ebs = None
        self.ats_scheduler_group = None
        self.ats_params_by_priority = None

        # Switch forwarding delay (in microseconds).
        # Can be a single value (bcet = wcet) or a tuple (bcet, wcet).
        self.forwarding_delay = kwargs.pop('forwarding_delay', 0)

        for key in kwargs:
            setattr(self, key, kwargs[key])

    def get_mechanism_for_priority(self, priority):
        """Look up the TSN mechanism assigned to a given priority.

        :param priority: The scheduling_parameter (priority) to look up.
        :returns: Mechanism name string ('TAS', 'CQF', 'CBS', 'ATS', None),
                  or None if priority is not found in the map.
        """
        if self.priority_mechanism_map is None:
            return None
        for key, mechanism in self.priority_mechanism_map.items():
            if isinstance(key, tuple):
                if priority in key:
                    return mechanism
            elif key == priority:
                return mechanism
        return None

    def get_cqf_pair_for_priority(self, priority):
        """Find the CQF pair tuple that contains a given priority.

        :param priority: The scheduling_parameter (priority) to look up.
        :returns: The CQF pair tuple, or None if priority is not part of any CQF pair.
        """
        if self.priority_mechanism_map is None:
            return None
        for key, mechanism in self.priority_mechanism_map.items():
            if isinstance(key, tuple) and mechanism == 'CQF' and priority in key:
                return key
        return None

    # ------------------------------------------------------------------
    # Mechanism queries for a given priority
    # ------------------------------------------------------------------

    def priority_uses_cbs(self, priority):
        """Check if the given priority uses CBS scheduling on this resource."""
        return self.get_mechanism_for_priority(priority) == 'CBS'

    def priority_uses_tas(self, priority):
        """Check if the given priority uses TAS scheduling on this resource."""
        return self.get_mechanism_for_priority(priority) == 'TAS'

    def priority_uses_cqf(self, priority):
        """Check if the given priority uses CQF scheduling on this resource."""
        return self.get_mechanism_for_priority(priority) == 'CQF'

    def priority_uses_ats(self, priority):
        """Check if the given priority uses ATS scheduling on this resource."""
        return self.get_mechanism_for_priority(priority) == 'ATS'

    def priority_uses_preemption(self, priority):
        """Check if the given priority uses frame preemption on this resource."""
        if self.is_express_by_priority is not None and priority in self.is_express_by_priority:
            return True
        return self.is_express is not None

    # ------------------------------------------------------------------
    # TSN parameter accessors for a given priority
    # ------------------------------------------------------------------

    def effective_tas_cycle_time(self, priority=None):
        """Return TAS cycle time for this resource (shared across all TAS priorities)."""
        return self.tas_cycle_time

    def effective_tas_window_time(self, priority):
        """Return TAS window time for the given priority.

        Lookup order:
        1. tas_window_time_by_priority[priority]
        2. tas_window_time (default)
        """
        if self.tas_window_time_by_priority is not None and priority in self.tas_window_time_by_priority:
            return self.tas_window_time_by_priority[priority]
        return self.tas_window_time

    def effective_cqf_cycle_time(self, priority):
        """Return CQF cycle time for the given priority.

        Lookup order:
        1. cqf_cycle_time_by_pair[pair] (CQF pair containing this priority)
        2. cqf_cycle_time (default)
        """
        if self.cqf_cycle_time_by_pair is not None:
            pair = self.get_cqf_pair_for_priority(priority)
            if pair is not None and pair in self.cqf_cycle_time_by_pair:
                return self.cqf_cycle_time_by_pair[pair]
        return self.cqf_cycle_time

    def effective_idleslope(self, priority):
        """Return CBS idleSlope for the given priority.

        Lookup order:
        1. idleslope_by_priority[priority]
        2. idleslope (default)
        """
        if self.idleslope_by_priority is not None and priority in self.idleslope_by_priority:
            return self.idleslope_by_priority[priority]
        return self.idleslope

    def effective_is_express(self, priority):
        """Return preemption is_express flag for the given priority.

        Lookup order:
        1. is_express_by_priority[priority]
        2. is_express (default)
        """
        if self.is_express_by_priority is not None and priority in self.is_express_by_priority:
            return self.is_express_by_priority[priority]
        return self.is_express

    def effective_guard_band(self, priority):
        """Return guard band duration for the given priority.

        Lookup order:
        1. guard_band_by_priority[priority]
        2. guard_band (default)
        3. None (caller should use task-specific default behavior)

        Note: When this returns None, the caller (e.g., TASSchedulerE2E) should use
        task-specific default behavior: task.wcet for TAS flows, or computed max(wcet)
        for NST flows.
        """
        if self.guard_band_by_priority is not None and priority in self.guard_band_by_priority:
            return self.guard_band_by_priority[priority]
        return self.guard_band

    def _ats_param(self, priority, param_key):
        """Look up a single ATS parameter for the given priority.

        Lookup order:
        1. ats_params_by_priority[priority][param_key]
        2. ats_<param_key> (default)
        """
        if self.ats_params_by_priority is not None and priority in self.ats_params_by_priority:
            params = self.ats_params_by_priority[priority]
            if isinstance(params, dict) and param_key in params:
                return params[param_key]
        return getattr(self, 'ats_' + param_key, None)

    def effective_ats_cir(self, priority):
        """Return ATS Committed Information Rate for the given priority."""
        return self._ats_param(priority, 'cir')

    def effective_ats_cbs(self, priority):
        """Return ATS Committed Burst Size for the given priority."""
        return self._ats_param(priority, 'cbs')

    def effective_ats_eir(self, priority):
        """Return ATS Excess Information Rate for the given priority."""
        return self._ats_param(priority, 'eir')

    def effective_ats_ebs(self, priority):
        """Return ATS Excess Burst Size for the given priority."""
        return self._ats_param(priority, 'ebs')

    def effective_ats_scheduler_group(self, priority):
        """Return ATS scheduler group for the given priority."""
        return self._ats_param(priority, 'scheduler_group')

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_task_parameters(self, task):
        """Validate that required TSN parameters are available for the given task.

        :param task: A task bound to this resource.
        :raises ValueError: If required parameters are missing.
        """
        prio = task.scheduling_parameter
        if self.priority_uses_cbs(prio) and self.effective_idleslope(prio) is None:
            raise ValueError(
                "Task '%s' uses CBS but idleslope is not configured on its resource" % task.name)
        if self.priority_uses_tas(prio):
            if self.effective_tas_cycle_time(prio) is None or self.effective_tas_window_time(prio) is None:
                raise ValueError(
                    "Task '%s' uses TAS but tas_cycle_time or tas_window_time "
                    "is not configured on its resource" % task.name)
        if self.priority_uses_cqf(prio):
            if self.effective_cqf_cycle_time(prio) is None:
                raise ValueError(
                    "Task '%s' uses CQF but cqf_cycle_time is not configured on its resource"
                    % task.name)
        if self.priority_uses_ats(prio):
            ats_vals = [self.effective_ats_cir(prio), self.effective_ats_cbs(prio),
                        self.effective_ats_eir(prio), self.effective_ats_ebs(prio),
                        self.effective_ats_scheduler_group(prio)]
            if None in ats_vals:
                raise ValueError(
                    "Task '%s' uses ATS but some ATS parameters are not configured "
                    "on its resource" % task.name)
        return True


class Mutex(object):
    """ A mutually-exclusive shared Resource.
    Shared resources create timing interferences between tasks
    which may be executed on different resources (e.g. multi-core CPU)
    but require access to a common resource (e.g. shared main memory) to execute.
    See e.g. Chapter 5 in [Schliecker2011]_.
    """

    def __init__(self, name=None):
        """ CTOR """

        # # Set of tasks mapped to this Resource
        self.tasks = set()

        # # Resource identifier
        self.name = name

class EffectChain(object):
    """ An cause-effect chain describes a (functional) chain of independent tasks.
        All tasks within a chain are time-triggered and hence sample their input data independently.
    """
    def __init__(self, name, tasks=None):
        self.name = name
        self.tasks = tasks
        
    def add_task(self, task):
        self.tasks.append(task)

    def task_sequence(self, writers_only=False):
        """ Generates and returns the sequence of reader/writer tasks in the form of [reader_0, writer_0, reader_1, writer_1,...].
            
            A task in this sequence therefore acts either as a reader or a writer. Tasks at odd positions in this
            sequence are readers while tasks at even positions are writers.

            :param writers_only:  if true, only include writer tasks in sequence (omit readers)
            :type writers_only:   boolean
        """

        sequence = list()
        for task in self.tasks:
            # add reading and writing tasks
            if not writers_only:
                sequence.append(task)
            sequence.append(task)

        return sequence
    
class Path(object):
    """ A Path describes a (event) chain of tasks.
    Required for path analysis (e.g. end-to-end latency).
    The information stored in Path classes could be derived from the task graph
    (see Task.next_tasks and Task.prev_task),
    but having redundancy here is more flexible (e.g. path analysis may only be
    interesting for some task chains).

    Optional attribute for TAS E2E correction (set by user if needed):
    - tas_aligned (bool): If True, first hop is assumed to see no gate-closed
      blocking; if False, first hop counts one. If not set, TAS E2E correction
      is not applied.
    """

    def __init__(self, name, tasks=None):
        """ CTOR """
        # # List of tasks in Path (must be in correct order)
        if tasks is not None:
            self.tasks = tasks
            self.__link_tasks(tasks)
        else:
            self.tasks = list()
        # # create backlink to this path from the tasks
        # # so a task knows its Path
        for t in self.tasks:
            t.path = self

        # # Name of Path
        self.name = name

        ## Constant overhead to add to the latency of the path
        self.overhead = 0
        ## Optional: tas_aligned (bool). True = aligned (first hop 0 gate-closed),
        ## False = unaligned (first hop 1). None = TAS E2E correction not applied.
        self.tas_aligned = None

    def __link_tasks(self, tasks):
        """ linking all tasks along a path"""
        assert len(tasks) > 0
        if len(tasks) == 1:
            return  # This is a fake path with just one task
        for i in zip(tasks[0:-1], tasks[1:]):
            i[0].link_dependent_task(i[1])

    def __repr__(self):
        """ Return str representation """
        # return str(self.name)
        s = str(self.name) + ": "
        for c in self.tasks:
            s += " -> " + str(c)
        return s

    def print_all(self):
        """ Print all tasks in Path. Uses __str__() """
        print(str(self))


class System(object):
    """ The System is the top-level entity of the system model.
    It contains resources, junctions, tasks and paths.
    """

    def __init__(self, name=''):
        """ CTOR """

        # # Name
        self.name = name

        # Set of resources, indexed by an ID, e.g. (x,y) tuple for mesh systems
        self.resources = set()

        # # Set of task chains
        self.paths = set()

        # # Set of junctions
        self.junctions = set()

        # # constraints bookkeeping
        self.constraints = ConstraintsManager()

    def __repr__(self):
        """ Return a string representation of the System """
        s = 'paths:'
        for h in sorted(self.paths, key=str):
            s += str(h) + ", "
        s += '\nresources:'
        for r in sorted(self.resources, key=str):
            # s += str(k)+":"+str(r)+", "
            s += str(r) + ", "

        return s

    def bind_junction(self, j):
        """ Registers a junction object in the System.
            Logically, the junction neither belongs
            to a system nor to a resource,
            for sake of convenience we associate junctions with the system.
        """
        self.junctions.add(j)
        return j

    def bind_resource(self, r):
        """ Add a Resource to the System """
        self.resources.add(r)
        return r

    def get_resource_by_name(self, resource_name):
        for r in self.resources:
            if r.name == resource_name:
                return r
        return None

    def bind_path(self, path):
        """ Add a Path to the System """
        self.paths.add(path)
        # NOTE: call to "link_dependent_tasks()" on each task of the path now
        # inside Path
        return path

    def print_subgraphs(self):
        """ enumerate all subgraphs of the application graph.
        if a subgraph is not well-formed (e.g. a source is missing),
        this algorithm may
        not work correctly (it will eventually produce to many subgraphs)
        """
        subgraphs = list()
        unreachable = set()

        for resource in self.resources:
            unreachable |= set(resource.tasks)

        while len(unreachable) > 0:
            # pick one random start task (in case the app graph is not well-
            # formed)
            root_task = iter(unreachable).next()
            # but prefer a task with a source attached
            for t in unreachable:
                if t.in_event_model is not None:
                    root_task = t
                    break

            reachable = util.breadth_first_search(root_task)
            subgraphs.append(reachable)
            unreachable = unreachable - reachable

        logger.warning("Application graph consists of %d disjoint subgraphs:" %
                    len(subgraphs))

        idx = 0
        for subgraph in subgraphs:
            logger.info("Subgraph %d" % idx)
            idx += 1
            for task in subgraph:
                logger.info("\t%s" % task)

        return subgraphs
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
