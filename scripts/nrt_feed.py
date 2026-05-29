#!/usr/bin/env python
"""Near-real-time live trickle: POST a NEW synthetic complaint every few
seconds through the REAL Tier-1 sandbox ingestion path.

This is REAL ingestion of SYNTHETIC data on a timer — NOT a fake animation.
Each tick builds a randomised Anexo-1A-shaped payload (random institution,
motivo, product, channel, Peruvian-Spanish narrative) and sends it through
the full security chain (OAuth client_credentials + HMAC SHA-256 +
Idempotency-Key + dev XFCC) to ``POST /v1/sandbox/complaints/granular`` —
exactly the path ``scripts/institution_push_demo.py`` uses. The SBS side
redacts, runs data-quality + the agent pipeline, persists a canonical
``complaints`` row (``source='api_realtime'``), and publishes on the live
SSE feed — so the cockpit's live-ingestion banner updates on its own.

Only the two institutions that have a seeded auth bundle (HMAC secret + dev
cert) can push: banco-tier1 (SBS-001234) and coopac-tier2 (SBS-005678).
FINANCIERA (SBS-009012) has no Tier-1 credentials seeded, so it is not in
the rotation.

Usage (local sandbox; API in SBS_API_MTLS_MODE=proxy):

    .venv/bin/python scripts/nrt_feed.py --insecure-skip-mtls
    .venv/bin/python scripts/nrt_feed.py --rate 6 --jitter 2 --insecure-skip-mtls
    .venv/bin/python scripts/nrt_feed.py --count 10 --insecure-skip-mtls   # then stop

Stop with Ctrl-C.
"""

from __future__ import annotations

import argparse
import random
import secrets
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import httpx  # noqa: E402

from institution_push_demo import (  # noqa: E402
    PROFILES,
    Profile,
    _dev_proxy_headers,
    _fetch_token,
    _make_client,
    _post_complaint,
)

# Only profiles with a seeded HMAC secret + dev cert can push Tier-1.
ROTATION = ["banco-tier1", "coopac-tier2"]

MOTIVOS = [
    "COBRO_INDEBIDO",
    "OPERACION_NO_RECONOCIDA",
    "DEMORA_ATENCION",
    "INCUMPLIMIENTO_CONTRATO",
    "CALIDAD_SERVICIO",
    "INFORMACION_INCORRECTA",
]
PRODUCTS = ["TARJETA_CREDITO", "CREDITOS", "DEPOSITOS", "TARJETA_DEBITO", "SEGUROS"]
CHANNELS = ["APP_MOVIL", "WEB", "AGENCIA", "TELEFONO"]
SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

_PRODUCT_ES = {
    "TARJETA_CREDITO": "tarjeta de crédito",
    "CREDITOS": "crédito",
    "DEPOSITOS": "cuenta de ahorros",
    "TARJETA_DEBITO": "tarjeta de débito",
    "SEGUROS": "seguro asociado",
}
_CHANNEL_ES = {
    "APP_MOVIL": "la app móvil",
    "WEB": "la banca por internet",
    "AGENCIA": "la agencia",
    "TELEFONO": "la banca telefónica",
}

# Synthetic Peruvian-Spanish narratives. {p}=product prose, {a}=amount,
# {c}=channel prose, {d}=date. No real PII — the endpoint redacts anyway.
_TEMPLATES = [
    "Se realizó un cargo no reconocido por S/ {a} en mi {p} el {d}. Lo detecté revisando {c} y solicito la reversión inmediata.",
    "El {d} intenté una operación por S/ {a} en {p} usando {c} y el sistema mostró un error, pero el monto fue descontado igual.",
    "Reclamo por una comisión de S/ {a} en mi {p} que no me informaron al momento de la contratación. Pido la devolución.",
    "Llevo más de {d2} días esperando respuesta sobre un cobro de S/ {a} en mi {p}. La atención por {c} no resolvió nada.",
    "Mi {p} registra un consumo de S/ {a} que no realicé. Reporté el caso por {c} pero no recibo solución.",
    "La tasa aplicada a mi {p} no coincide con lo pactado; la diferencia suma S/ {a} desde el {d}. Solicito corrección.",
]


def _amount(rng: random.Random) -> str:
    return f"{round(rng.uniform(30, 6000), 2):.2f}"


def _recent_date(rng: random.Random) -> str:
    from datetime import timedelta

    d = datetime.now(timezone.utc).date() - timedelta(days=rng.randint(0, 30))
    return d.isoformat()


