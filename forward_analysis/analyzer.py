"""Thin wrapper layer - re-exports from fa_fpfifo for __init__.py compatibility.

The core analysis algorithm is implemented in fa_fpfifo.py, based on:
  Benammar N, Ridouard F, Bauer H, et al.
  "Forward end-to-end delay analysis extension for FP/FIFO policy
   in AFDX networks"[C]//2017 22nd IEEE International Conference on
  Emerging Technologies and Factory Automation (ETFA). IEEE, 2017: 1-8.
"""
from .fa_fpfifo import FPFIFOForwardAnalyzer, HopResult, AnalysisResult

__all__ = ['FPFIFOForwardAnalyzer', 'HopResult', 'AnalysisResult']
