# SPDX-License-Identifier: Apache-2.0
"""Social-media signal ingestion (P-RESHAPE-6).

The adapter interface is production-shaped; only the fixture adapter is
wired for the sandbox. Twitter / Meta adapters are stubs that refuse to
run without real credentials, so a deployment slip cannot silently make
live API calls.
"""

from sbs_api.ingestion.social.adapter_base import SocialAdapter, SocialSignalRaw
from sbs_api.ingestion.social.entity_resolver import resolve_institution_codes
from sbs_api.ingestion.social.fixture_adapter import FixtureSocialAdapter

__all__ = [
    "FixtureSocialAdapter",
    "SocialAdapter",
    "SocialSignalRaw",
    "resolve_institution_codes",
]
