// SPDX-License-Identifier: Apache-2.0
/**
 * Webhook signature verification for the SBS SupTech Complaints API.
 *
 * Hand-maintained, ~150 lines, uses only `node:crypto` from the
 * standard Node.js library — no external dependencies. Per
 * [ADR 0038](../../docs/adr/0038-sdk-helper-scope-and-distribution.md)
 * this helper is intentionally tiny: it verifies the
 * `X-SBS-Signature` header on outbound webhook callbacks and does
 * nothing else.
 *
 * The canonical request shape mirrors the server-side outbound signer
 * in `api/sbs_api/webhook/signing.py` byte-for-byte. See
 * [ADR 0035](../../docs/adr/0035-outbound-webhook-signing-contract.md)
 * for the contract.
 */

import { createHash, createHmac, timingSafeEqual } from 'node:crypto';

export const ALGORITHM_PREFIX = 'hmac-sha256-v1=';
export const KEY_ID_SANDBOX_V1 = 'sandbox-v1';
export const MAX_CLOCK_SKEW_SECONDS = 300;

const EMPTY_BODY_SHA256_HEX = createHash('sha256').update(Buffer.alloc(0)).digest('hex');

// ---- Exception classes ------------------------------------------------------

export class WebhookVerificationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'WebhookVerificationError';
  }
}

export class SignatureInvalidError extends WebhookVerificationError {
  constructor(message: string) {
    super(message);
    this.name = 'SignatureInvalidError';
  }
}

export class SignatureExpiredError extends WebhookVerificationError {
  constructor(message: string) {
    super(message);
    this.name = 'SignatureExpiredError';
  }
}

export class KeyIdUnknownError extends WebhookVerificationError {
  constructor(message: string) {
    super(message);
    this.name = 'KeyIdUnknownError';
  }
}

// ---- Public surface ---------------------------------------------------------

/**
 * Constant-time bytes comparison. Use this instead of `===` whenever
 * comparing signature material — `===` can leak the position of the
 * first differing byte through timing.
 */
export function constantTimeCompare(a: Buffer | string, b: Buffer | string): boolean {
  const ba = Buffer.isBuffer(a) ? a : Buffer.from(a, 'utf8');
  const bb = Buffer.isBuffer(b) ? b : Buffer.from(b, 'utf8');
  if (ba.length !== bb.length) {
    return false;
  }
  return timingSafeEqual(ba, bb);
}

export interface CanonicalRequestParams {
  method: string;
  callbackPath: string;
  timestamp: string;
  rawBody: Buffer;
  institutionId: string;
}

/**
 * Build the five-line canonical request per ADR 0035.
 *
 * Lines are joined by `\n` (LF, never CRLF) and UTF-8 encoded.
 *   1. HTTP method, uppercased.
 *   2. Callback path-and-query (no scheme, no host).
 *   3. `X-SBS-Timestamp` value, verbatim.
 *   4. Lowercase hex SHA-256 of the raw body bytes.
 *   5. `institutionId`.
 */
export function canonicalizeRequest({
  method,
  callbackPath,
  timestamp,
  rawBody,
  institutionId,
}: CanonicalRequestParams): Buffer {
  const bodyHash =
    rawBody.length === 0
      ? EMPTY_BODY_SHA256_HEX
      : createHash('sha256').update(rawBody).digest('hex');
  const lines = [
    method.toUpperCase(),
    callbackPath,
    timestamp,
    bodyHash,
    institutionId,
  ].join('\n');
  return Buffer.from(lines, 'utf8');
}

/** Return `hmac-sha256-v1=<base64>` over `canonical`. */
export function computeSignature(secret: Buffer, canonical: Buffer): string {
  const mac = createHmac('sha256', secret).update(canonical).digest('base64');
  return `${ALGORITHM_PREFIX}${mac}`;
}

function parseTimestampToEpochSeconds(timestamp: string): number {
  // RFC 3339 / ISO 8601. Date.parse handles both `2026-05-20T12:34:56Z`
  // and `2026-05-20T12:34:56+00:00`. NaN on invalid.
  const ms = Date.parse(timestamp);
  if (Number.isNaN(ms)) {
    throw new SignatureExpiredError(`invalid timestamp: ${timestamp}`);
  }
  return Math.floor(ms / 1000);
}

export interface VerifySignatureParams {
  secret: Buffer;
  keyId: string;
  timestamp: string;
  rawBody: Buffer;
  signatureHeader: string;
  method: string;
  callbackPath: string;
  institutionId: string;
  /** Override "now" (epoch seconds) for reproducible tests. */
  nowEpochSeconds?: number;
}

/**
 * Verify an inbound SBS webhook callback signature.
 *
 * Throws `SignatureExpiredError` if the timestamp is outside the
 * ±5-minute skew window; `KeyIdUnknownError` if the key id is not
 * recognised; `SignatureInvalidError` if the HMAC does not match.
 * Returns nothing on success.
 */
export function verifyWebhookSignature(params: VerifySignatureParams): void {
  const {
    secret,
    keyId,
    timestamp,
    rawBody,
    signatureHeader,
    method,
    callbackPath,
    institutionId,
    nowEpochSeconds,
  } = params;

  if (keyId !== KEY_ID_SANDBOX_V1) {
    throw new KeyIdUnknownError(
      `unknown X-SBS-Key-Id ${JSON.stringify(keyId)}; this helper expects ${JSON.stringify(KEY_ID_SANDBOX_V1)}`,
    );
  }

  const tsEpoch = parseTimestampToEpochSeconds(timestamp);
  const current = nowEpochSeconds ?? Math.floor(Date.now() / 1000);
  const delta = Math.abs(current - tsEpoch);
  if (delta > MAX_CLOCK_SKEW_SECONDS) {
    throw new SignatureExpiredError(
      `timestamp ${timestamp} is ${delta}s from current time; max skew is ${MAX_CLOCK_SKEW_SECONDS}s`,
    );
  }

  if (!signatureHeader.startsWith(ALGORITHM_PREFIX)) {
    throw new SignatureInvalidError(
      `signature header must start with ${JSON.stringify(ALGORITHM_PREFIX)}`,
    );
  }

  const canonical = canonicalizeRequest({
    method,
    callbackPath,
    timestamp,
    rawBody,
    institutionId,
  });
  const expected = computeSignature(secret, canonical);

  if (!constantTimeCompare(expected, signatureHeader)) {
    throw new SignatureInvalidError('signature mismatch');
  }
}
