"""ADR 0034 §proportional-treatment invariant — code-identity test.

The proportional-treatment claim ("Tier 1 and Tier 2 land in the same
downstream pipeline") relies on the batch worker validating rows
through the *same* Pydantic model object as the Tier 1 endpoint, not a
look-alike copy. The test asserts class identity (`is`) so a refactor
that introduces a parallel validation path is detected here, not at
production-data time.
"""

from __future__ import annotations


def test_batch_worker_imports_tier_1_complaint_model():
    from sbs_api.models.anexo_1a import Complaint
    from sbs_api.workers.batch_worker import TIER_1_COMPLAINT_MODEL

    assert TIER_1_COMPLAINT_MODEL is Complaint, (
        "Tier 2 batch worker must validate through the same Complaint "
        "class as Tier 1. ADR 0034 §proportional-treatment."
    )


def test_complaint_submission_wraps_same_complaint_model():
    """The Tier 1 endpoint's ComplaintSubmission carries `complaint: Complaint`.

    The model field's type annotation must resolve to the same class
    the batch worker uses.
    """

    from sbs_api.models.anexo_1a import Complaint
    from sbs_api.models.requests import ComplaintSubmission

    field = ComplaintSubmission.model_fields["complaint"]
    assert field.annotation is Complaint, (
        "ComplaintSubmission.complaint annotation drifted away from "
        "the canonical Complaint class. Restore the import or update "
        "the invariant in this test."
    )
