"""Approvals queue + detail + decision endpoints (Prompt 10 / WS5)."""

from sbs_api.approvals.builder import (
    build_approval_detail,
    build_approvals_queue,
)

__all__ = ["build_approval_detail", "build_approvals_queue"]
