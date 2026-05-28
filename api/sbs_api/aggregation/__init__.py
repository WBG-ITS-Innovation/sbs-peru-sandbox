"""Deterministic pattern-aggregation job (P-RESHAPE-2).

This package runs **outside** the agent layer. It scans rolling
windows of the canonical complaints stream, joins INDECOPI cases for
the cross-source rule, and emits ``pattern_detections`` rows. The
orchestrator picks each HIGH-severity row up and fires the
Investigation agent against it (the second of two trigger sources;
the first remains per-complaint ``system_signal``).

No LLM calls, no agents — pure SQL + Python so the audit chain stays
reproducible and the tick stays cheap.
"""

from sbs_api.aggregation.detector import (
    FraudCandidate,
    PatternCandidate,
    PatternType,
    detect_fraud_emergence,
    detect_patterns,
)
from sbs_api.aggregation.severity import (
    FRAUD_WEIGHTS,
    LOCKED_WEIGHTS,
    FraudSeverityInputs,
    SeverityBand,
    SeverityInputs,
    SeverityResult,
    score_fraud_severity,
    score_severity,
)
from sbs_api.aggregation.windower import (
    BucketWindow,
    FraudWindow,
    build_fraud_windows,
    build_windows,
)

__all__ = [
    "BucketWindow",
    "FRAUD_WEIGHTS",
    "FraudCandidate",
    "FraudSeverityInputs",
    "FraudWindow",
    "LOCKED_WEIGHTS",
    "PatternCandidate",
    "PatternType",
    "SeverityBand",
    "SeverityInputs",
    "SeverityResult",
    "build_fraud_windows",
    "build_windows",
    "detect_fraud_emergence",
    "detect_patterns",
    "score_fraud_severity",
    "score_severity",
]
