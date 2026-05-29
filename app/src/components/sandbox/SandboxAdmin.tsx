/* eslint-disable i18next/no-literal-string */
'use client';

import { ExternalLink, History, Inbox, RefreshCw, Send, Server } from 'lucide-react';
import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';

import { Badge, Card, CardBody, CardHeader, CardTitle } from '@/components/ui';
import type { Locale } from '@/i18n';
import { bi } from '@/lib/bi';
import { cn } from '@/lib/cn';

// IT / sandbox-admin view. Surfaces REAL controllable surfaces and REAL data
// only: a link to the live ingestion controls (the /sandbox panels), the real
// recent submissions feed, the real audit log, and the seeded institutions'
// real Tier-1 credential state. No control here is fake — read-only views plus
// a link to the working control surface. Institution enable/disable is omitted
// because there is no real toggle wired to it.

interface FeedItem {
  complaint_id: string;
  institution_name?: string;
  severity?: string;
  classification?: string;
  received_at?: string;
}
interface AuditRow {
  id: number;
  created_at: string;
  actor_type: string;
  actor_id: string;
  action: string;
  object_type: string;
  object_id: string;
}

// Real seeded sandbox institutions (mirrors scripts/dev-seed.sql + the Tier-1
// sender profiles). Read-only — this reflects the actual credential state.
const INSTITUTIONS = [
  { id: 'SBS-001234', name: 'Banco Demo 001', tier1: true, note: 'banco-tier1' },
  { id: 'SBS-005678', name: 'Coopac Demo 002', tier1: true, note: 'coopac-tier2' },
  { id: 'SBS-009012', name: 'Financiera Demo 003', tier1: false, note: 'sin credenciales Tier-1 / no Tier-1 credentials' },
];

