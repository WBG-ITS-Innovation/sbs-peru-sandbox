/* eslint-disable i18next/no-literal-string */
'use client';

import { KeyRound, Layers, Send, Terminal } from 'lucide-react';
import Link from 'next/link';

import { Badge, Card, CardBody, CardHeader, CardTitle } from '@/components/ui';
import type { Locale } from '@/i18n';
import { bi } from '@/lib/bi';

// Live API reference for the portal: the two-tier model, the REAL endpoints,
// the REAL signed-request pattern, and a working link to the sandbox control
// surface. Documentation + a real link — no fake controls.

const ENDPOINTS = [
  { method: 'POST', path: '/v1/oauth/token', auth: 'Basic (client_credentials)', es: 'Obtener token OAuth', en: 'Obtain OAuth token' },
  { method: 'POST', path: '/v1/sandbox/complaints/granular', auth: 'OAuth + HMAC + mTLS', es: 'Tier 1 — reclamo granular (NRT)', en: 'Tier 1 — granular complaint (NRT)' },
  { method: 'POST', path: '/v1/batches', auth: 'OAuth batch:upload + HMAC (multipart) + mTLS', es: 'Tier 2 — subir lote CSV', en: 'Tier 2 — upload CSV batch' },
  { method: 'GET', path: '/v1/batches/{id}', auth: 'OAuth batch:upload', es: 'Tier 2 — estado del lote', en: 'Tier 2 — batch status' },
];

const AUTH_EXAMPLE = `# 1) OAuth client_credentials token
curl -u "$CLIENT_ID:$CLIENT_SECRET" \\
  -d grant_type=client_credentials -d scope="complaints:write" \\
  "$API/v1/oauth/token"

# 2) HMAC canonical request (newline-joined), then HMAC-SHA256 with the
#    institution's shared secret:
#    METHOD\\nTARGET\\nHOST\\nTIMESTAMP\\nSHA256(body)\\nINSTITUTION_ID

# 3) Signed POST (Tier 1 granular)
curl -X POST "$API/v1/sandbox/complaints/granular" \\
  -H "Authorization: Bearer $TOKEN" \\
  -H "Idempotency-Key: $(uuidgen)" \\
  -H "X-SBS-Timestamp: $TS" \\
  -H "X-SBS-Signature: hmac-sha256-v1=$SIG" \\
  -H "X-SBS-Institution-Id: SBS-001234" \\
  -H "Content-Type: application/json" \\
  --data @complaint.json`;

