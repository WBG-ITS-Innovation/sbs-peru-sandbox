# SPDX-License-Identifier: Apache-2.0
"""Webhook URL validation — Workstream D (ADR 0035 §webhook-url-validation).

The validation module enforces HTTPS / FQDN / public-IP. The env
override allows bypass in dev / test only; the staging/prod refusal
is enforced at app boot (asserted in test_app_factory).
"""

from __future__ import annotations

import socket
from unittest.mock import patch

import pytest

from sbs_api.webhook.url_validation import validate_callback_url


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    from sbs_api.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _public_ip_resolution(*args, **kwargs):
    return [(socket.AF_INET, None, None, "", ("8.8.8.8", 0))]


def _private_ip_resolution(*args, **kwargs):
    return [(socket.AF_INET, None, None, "", ("192.168.1.10", 0))]


def _metadata_ip_resolution(*args, **kwargs):
    return [(socket.AF_INET, None, None, "", ("169.254.169.254", 0))]


def _loopback_resolution(*args, **kwargs):
    return [(socket.AF_INET, None, None, "", ("127.0.0.1", 0))]


def test_https_required_in_strict_mode(monkeypatch):
    monkeypatch.setenv("SBS_API_ALLOW_INSECURE_WEBHOOK_URLS", "false")
    monkeypatch.setenv("SBS_API_ENVIRONMENT", "prod")
    with patch("socket.getaddrinfo", side_effect=_public_ip_resolution):
        result = validate_callback_url(
            "http://webhook.example.com/sbs-callback"
        )
    assert result.valid is False
    assert "https" in (result.reason or "")


def test_fqdn_required_in_strict_mode(monkeypatch):
    monkeypatch.setenv("SBS_API_ALLOW_INSECURE_WEBHOOK_URLS", "false")
    monkeypatch.setenv("SBS_API_ENVIRONMENT", "prod")
    with patch("socket.getaddrinfo", side_effect=_public_ip_resolution):
        result = validate_callback_url(
            "https://listener/sbs-callback"
        )
    assert result.valid is False
    assert "fully-qualified" in (result.reason or "")


def test_ip_literal_host_rejected_in_strict_mode(monkeypatch):
    monkeypatch.setenv("SBS_API_ALLOW_INSECURE_WEBHOOK_URLS", "false")
    monkeypatch.setenv("SBS_API_ENVIRONMENT", "prod")
    result = validate_callback_url("https://8.8.8.8/sbs-callback")
    assert result.valid is False
    assert "fully-qualified" in (result.reason or "")


def test_private_ip_resolution_rejected(monkeypatch):
    monkeypatch.setenv("SBS_API_ALLOW_INSECURE_WEBHOOK_URLS", "false")
    monkeypatch.setenv("SBS_API_ENVIRONMENT", "prod")
    with patch("socket.getaddrinfo", side_effect=_private_ip_resolution):
        result = validate_callback_url(
            "https://webhook.example.com/sbs-callback"
        )
    assert result.valid is False
    assert "non-public" in (result.reason or "")


def test_aws_metadata_ip_rejected(monkeypatch):
    monkeypatch.setenv("SBS_API_ALLOW_INSECURE_WEBHOOK_URLS", "false")
    monkeypatch.setenv("SBS_API_ENVIRONMENT", "prod")
    with patch("socket.getaddrinfo", side_effect=_metadata_ip_resolution):
        result = validate_callback_url(
            "https://webhook.example.com/sbs-callback"
        )
    assert result.valid is False
    assert "non-public" in (result.reason or "")


def test_loopback_rejected(monkeypatch):
    monkeypatch.setenv("SBS_API_ALLOW_INSECURE_WEBHOOK_URLS", "false")
    monkeypatch.setenv("SBS_API_ENVIRONMENT", "prod")
    with patch("socket.getaddrinfo", side_effect=_loopback_resolution):
        result = validate_callback_url(
            "https://webhook.example.com/sbs-callback"
        )
    assert result.valid is False


def test_happy_path_https_fqdn_public_ip(monkeypatch):
    monkeypatch.setenv("SBS_API_ALLOW_INSECURE_WEBHOOK_URLS", "false")
    monkeypatch.setenv("SBS_API_ENVIRONMENT", "prod")
    with patch("socket.getaddrinfo", side_effect=_public_ip_resolution):
        result = validate_callback_url(
            "https://webhook.example.com/sbs-callback"
        )
    assert result.valid is True
    assert result.reason is None


def test_dev_override_bypasses_all_checks(monkeypatch):
    monkeypatch.setenv("SBS_API_ALLOW_INSECURE_WEBHOOK_URLS", "true")
    monkeypatch.setenv("SBS_API_ENVIRONMENT", "dev")
    # http + bare hostname + private IP — bypassed.
    result = validate_callback_url("http://webhook-listener:8080/sbs-callback")
    assert result.valid is True


def test_test_env_override_bypasses_all_checks(monkeypatch):
    monkeypatch.setenv("SBS_API_ALLOW_INSECURE_WEBHOOK_URLS", "true")
    monkeypatch.setenv("SBS_API_ENVIRONMENT", "test")
    result = validate_callback_url("http://webhook-listener:8080/sbs-callback")
    assert result.valid is True


def test_unresolvable_host_rejected(monkeypatch):
    monkeypatch.setenv("SBS_API_ALLOW_INSECURE_WEBHOOK_URLS", "false")
    monkeypatch.setenv("SBS_API_ENVIRONMENT", "prod")
    with patch("socket.getaddrinfo", side_effect=OSError("not found")):
        result = validate_callback_url(
            "https://nonexistent.invalid/sbs-callback"
        )
    assert result.valid is False
    assert "did not resolve" in (result.reason or "")


def test_app_refuses_to_boot_with_override_in_prod(monkeypatch):
    monkeypatch.setenv("SBS_API_ALLOW_INSECURE_WEBHOOK_URLS", "true")
    monkeypatch.setenv("SBS_API_ENVIRONMENT", "prod")
    monkeypatch.setenv(
        "SBS_API_DATABASE_URL",
        "postgresql+asyncpg://sbs:sbs@localhost:5432/test_sbs",  # pragma: allowlist secret
    )
    from sbs_api.app import create_app
    from sbs_api.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="ALLOW_INSECURE_WEBHOOK_URLS"):
        create_app()
