"""Thin Slice Lane B: JIT longitudinal read path (owned synthesis layer).

Shadow/offline slice. Nothing in production consumes these reads.

Pipeline (all steps mandatory):
  bounded pulled question
    -> Honcho-style evidence retrieval (messages only; stored conclusions QUARANTINED)
    -> Cortex authoritative joins (corrections / lifecycle / closures / boundaries)
    -> recruited synthesis (our layer; hard gates)
    -> ephemeral recruited read (never persisted as truth)

Hard gates (any violation fails the read):
  G1 correction precedence, G2 temporal cutoff (structural), G3 abstention on
  hearsay/insufficient evidence, G4 scope/frame separation,
  G5 no stored-conclusion reliance.
"""

from src.longitudinal_read.interface import ask_longitudinal
from src.longitudinal_read.models import EvidenceItem, ReadRequest, RecruitedRead

__all__ = ["ask_longitudinal", "EvidenceItem", "ReadRequest", "RecruitedRead"]
