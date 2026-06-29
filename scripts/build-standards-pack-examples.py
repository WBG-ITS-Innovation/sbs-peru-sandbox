# SPDX-License-Identifier: Apache-2.0
"""Extract example payloads from the OpenAPI spec to standards-pack/examples/.

Generates three JSON files:

* ``valid-anexo-1a-complaint.json`` — the ``ValidComplaintBody`` example
* ``valid-batch-manifest.json`` — the ``ValidBatchManifest`` example
* ``invalid-missing-field.json`` — a Complaint missing ``motivo_code``
  plus the expected ProblemDetail response

The first two are extracted verbatim from ``components.examples``. The
third is hand-constructed so integrators can verify their error-handling
path locally.

ADR 0039 §contains lists ``examples`` as a top-level pack directory.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import yaml


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=pathlib.Path)
    parser.add_argument("--out", required=True, type=pathlib.Path)
    args = parser.parse_args()

    spec = yaml.safe_load(args.spec.read_text(encoding="utf-8"))
    examples = spec.get("components", {}).get("examples", {})

    out: pathlib.Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    def write_named(filename: str, example_name: str) -> None:
        body = examples.get(example_name)
        if not body or "value" not in body:
            print(f"ERROR: example {example_name!r} not in spec", file=sys.stderr)
            sys.exit(2)
        (out / filename).write_text(
            json.dumps(body["value"], indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {out / filename}")

    write_named("valid-anexo-1a-complaint.json", "ValidComplaintBody")
    write_named("valid-batch-manifest.json", "ValidBatchManifest")

    # The "invalid" example carries the expected ProblemDetail response
    # so integrators can wire their error-handling against it. The
    # missing field is motivo_code, which is required by Annex 1-A.
    invalid_complaint = examples.get("ValidComplaintBody", {}).get("value", {}).copy()
    invalid_complaint.pop("motivo_code", None)
    invalid_payload = {
        "request": {
            "method": "POST",
            "path": "/v1/complaints",
            "headers": {
                "Content-Type": "application/json",
                "X-SBS-Key-Id": "sandbox-v1",
                # Illustrative UUID, not a real credential. gitleaks:allow
                "Idempotency-Key": "5d3a8c14-1a2b-4c3d-9e7f-0a1b2c3d4e5f",  # gitleaks:allow
            },
            "body": invalid_complaint,
        },
        "expected_response": {
            "status": 422,
            "headers": {
                "Content-Type": "application/problem+json",
            },
            "body": {
                "type": "https://example.invalid/sbs/errors/SBS-422-001",
                "title": "Validation failed",
                "status": 422,
                "code": "SBS-422-001",
                "detail": "One or more fields failed validation.",
                "errors": [
                    {
                        "field": "motivo_code",
                        "code": "value_error.missing",
                        "message": "Field required",
                    }
                ],
                "trace_id": "00000000000000000000000000000000",
            },
        },
        "_comment": (
            "Hand-constructed example demonstrating the ProblemDetail "
            "shape an integrator receives when a required field is "
            "missing. The trace_id field is masked; on a real request "
            "it carries the OTel trace identifier from the response "
            "traceparent header. See catalogs/error-catalog.md for the "
            "full SBS-422-001 entry."
        ),
    }
    (out / "invalid-missing-field.json").write_text(
        json.dumps(invalid_payload, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {out / 'invalid-missing-field.json'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
