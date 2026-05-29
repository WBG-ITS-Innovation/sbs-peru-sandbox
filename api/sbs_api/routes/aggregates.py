"""Grouped-aggregate endpoint over the enriched complaints data.

GET /v1/internal/aggregates/patterns?scope=entity|group|all

Every number is computed from SQL over ``complaints`` + ``institutions`` —
nothing is hardcoded. Rows are grouped by (motivo_code, submotivo, topic),
plus a per-scope institution dimension:

* ``entity`` (default) — adds ``institution_id``.
* ``group``            — adds the peer ``cohort_id`` (segment:tier), derived
                         via :func:`sbs_api.peer_risk.cohorts.assign_cohort`.
* ``all``              — no institution dimension.

Favour percentages are over RESOLVED complaints only (``tipo_resolucion``
not null): ``pct_favor_user`` + ``pct_favor_bank`` + ``pct_partial`` sum to
100% of resolved. A bucket with no resolved complaints returns ``null`` for
all three — never a fabricated 0. ``n_pending`` lets the UI show the honest
unresolved share.

Auth mirrors the other ``/v1/internal/*`` routes: the shared-secret Bearer
guard (:func:`verify_internal_secret`).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.db.models.complaint import ComplaintRecord
from sbs_api.db.models.institution import InstitutionRecord
from sbs_api.dependencies.db import get_session
from sbs_api.observability.logging import get_logger
from sbs_api.peer_risk.cohorts import CohortAssignmentError, assign_cohort
from sbs_api.routes._internal_auth import verify_internal_secret

log = get_logger(__name__)

router = APIRouter(prefix="/internal/aggregates", tags=["Internal"])

Scope = Literal["entity", "group", "all"]

# tipo_resolucion follows the Anexo 1-A TIP_RES convention. The enrichment
# writes exactly these three labels; match by equality (not pattern) so the
# counts are unambiguous. solucion_parcial is neither user- nor bank-
# favouring, so pct_favor_user + pct_favor_bank + pct_partial = 100% of
# resolved complaints — the partial share is surfaced explicitly.
_LABEL_FAVOR_USER = "favor_usuario"
_LABEL_FAVOR_BANK = "favor_entidad"
_LABEL_PARTIAL = "solucion_parcial"


def _cohort_for(display_name: str, tier_classification: str | None) -> dict[str, str]:
    """(cohort_id, segment, size_tier) for an institution. Calls the canonical
    cohort logic; falls back to a derived label only if that raises."""
    try:
        c = assign_cohort(
            display_name=display_name, tier_classification=tier_classification
        )
        return {
            "cohort_id": c.cohort_id,
            "segment": c.segment.value,
            "size_tier": c.size_tier.value,
        }
    except CohortAssignmentError:
        segment = (display_name.split("_", 1)[0].upper() if display_name else "OTHER")
        tier = (tier_classification or "unknown").upper()
        return {"cohort_id": f"{segment}:{tier}", "segment": segment, "size_tier": tier}


def _pct(numer: int, denom: int) -> float | None:
    """Percentage 0–100 (1 decimal), or None when the denominator is 0 —
    an honest 'no resolved complaints', never a fabricated 0."""
    if denom <= 0:
        return None
    return round(100.0 * numer / denom, 1)


@router.get(
    "/patterns",
    dependencies=[Depends(verify_internal_secret)],
)
async def get_aggregate_patterns(
    scope: Scope = Query(default="entity"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    try:
        # One SQL pass at the finest (per-institution) grain with raw counts;
        # the scope-specific roll-up happens in Python so the cohort logic in
        # peer_risk.cohorts is reused rather than reimplemented in SQL.
        favor_user = func.count().filter(
            ComplaintRecord.tipo_resolucion == _LABEL_FAVOR_USER
        )
        favor_bank = func.count().filter(
            ComplaintRecord.tipo_resolucion == _LABEL_FAVOR_BANK
        )
        favor_partial = func.count().filter(
            ComplaintRecord.tipo_resolucion == _LABEL_PARTIAL
        )
        stmt = (
            select(
                ComplaintRecord.institution_id,
                InstitutionRecord.display_name,
                InstitutionRecord.tier_classification,
                ComplaintRecord.motivo_code,
                ComplaintRecord.submotivo,
                ComplaintRecord.submotivo_2,
                ComplaintRecord.topic,
                func.count().label("n_complaints"),
                func.count()
                .filter(ComplaintRecord.resolution_status == "pendiente")
                .label("n_pending"),
                func.count()
                .filter(ComplaintRecord.tipo_resolucion.is_not(None))
                .label("n_resolved"),
                favor_user.label("n_favor_user"),
                favor_bank.label("n_favor_bank"),
                favor_partial.label("n_favor_partial"),
                func.array_agg(ComplaintRecord.complaint_id).label("complaint_ids"),
            )
            .join(
                InstitutionRecord,
                InstitutionRecord.institution_id == ComplaintRecord.institution_id,
            )
            .group_by(
                ComplaintRecord.institution_id,
                InstitutionRecord.display_name,
                InstitutionRecord.tier_classification,
                ComplaintRecord.motivo_code,
                ComplaintRecord.submotivo,
                ComplaintRecord.submotivo_2,
                ComplaintRecord.topic,
            )
        )
        base = (await session.execute(stmt)).all()
    except Exception:  # noqa: BLE001 — degrade to empty, never fabricate.
        log.warning("aggregates.patterns.query_failed", scope=scope, exc_info=True)
        return {
            "scope": scope,
            "generated_at": generated_at,
            "total_in_scope": 0,
            "rows": [],
        }

    # Fold the per-institution base rows into the requested scope.
    buckets: dict[tuple, dict[str, Any]] = {}
    cohort_cache: dict[str, dict[str, str]] = {}
    total = 0

    for r in base:
        total += r.n_complaints
        dims: dict[str, Any] = {
            "motivo_code": r.motivo_code,
            "submotivo": r.submotivo,
            "submotivo_2": r.submotivo_2,
            "topic": r.topic,
        }
        if scope == "entity":
            dims["institution_id"] = r.institution_id
            dims["institution_name"] = r.display_name
            key = (r.institution_id, r.motivo_code, r.submotivo, r.submotivo_2, r.topic)
        elif scope == "group":
            coh = cohort_cache.get(r.institution_id)
            if coh is None:
                coh = _cohort_for(r.display_name, r.tier_classification)
                cohort_cache[r.institution_id] = coh
            dims.update(coh)
            key = (coh["cohort_id"], r.motivo_code, r.submotivo, r.submotivo_2, r.topic)
        else:  # all
            key = (r.motivo_code, r.submotivo, r.submotivo_2, r.topic)

        b = buckets.get(key)
        if b is None:
            b = {
                **dims,
                "n_complaints": 0,
                "n_pending": 0,
                "n_resolved": 0,
                "n_favor_user": 0,
                "n_favor_bank": 0,
                "n_favor_partial": 0,
                "_ids": [],
            }
            buckets[key] = b
        b["n_complaints"] += r.n_complaints
        b["n_pending"] += r.n_pending
        b["n_resolved"] += r.n_resolved
        b["n_favor_user"] += r.n_favor_user
        b["n_favor_bank"] += r.n_favor_bank
        b["n_favor_partial"] += r.n_favor_partial
        b["_ids"].extend(r.complaint_ids or [])

    rows: list[dict[str, Any]] = []
    for b in buckets.values():
        # Raw numerators stay in the row so every percentage is reconstructable.
        b["pct_of_all"] = _pct(b["n_complaints"], total)
        b["pct_favor_user"] = _pct(b["n_favor_user"], b["n_resolved"])
        b["pct_favor_bank"] = _pct(b["n_favor_bank"], b["n_resolved"])
        b["pct_partial"] = _pct(b["n_favor_partial"], b["n_resolved"])
        # Contributing complaint ids for the "Ver reclamos" drill-in (capped).
        b["complaint_ids"] = sorted(b.pop("_ids"))[:100]
        rows.append(b)

    rows.sort(key=lambda x: x["n_complaints"], reverse=True)

    return {
        "scope": scope,
        "generated_at": generated_at,
        "total_in_scope": total,
        "rows": rows,
    }