export function SandboxAdmin({ locale }: { locale: Locale }) {
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [audit, setAudit] = useState<AuditRow[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [f, a] = await Promise.all([
        fetch('/app/api/aggregates/feed', { cache: 'no-store' }).then((r) => r.json()).catch(() => ({})),
        fetch('/app/api/admin/audit?page_size=20', { cache: 'no-store' }).then((r) => r.json()).catch(() => ({})),
      ]);
      const items = ((f.items ?? []) as FeedItem[]).filter((i) => i.received_at);
      items.sort((x, y) => (y.received_at ?? '').localeCompare(x.received_at ?? ''));
      setFeed(items.slice(0, 20));
      setAudit((a.items ?? []) as AuditRow[]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, [load]);

  return (
    <div className="space-y-4">
      {/* Real control surface — ingestion rate lives in the working /sandbox panels. */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-base">
            <Server className="h-4 w-4 text-brand-cyan" aria-hidden="true" />
            {bi(locale, 'Parámetros controlables (reales)', 'Controllable parameters (real)')}
          </CardTitle>
          <button type="button" onClick={load} disabled={loading} className="inline-flex items-center gap-1 rounded-sbs border border-border bg-surface px-2 py-1 text-2xs hover:bg-surface-subtle disabled:opacity-50">
            <RefreshCw className={cn('h-3 w-3', loading && 'animate-spin')} aria-hidden="true" />
            {bi(locale, 'Actualizar', 'Refresh')}
          </button>
        </CardHeader>
        <CardBody className="space-y-2">
          <p className="text-xs text-fg-muted">
            {bi(
              locale,
              'La frecuencia de ingestión, el envío puntual y la ráfaga (Tier 1) y el envío de lotes (Tier 2) son controles reales que llaman al API. Se operan en el panel del simulador.',
              'Ingestion frequency, single send and burst (Tier 1) and batch upload (Tier 2) are real controls that call the API. They are operated in the simulator panel.',
            )}
          </p>
          <Link href="/sandbox" className="inline-flex items-center gap-1.5 rounded-sbs border border-brand-navy bg-brand-navy px-3 py-1.5 text-xs font-medium text-fg-inverted hover:bg-brand-navy/90">
            <Send className="h-3.5 w-3.5" aria-hidden="true" />
            {bi(locale, 'Abrir controles de ingestión (Tier 1 / Tier 2)', 'Open ingestion controls (Tier 1 / Tier 2)')}
          </Link>
        </CardBody>
      </Card>

      {/* Institutions — read-only real credential state. */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{bi(locale, 'Instituciones del sandbox', 'Sandbox institutions')}</CardTitle>
        </CardHeader>
        <CardBody>
          <table className="w-full text-xs">
            <thead className="bg-surface-subtle text-fg-muted">
              <tr>
                <th className="px-2 py-1.5 text-left font-mono uppercase tracking-wide">institution_id</th>
                <th className="px-2 py-1.5 text-left">{bi(locale, 'Nombre', 'Name')}</th>
                <th className="px-2 py-1.5 text-left">Tier 1</th>
                <th className="px-2 py-1.5 text-left">{bi(locale, 'Perfil / nota', 'Profile / note')}</th>
              </tr>
            </thead>
            <tbody>
              {INSTITUTIONS.map((i) => (
                <tr key={i.id} className="border-t border-border-subtle">
                  <td className="px-2 py-1.5 font-mono">{i.id}</td>
                  <td className="px-2 py-1.5">{i.name}</td>
                  <td className="px-2 py-1.5">
                    <Badge variant={i.tier1 ? 'source' : 'default'}>{i.tier1 ? bi(locale, 'habilitado', 'enabled') : bi(locale, 'no', 'no')}</Badge>
                  </td>
                  <td className="px-2 py-1.5 font-mono text-2xs text-fg-muted">{i.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-2xs italic text-fg-subtle">
            {bi(
              locale,
              'Estado real de credenciales (dev-seed). Solo lectura: no se expone un interruptor de habilitar/deshabilitar porque no hay un mecanismo real conectado.',
              'Real credential state (dev-seed). Read-only: no enable/disable switch is exposed because there is no real mechanism wired to it.',
            )}
          </p>
        </CardBody>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Recent submissions — real feed. */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Inbox className="h-4 w-4 text-brand-navy" aria-hidden="true" />
              {bi(locale, 'Envíos recientes (real)', 'Recent submissions (real)')}
            </CardTitle>
          </CardHeader>
          <CardBody>
            <div className="max-h-80 overflow-auto">
              <table className="w-full text-2xs">
                <thead className="sticky top-0 bg-surface-subtle text-fg-muted">
                  <tr>
                    <th className="px-2 py-1 text-left">complaint_id</th>
                    <th className="px-2 py-1 text-left">{bi(locale, 'Institución', 'Institution')}</th>
                    <th className="px-2 py-1 text-left">{bi(locale, 'Sev.', 'Sev.')}</th>
                    <th className="px-2 py-1 text-left">{bi(locale, 'Recibido', 'Received')}</th>
                  </tr>
                </thead>
                <tbody>
                  {feed.map((i) => (
                    <tr key={i.complaint_id} className="border-t border-border-subtle">
                      <td className="px-2 py-1 font-mono">
                        <Link href={`/processing/${i.complaint_id}`} className="inline-flex items-center gap-1 text-fg-link hover:underline">
                          {i.complaint_id}<ExternalLink className="h-3 w-3" aria-hidden="true" />
                        </Link>
                      </td>
                      <td className="px-2 py-1">{i.institution_name ?? '—'}</td>
                      <td className="px-2 py-1 font-mono">{i.severity ?? '—'}</td>
                      <td className="px-2 py-1 font-mono text-fg-muted">{(i.received_at ?? '').slice(0, 19).replace('T', ' ')}</td>
                    </tr>
                  ))}
                  {feed.length === 0 ? <tr><td colSpan={4} className="px-2 py-3 text-center text-fg-muted">{loading ? bi(locale, 'Cargando…', 'Loading…') : bi(locale, 'Sin envíos.', 'No submissions.')}</td></tr> : null}
                </tbody>
              </table>
            </div>
          </CardBody>
        </Card>

        {/* Audit log — real. */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2 text-base">
              <History className="h-4 w-4 text-brand-navy" aria-hidden="true" />
              {bi(locale, 'Bitácora de auditoría (real)', 'Audit log (real)')}
            </CardTitle>
            <Link href="/audit" className="text-2xs text-fg-link hover:underline">{bi(locale, 'Ver todo', 'View all')}</Link>
          </CardHeader>
          <CardBody>
            <div className="max-h-80 overflow-auto">
              <table className="w-full text-2xs">
                <thead className="sticky top-0 bg-surface-subtle text-fg-muted">
                  <tr>
                    <th className="px-2 py-1 text-left">{bi(locale, 'Hora', 'Time')}</th>
                    <th className="px-2 py-1 text-left">{bi(locale, 'Actor', 'Actor')}</th>
                    <th className="px-2 py-1 text-left">{bi(locale, 'Acción', 'Action')}</th>
                    <th className="px-2 py-1 text-left">{bi(locale, 'Objeto', 'Object')}</th>
                  </tr>
                </thead>
                <tbody>
                  {audit.map((r) => (
                    <tr key={r.id} className="border-t border-border-subtle">
                      <td className="px-2 py-1 font-mono text-fg-muted">{r.created_at.slice(11, 19)}</td>
                      <td className="px-2 py-1 font-mono">{r.actor_id}</td>
                      <td className="px-2 py-1">{r.action}</td>
                      <td className="px-2 py-1 font-mono text-fg-muted">{r.object_type}:{(r.object_id ?? '').slice(0, 14)}</td>
                    </tr>
                  ))}
                  {audit.length === 0 ? <tr><td colSpan={4} className="px-2 py-3 text-center text-fg-muted">{loading ? bi(locale, 'Cargando…', 'Loading…') : bi(locale, 'Sin eventos.', 'No events.')}</td></tr> : null}
                </tbody>
              </table>
            </div>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
