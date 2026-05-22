// Bridge to the FastAPI internal audit endpoint. The Next.js server
// calls FastAPI; the same single-entrypoint rule applies as in
// api/sbs_api/audit.py — the audit table has one writer, regardless of
// which side of the supervisor app a state change originates from.

import 'server-only';

import { authConfig } from './config';

export interface AuditWriteRequest {
  actor_type: 'user' | 'agent';
  actor_id: string;
  action: string;            // kebab-case
  object_type: string;
  object_id: string;
  diff?: Record<string, unknown> | null;
  meta?: Record<string, unknown> | null;
}

/**
 * Write one audit row via FastAPI's POST /v1/internal/audit endpoint.
 * Caller awaits the write so its own transaction does not return
 * before the audit row is durable. Throws on non-2xx so the caller
 * can decide whether to fail the parent operation.
 */
export async function writeAuditEvent(event: AuditWriteRequest): Promise<void> {
  const response = await fetch(
    `${authConfig.internalApiBaseUrl}/v1/internal/audit`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        // Shared secret between the Next.js server and FastAPI. Production
        // overlay uses a Kubernetes secret; sandbox uses an env var. The
        // header name matches FastAPI's check in api/sbs_api/routes/internal.py.
        Authorization: `Bearer ${authConfig.internalApiSecret()}`,
      },
      body: JSON.stringify(event),
      cache: 'no-store',
    },
  );
  if (!response.ok) {
    const text = await response.text();
    throw new Error(
      `Audit endpoint returned ${response.status}: ${text}`,
    );
  }
}
