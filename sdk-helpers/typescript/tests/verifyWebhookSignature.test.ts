// SPDX-License-Identifier: Apache-2.0
/**
 * Tests for the TypeScript webhook verification helper.
 *
 * Same matrix as the Python helper: round-trip success, tampered
 * body, tampered signature, wrong method, wrong institution_id,
 * expired and future timestamps, wrong key id, missing prefix,
 * `nowEpochSeconds` override for reproducibility, and constant-time
 * compare on equal/unequal inputs.
 *
 * Additional TypeScript-only tests live in
 * `import-paths.test.ts` and `cjs-import-paths.test.cjs`
 * exercising the dual ESM + CJS exports.
 */

import { createHmac } from 'node:crypto';

import {
  ALGORITHM_PREFIX,
  KEY_ID_SANDBOX_V1,
  KeyIdUnknownError,
  MAX_CLOCK_SKEW_SECONDS,
  SignatureExpiredError,
  SignatureInvalidError,
  canonicalizeRequest,
  computeSignature,
  constantTimeCompare,
  verifyWebhookSignature,
} from '../src/index';

const SECRET = Buffer.from('sandbox-shared-secret-known-only-to-coopac-and-sbs');
const INSTITUTION_ID = 'SBS-001234';
const METHOD = 'POST';
const CALLBACK_PATH = '/sbs-callback';

function nowIso(): string {
  return new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');
}

function sign(opts: {
  timestamp: string;
  body: Buffer;
  secret?: Buffer;
  method?: string;
  callbackPath?: string;
  institutionId?: string;
}): string {
  const canonical = canonicalizeRequest({
    method: opts.method ?? METHOD,
    callbackPath: opts.callbackPath ?? CALLBACK_PATH,
    timestamp: opts.timestamp,
    rawBody: opts.body,
    institutionId: opts.institutionId ?? INSTITUTION_ID,
  });
  return computeSignature(opts.secret ?? SECRET, canonical);
}

// ---- Canonical-request construction ---------------------------------------

describe('canonicalizeRequest', () => {
  test('produces five LF-joined lines, method uppercased', () => {
    const canonical = canonicalizeRequest({
      method: 'post',
      callbackPath: '/cb',
      timestamp: '2026-05-20T12:00:00Z',
      rawBody: Buffer.from('{"ok":true}'),
      institutionId: 'SBS-001234',
    });
    const lines = canonical.toString('utf8').split('\n');
    expect(lines).toHaveLength(5);
    expect(lines[0]).toBe('POST');
    expect(lines[1]).toBe('/cb');
    expect(lines[2]).toBe('2026-05-20T12:00:00Z');
    expect(lines[3]).toMatch(/^[0-9a-f]{64}$/); // hex SHA-256
    expect(lines[4]).toBe('SBS-001234');
  });

  test('empty body uses cached SHA-256(b\'\') hex', () => {
    const canonical = canonicalizeRequest({
      method: 'POST',
      callbackPath: '/cb',
      timestamp: '2026-05-20T12:00:00Z',
      rawBody: Buffer.alloc(0),
      institutionId: 'SBS-001234',
    });
    const lines = canonical.toString('utf8').split('\n');
    // SHA-256 of an empty bytes object.
    expect(lines[3]).toBe(
      'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', // pragma: allowlist secret
    );
  });
});

describe('computeSignature', () => {
  test('starts with the algorithm prefix and contains base64 mac', () => {
    const sig = computeSignature(SECRET, Buffer.from('canonical'));
    expect(sig.startsWith(ALGORITHM_PREFIX)).toBe(true);
    const b64 = sig.slice(ALGORITHM_PREFIX.length);
    const expectedMac = createHmac('sha256', SECRET)
      .update(Buffer.from('canonical'))
      .digest('base64');
    expect(b64).toBe(expectedMac);
  });
});

// ---- verifyWebhookSignature ------------------------------------------------

