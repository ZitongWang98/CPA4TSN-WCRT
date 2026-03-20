"""Frame Preemption Scheduler — thin wrapper around CQFPScheduler.

Implements the analysis from:
  [7] Luo et al., "Formal worst-case performance analysis of
      time-sensitive Ethernet with frame preemption," ETFA 2016.

When CQFPScheduler is configured without CQF pairs, it degrades to
pure express/preemptable SP analysis, which is exactly [7].
"""
from pycpa.schedulers_cqfp import CQFPScheduler


class PreemptionScheduler(CQFPScheduler):
    """Pure frame preemption (express + preemptable SP, no CQF/TAS)."""
    pass