def _build_payload(rng: random.Random, profile: Profile) -> dict:
    product = rng.choice(PRODUCTS)
    channel = rng.choice(CHANNELS)
    motivo = rng.choice(MOTIVOS)
    narrative = rng.choice(_TEMPLATES).format(
        p=_PRODUCT_ES[product],
        a=_amount(rng),
        c=_CHANNEL_ES[channel],
        d=_recent_date(rng),
        d2=rng.randint(16, 45),
    )
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "institution_id": profile.institution_id,
        "institution_name": profile.institution_display,
        "client_submission_id": f"nrt-{secrets.token_hex(4)}",
        "received_at": now_iso,
        "demo_scenario": "nrt-trickle",
        "institution_complaint_id": f"NRT-{secrets.token_hex(3).upper()}",
        "channel_in": channel,
        "channel_operation": channel,
        "product": product,
        "motive": motivo,
        "narrative": narrative,
        "response_detail": None,
        "status": "pendiente",
        "severity": rng.choice(SEVERITIES),
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    p.add_argument("--api-base", default="http://localhost:8000/v1")
    p.add_argument("--rate", type=float, default=6.0, help="Seconds between POSTs (default 6).")
    p.add_argument("--jitter", type=float, default=2.0, help="Random +/- seconds added to rate (default 2).")
    p.add_argument("--count", type=int, default=0, help="Stop after N complaints (0 = run until Ctrl-C).")
    p.add_argument("--seed", type=int, default=None, help="Optional RNG seed (default: nondeterministic).")
    p.add_argument(
        "--insecure-skip-mtls",
        action="store_true",
        help="Local sandbox only: send dev XFCC header instead of a TLS client cert (API in SBS_API_MTLS_MODE=proxy).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    rng = random.Random(args.seed)

    clients: dict[str, httpx.Client] = {}
    tokens: dict[str, str] = {}

    def _client(profile: Profile) -> httpx.Client:
        if profile.name not in clients:
            clients[profile.name] = _make_client(
                api_base=args.api_base, profile=profile, insecure_skip_mtls=args.insecure_skip_mtls
            )
        return clients[profile.name]

    def _token(profile: Profile, refresh: bool = False) -> str:
        if refresh or profile.name not in tokens:
            tokens[profile.name] = _fetch_token(
                _client(profile),
                api_base=args.api_base,
                profile=profile,
                dev_proxy_headers=_dev_proxy_headers(
                    profile=profile, insecure_skip_mtls=args.insecure_skip_mtls
                ),
            )
        return tokens[profile.name]

    print(
        f"nrt_feed: rate={args.rate}s jitter=±{args.jitter}s rotation={ROTATION} "
        f"api_base={args.api_base} count={'∞' if args.count == 0 else args.count}",
        flush=True,
    )
    sent = 0
    try:
        while args.count == 0 or sent < args.count:
            profile = PROFILES[rng.choice(ROTATION)]
            payload = _build_payload(rng, profile)
            dev_headers = _dev_proxy_headers(
                profile=profile, insecure_skip_mtls=args.insecure_skip_mtls
            )
            try:
                resp, _ts, _sig = _post_complaint(
                    _client(profile),
                    api_base=args.api_base,
                    profile=profile,
                    token=_token(profile),
                    body_dict=payload,
                    idempotency_key=f"nrt-{uuid.uuid4().hex[:24]}",
                    dev_proxy_headers=dev_headers,
                )
                if resp.status_code == 401:  # token expired → refresh once
                    resp, _ts, _sig = _post_complaint(
                        _client(profile),
                        api_base=args.api_base,
                        profile=profile,
                        token=_token(profile, refresh=True),
                        body_dict=payload,
                        idempotency_key=f"nrt-{uuid.uuid4().hex[:24]}",
                        dev_proxy_headers=dev_headers,
                    )
                ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
                if resp.status_code in (200, 201):
                    cid = (resp.json() or {}).get("complaint_id", "?")
                    sent += 1
                    print(
                        f"[{ts}] #{sent:>3} POST {profile.institution_id} "
                        f"motivo={payload['motive']:<24} → 201 complaint_id={cid}",
                        flush=True,
                    )
                else:
                    print(
                        f"[{ts}] POST {profile.institution_id} → HTTP {resp.status_code}: "
                        f"{resp.text[:160]}",
                        flush=True,
                    )
            except Exception as exc:  # noqa: BLE001 — keep the loop alive
                print(f"[error] {type(exc).__name__}: {exc}", flush=True)

            if args.count == 0 or sent < args.count:
                delay = max(0.5, args.rate + rng.uniform(-args.jitter, args.jitter))
                time.sleep(delay)
    except KeyboardInterrupt:
        print(f"\nnrt_feed: stopped after {sent} complaints.", flush=True)
    finally:
        for c in clients.values():
            c.close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