describe('verifyWebhookSignature', () => {
  test('round-trip returns void on success', () => {
    const ts = nowIso();
    const body = Buffer.from('{"event":"batch_completed"}');
    const sig = sign({ timestamp: ts, body });
    expect(() =>
      verifyWebhookSignature({
        secret: SECRET,
        keyId: KEY_ID_SANDBOX_V1,
        timestamp: ts,
        rawBody: body,
        signatureHeader: sig,
        method: METHOD,
        callbackPath: CALLBACK_PATH,
        institutionId: INSTITUTION_ID,
      }),
    ).not.toThrow();
  });

  test('tampered body raises SignatureInvalidError', () => {
    const ts = nowIso();
    const body = Buffer.from('{"ok":true}');
    const sig = sign({ timestamp: ts, body });
    expect(() =>
      verifyWebhookSignature({
        secret: SECRET,
        keyId: KEY_ID_SANDBOX_V1,
        timestamp: ts,
        rawBody: Buffer.from('{"ok":TRUE}'),
        signatureHeader: sig,
        method: METHOD,
        callbackPath: CALLBACK_PATH,
        institutionId: INSTITUTION_ID,
      }),
    ).toThrow(SignatureInvalidError);
  });

  test('tampered signature raises SignatureInvalidError', () => {
    const ts = nowIso();
    const body = Buffer.from('{"ok":true}');
    const sig = sign({ timestamp: ts, body });
    const bad = sig.slice(0, -1) + (sig.endsWith('A') ? 'B' : 'A');
    expect(() =>
      verifyWebhookSignature({
        secret: SECRET,
        keyId: KEY_ID_SANDBOX_V1,
        timestamp: ts,
        rawBody: body,
        signatureHeader: bad,
        method: METHOD,
        callbackPath: CALLBACK_PATH,
        institutionId: INSTITUTION_ID,
      }),
    ).toThrow(SignatureInvalidError);
  });

  test('wrong method raises SignatureInvalidError', () => {
    const ts = nowIso();
    const body = Buffer.from('{}');
    const sig = sign({ timestamp: ts, body, method: 'POST' });
    expect(() =>
      verifyWebhookSignature({
        secret: SECRET,
        keyId: KEY_ID_SANDBOX_V1,
        timestamp: ts,
        rawBody: body,
        signatureHeader: sig,
        method: 'PUT',
        callbackPath: CALLBACK_PATH,
        institutionId: INSTITUTION_ID,
      }),
    ).toThrow(SignatureInvalidError);
  });

  test('wrong institution_id raises SignatureInvalidError', () => {
    const ts = nowIso();
    const body = Buffer.from('{}');
    const sig = sign({ timestamp: ts, body });
    expect(() =>
      verifyWebhookSignature({
        secret: SECRET,
        keyId: KEY_ID_SANDBOX_V1,
        timestamp: ts,
        rawBody: body,
        signatureHeader: sig,
        method: METHOD,
        callbackPath: CALLBACK_PATH,
        institutionId: 'SBS-999999',
      }),
    ).toThrow(SignatureInvalidError);
  });

  test('expired (old) timestamp raises SignatureExpiredError', () => {
    const oldTs = new Date(Date.now() - (MAX_CLOCK_SKEW_SECONDS + 30) * 1000)
      .toISOString()
      .replace(/\.\d{3}Z$/, 'Z');
    const body = Buffer.from('{}');
    const sig = sign({ timestamp: oldTs, body });
    expect(() =>
      verifyWebhookSignature({
        secret: SECRET,
        keyId: KEY_ID_SANDBOX_V1,
        timestamp: oldTs,
        rawBody: body,
        signatureHeader: sig,
        method: METHOD,
        callbackPath: CALLBACK_PATH,
        institutionId: INSTITUTION_ID,
      }),
    ).toThrow(SignatureExpiredError);
  });

  test('future timestamp raises SignatureExpiredError', () => {
    const futureTs = new Date(Date.now() + (MAX_CLOCK_SKEW_SECONDS + 30) * 1000)
      .toISOString()
      .replace(/\.\d{3}Z$/, 'Z');
    const body = Buffer.from('{}');
    const sig = sign({ timestamp: futureTs, body });
    expect(() =>
      verifyWebhookSignature({
        secret: SECRET,
        keyId: KEY_ID_SANDBOX_V1,
        timestamp: futureTs,
        rawBody: body,
        signatureHeader: sig,
        method: METHOD,
        callbackPath: CALLBACK_PATH,
        institutionId: INSTITUTION_ID,
      }),
    ).toThrow(SignatureExpiredError);
  });

  test('malformed timestamp raises SignatureExpiredError', () => {
    const body = Buffer.from('{}');
    expect(() =>
      verifyWebhookSignature({
        secret: SECRET,
        keyId: KEY_ID_SANDBOX_V1,
        timestamp: 'not-a-timestamp',
        rawBody: body,
        signatureHeader: `${ALGORITHM_PREFIX}any`,
        method: METHOD,
        callbackPath: CALLBACK_PATH,
        institutionId: INSTITUTION_ID,
      }),
    ).toThrow(SignatureExpiredError);
  });

  test('wrong key id raises KeyIdUnknownError', () => {
    const ts = nowIso();
    const body = Buffer.from('{}');
    const sig = sign({ timestamp: ts, body });
    expect(() =>
      verifyWebhookSignature({
        secret: SECRET,
        keyId: 'sandbox-v9000',
        timestamp: ts,
        rawBody: body,
        signatureHeader: sig,
        method: METHOD,
        callbackPath: CALLBACK_PATH,
        institutionId: INSTITUTION_ID,
      }),
    ).toThrow(KeyIdUnknownError);
  });

  test('signature header missing prefix raises SignatureInvalidError', () => {
    const ts = nowIso();
    const body = Buffer.from('{}');
    expect(() =>
      verifyWebhookSignature({
        secret: SECRET,
        keyId: KEY_ID_SANDBOX_V1,
        timestamp: ts,
        rawBody: body,
        signatureHeader: 'bare-base64-no-prefix',
        method: METHOD,
        callbackPath: CALLBACK_PATH,
        institutionId: INSTITUTION_ID,
      }),
    ).toThrow(SignatureInvalidError);
  });

  test('nowEpochSeconds override pins the clock for reproducibility', () => {
    const ts = '2026-05-20T12:00:00Z';
    const body = Buffer.from('{}');
    const sig = sign({ timestamp: ts, body });
    // Pin "now" to one minute after the timestamp — within the window.
    expect(() =>
      verifyWebhookSignature({
        secret: SECRET,
        keyId: KEY_ID_SANDBOX_V1,
        timestamp: ts,
        rawBody: body,
        signatureHeader: sig,
        method: METHOD,
        callbackPath: CALLBACK_PATH,
        institutionId: INSTITUTION_ID,
        nowEpochSeconds: Math.floor(Date.parse(ts) / 1000) + 60,
      }),
    ).not.toThrow();
  });
});

// ---- Constant-time compare -------------------------------------------------

describe('constantTimeCompare', () => {
  test('equal strings', () => {
    expect(constantTimeCompare('abc', 'abc')).toBe(true);
  });
  test('equal buffers', () => {
    expect(constantTimeCompare(Buffer.from('abc'), Buffer.from('abc'))).toBe(true);
  });
  test('unequal same-length', () => {
    expect(constantTimeCompare('abc', 'abd')).toBe(false);
  });
  test('unequal different-length', () => {
    expect(constantTimeCompare('abc', 'abcd')).toBe(false);
  });
});

describe('dependency surface', () => {
  test('package.json declares no runtime dependencies', () => {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const pkg = require('../package.json');
    expect(pkg.dependencies).toEqual({});
  });
});
