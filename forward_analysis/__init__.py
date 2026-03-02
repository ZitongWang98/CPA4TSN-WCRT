"""
Forward End-to-End Delay Analysis for AFDX Networks

This package implements the forward analysis method from:

  Benammar N, Ridouard F, Bauer H, et al.
  "Forward end-to-end delay analysis extension for FP/FIFO policy
   in AFDX networks"[C]//2017 22nd IEEE International Conference on
  Emerging Technologies and Factory Automation (ETFA). IEEE, 2017: 1-8.

The forward analysis method computes tighter worst-case delay bounds
than traditional holistic Network Calculus by propagating Smax/Smin
hop-by-hop along each flow's path.

Supported analysis modes:
  - Theorem 2: FA-FP/FIFO without serialization effect  (Formula 9)
  - Theorem 4: FA-FP/FIFO with serialization effect     (Formula 12)

This package is designed to work alongside pyCPA: it reads from
pyCPA's model objects (System, Resource, Task, EventModel) but
runs its own analysis algorithm independently of pyCPA's CPA loop.

Usage:
    from forward_analysis import FPFIFOForwardAnalyzer
    analyzer = FPFIFOForwardAnalyzer(system)
    results = analyzer.analyze_all(with_serialization=True)
"""

from .analyzer import FPFIFOForwardAnalyzer

__all__ = ['FPFIFOForwardAnalyzer']