export function LiveApiPanel({ locale }: { locale: Locale }) {
  return (
    <section className="space-y-4">
      {/* Two-tier model */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Layers className="h-4 w-4 text-brand-cyan" aria-hidden="true" />
            {bi(locale, 'Modelo de dos niveles', 'Two-tier model')}
          </CardTitle>
        </CardHeader>
        <CardBody className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-sbs border border-border bg-surface-subtle/40 p-3">
            <p className="text-sm font-semibold text-brand-navy">{bi(locale, 'Tier 1 — granular (NRT)', 'Tier 1 — granular (NRT)')}</p>
            <p className="mt-1 text-xs text-fg-muted">
              {bi(
                locale,
                'Reclamo a reclamo, casi en tiempo real, por POST firmado a /v1/sandbox/complaints/granular. Para bancos con integración directa. El SBS redacta PII, valida Anexo 1-A, corre los agentes y publica en el feed en vivo.',
                'One complaint at a time, near-real-time, via a signed POST to /v1/sandbox/complaints/granular. For directly-integrated banks. SBS redacts PII, validates Anexo 1-A, runs the agents and publishes to the live feed.',
              )}
            </p>
          </div>
          <div className="rounded-sbs border border-border bg-surface-subtle/40 p-3">
            <p className="text-sm font-semibold text-brand-navy">{bi(locale, 'Tier 2 — lote (batch)', 'Tier 2 — batch')}</p>
            <p className="mt-1 text-xs text-fg-muted">
              {bi(
                locale,
                'Carga periódica de un CSV Anexo 1-A + manifiesto por POST /v1/batches (multipart). Para cooperativas y entidades con envío diferido. El worker procesa el lote (pending → processing → complete) y cuenta filas aceptadas/rechazadas.',
                'Periodic upload of an Anexo 1-A CSV + manifest via POST /v1/batches (multipart). For cooperatives and deferred reporters. The worker processes the batch (pending → processing → complete) and counts accepted/rejected rows.',
              )}
            </p>
          </div>
        </CardBody>
      </Card>

      {/* Live endpoints */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-base">
            <Send className="h-4 w-4 text-brand-cyan" aria-hidden="true" />
            {bi(locale, 'Endpoints en vivo', 'Live endpoints')}
          </CardTitle>
          <Badge variant="source" className="font-mono">{bi(locale, 'sandbox real', 'real sandbox')}</Badge>
        </CardHeader>
        <CardBody>
          <table className="w-full text-xs">
            <thead className="bg-surface-subtle text-fg-muted">
              <tr>
                <th className="px-2 py-1.5 text-left">{bi(locale, 'Método', 'Method')}</th>
                <th className="px-2 py-1.5 text-left">Path</th>
                <th className="px-2 py-1.5 text-left">{bi(locale, 'Autenticación', 'Auth')}</th>
                <th className="px-2 py-1.5 text-left">{bi(locale, 'Descripción', 'Description')}</th>
              </tr>
            </thead>
            <tbody>
              {ENDPOINTS.map((e) => (
                <tr key={e.path} className="border-t border-border-subtle">
                  <td className="px-2 py-1.5 font-mono font-semibold text-brand-navy">{e.method}</td>
                  <td className="px-2 py-1.5 font-mono">{e.path}</td>
                  <td className="px-2 py-1.5 text-2xs text-fg-muted">{e.auth}</td>
                  <td className="px-2 py-1.5">{bi(locale, e.es, e.en)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardBody>
      </Card>

      {/* Real auth pattern */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <KeyRound className="h-4 w-4 text-brand-cyan" aria-hidden="true" />
            {bi(locale, 'Patrón de autenticación real', 'Real auth pattern')}
          </CardTitle>
        </CardHeader>
        <CardBody>
          <pre className="overflow-auto rounded-sbs border border-border bg-brand-navy/95 p-3 font-mono text-2xs leading-relaxed text-white">
{AUTH_EXAMPLE}
          </pre>
          <p className="mt-2 text-2xs text-fg-muted">
            {bi(
              locale,
              'Es el mismo patrón firmado que usan los CLIs y el simulador. La referencia interactiva completa (Stoplight Elements sobre la OpenAPI real) se sirve con bash scripts/serve-devportal.sh.',
              'This is the same signed pattern the CLIs and the simulator use. The full interactive reference (Stoplight Elements over the real OpenAPI) is served by bash scripts/serve-devportal.sh.',
            )}
          </p>
        </CardBody>
      </Card>

      {/* Real link to the working control surface */}
      <Card>
        <CardBody className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Terminal className="h-4 w-4 text-brand-cyan" aria-hidden="true" />
            <p className="text-sm text-fg">
              {bi(locale, 'Prueba estos endpoints en vivo desde el simulador de instituciones.', 'Try these endpoints live from the institution simulator.')}
            </p>
          </div>
          <Link href="/sandbox" className="inline-flex items-center gap-1.5 rounded-sbs border border-brand-navy bg-brand-navy px-3 py-1.5 text-xs font-medium text-fg-inverted hover:bg-brand-navy/90">
            <Send className="h-3.5 w-3.5" aria-hidden="true" />
            {bi(locale, 'Abrir el simulador', 'Open the simulator')}
          </Link>
        </CardBody>
      </Card>
    </section>
  );
}
