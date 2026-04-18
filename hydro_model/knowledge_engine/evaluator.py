"""Quality evaluation framework.

Scores every MineResult along four dimensions:
  1. Completeness  — are required fields populated?
  2. Precision     — numeric resolution / coordinate decimal places
  3. Freshness     — how recent is the source data?
  4. Consistency   — does it agree with other sources for the same entity?

The composite score (0-1) determines whether a result is consolidated
into the knowledge layer automatically or flagged for human review.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .registry import MineResult
from .taxonomy import DOMAIN_OF, DataType, Domain

log = logging.getLogger(__name__)

# Weights for composite score
W_COMPLETENESS = 0.30
W_PRECISION = 0.25
W_FRESHNESS = 0.20
W_CONSISTENCY = 0.25

AUTO_ACCEPT_THRESHOLD = 0.60
REVIEW_THRESHOLD = 0.35


@dataclass
class QualityScore:
    completeness: float = 0.0
    precision: float = 0.0
    freshness: float = 0.0
    consistency: float = 0.0

    @property
    def composite(self) -> float:
        return round(
            W_COMPLETENESS * self.completeness
            + W_PRECISION * self.precision
            + W_FRESHNESS * self.freshness
            + W_CONSISTENCY * self.consistency,
            4,
        )

    @property
    def verdict(self) -> str:
        c = self.composite
        if c >= AUTO_ACCEPT_THRESHOLD:
            return "auto_accept"
        if c >= REVIEW_THRESHOLD:
            return "review_required"
        return "reject"


@dataclass
class EvalResult:
    mine_result: MineResult
    quality: QualityScore
    issues: list[str] = field(default_factory=list)


# ── Dimension scorers ───────────────────────────────────────────────────────

_REQUIRED_FIELDS: dict[Domain, list[str]] = {
    Domain.GEOSPATIAL: ["format", "crs"],
    Domain.INFRASTRUCTURE: ["name"],
    Domain.STATIONS: ["name", "lon", "lat"],
    Domain.TOPOLOGY: ["nodes"],
    Domain.HYDRAULIC: ["data_points"],
    Domain.TIMESERIES: ["variable", "n_records"],
}


def _score_completeness(mr: MineResult) -> tuple[float, list[str]]:
    domain = DOMAIN_OF.get(mr.data_type)
    required = _REQUIRED_FIELDS.get(domain, []) if domain else []
    if not required:
        return (0.5, [])
    present = sum(1 for k in required if mr.payload.get(k) is not None)
    score = present / len(required)
    issues = [f"missing: {k}" for k in required if mr.payload.get(k) is None]
    return (score, issues)


def _score_precision(mr: MineResult) -> float:
    prec = mr.payload.get("precision")
    if prec is not None:
        return min(1.0, prec / 6.0)
    n = mr.payload.get("data_points") or mr.payload.get("n_records") or 0
    if n > 1000:
        return 1.0
    if n > 100:
        return 0.7
    if n > 10:
        return 0.5
    if n > 0:
        return 0.3
    return 0.1


def _score_freshness(mr: MineResult) -> float:
    ts = mr.payload.get("modified") or mr.payload.get("updated_at")
    if not ts:
        return 0.3
    try:
        if isinstance(ts, str):
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        else:
            dt = ts
        age_days = (datetime.now(timezone.utc) - dt).days
        if age_days < 30:
            return 1.0
        if age_days < 180:
            return 0.8
        if age_days < 365:
            return 0.6
        if age_days < 730:
            return 0.4
        return 0.2
    except Exception:
        return 0.3


def _score_consistency(
    mr: MineResult,
    peers: list[MineResult],
) -> float:
    if not peers:
        return 0.5
    if mr.data_type in (
        DataType.HYDRO_STATION, DataType.RAINFALL_STATION, DataType.EVAP_STATION,
    ):
        my_name = mr.payload.get("name", "")
        my_lat = mr.payload.get("lat")
        my_lon = mr.payload.get("lon")
        if my_lat is None or my_lon is None:
            return 0.3
        agrees = 0
        for p in peers:
            if p is mr or p.source_path == mr.source_path:
                continue
            plat = p.payload.get("lat")
            plon = p.payload.get("lon")
            pname = p.payload.get("name", "")
            if plat is None or plon is None or pname != my_name:
                continue
            dist_deg = ((plat - my_lat) ** 2 + (plon - my_lon) ** 2) ** 0.5
            if dist_deg < 0.05:
                agrees += 1
        if agrees >= 2:
            return 1.0
        if agrees == 1:
            return 0.7
        return 0.3
    return 0.5


# ── Orchestrator ────────────────────────────────────────────────────────────

def evaluate_results(
    results_by_type: dict[str, list[MineResult]],
) -> dict[str, list[EvalResult]]:
    """Evaluate all mine results.  Returns same grouping with scores attached."""
    evaluated: dict[str, list[EvalResult]] = {}

    for dt_key, results in results_by_type.items():
        evals: list[EvalResult] = []
        for mr in results:
            compl, issues = _score_completeness(mr)
            prec = _score_precision(mr)
            fresh = _score_freshness(mr)
            consist = _score_consistency(mr, results)
            q = QualityScore(
                completeness=round(compl, 3),
                precision=round(prec, 3),
                freshness=round(fresh, 3),
                consistency=round(consist, 3),
            )
            evals.append(EvalResult(mine_result=mr, quality=q, issues=issues))
        evals.sort(key=lambda e: -e.quality.composite)
        evaluated[dt_key] = evals

    return evaluated


def summary_report(
    evaluated: dict[str, list[EvalResult]],
) -> dict[str, Any]:
    """Generate a human-readable quality summary."""
    by_verdict: dict[str, int] = {"auto_accept": 0, "review_required": 0, "reject": 0}
    type_summaries: dict[str, dict] = {}

    for dt_key, evals in evaluated.items():
        best_score = evals[0].quality.composite if evals else 0.0
        count = len(evals)
        verdict = evals[0].quality.verdict if evals else "reject"
        by_verdict[verdict] = by_verdict.get(verdict, 0) + 1
        type_summaries[dt_key] = {
            "count": count,
            "best_score": best_score,
            "verdict": verdict,
        }

    return {
        "total_types_evaluated": len(evaluated),
        "verdict_distribution": by_verdict,
        "type_summaries": type_summaries,
    }
