"""FI-facing outbound webhook delivery (P-RESHAPE-4).

Distinct from :mod:`sbs_api.webhook` (the Tier-2 batch callback path).
This package delivers approved Issue Resurface briefs to an FI's
conduct-officer endpoint, reusing the existing HMAC signing helpers
from :mod:`sbs_api.webhook.signing` — auth/signature are NOT
reimplemented here.
"""
