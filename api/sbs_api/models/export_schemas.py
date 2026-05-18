"""Export Pydantic models to standalone JSON Schema files.

Runs as ``python -m sbs_api.models.export_schemas`` or via
``scripts/regenerate-schemas.sh``. Writes one file per public model to
``api/openapi/schemas/<ModelName>.json``.

The exported schemas are the institution-facing JSON Schema artifact, distinct
from the inline schemas inside ``api/openapi/sbs-api-v1.yaml``. Both are JSON
Schema 2020-12; ``tests/test_openapi_pydantic_match.py`` asserts that they
agree on field-level semantics (cosmetic differences tolerated).
"""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Iterable

from pydantic import BaseModel

from sbs_api.models import (
    BatchManifest,
    BatchResultRow,
    BatchStatus,
    BatchSubmission,
    Complaint,
    ComplaintCreated,
    ComplaintListItem,
    ComplaintQuery,
    ComplaintStatusPatch,
    ComplaintSubmission,
    HealthStatus,
    InstitutionStatus,
    ProblemDetail,
    VersionInfo,
)
from sbs_api.models.responses import BatchResultsResponse, ComplaintListResponse


PUBLIC_MODELS: tuple[type[BaseModel], ...] = (
    Complaint,
    ComplaintSubmission,
    ComplaintCreated,
    ComplaintListItem,
    ComplaintListResponse,
    ComplaintStatusPatch,
    ComplaintQuery,
    BatchManifest,
    BatchSubmission,
    BatchStatus,
    BatchResultRow,
    BatchResultsResponse,
    InstitutionStatus,
    HealthStatus,
    VersionInfo,
    ProblemDetail,
)


def _schemas_dir() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    # api/sbs_api/models/export_schemas.py → api/openapi/schemas
    return here.parents[2] / "openapi" / "schemas"


def export(
    models: Iterable[type[BaseModel]] = PUBLIC_MODELS,
    out_dir: pathlib.Path | None = None,
) -> list[pathlib.Path]:
    """Write JSON Schema files for *models*.

    Returns the list of paths written.
    """
    target = out_dir or _schemas_dir()
    target.mkdir(parents=True, exist_ok=True)
    written: list[pathlib.Path] = []
    for model in models:
        schema = model.model_json_schema()
        # Pin the JSON Schema dialect explicitly; Pydantic emits 2020-12.
        schema.setdefault("$schema", "https://json-schema.org/draft/2020-12/schema")
        path = target / f"{model.__name__}.json"
        path.write_text(
            json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    written = export()
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
