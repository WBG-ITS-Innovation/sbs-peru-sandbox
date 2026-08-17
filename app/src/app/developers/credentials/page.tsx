// SPDX-License-Identifier: Apache-2.0
import { History, Info, Plus } from 'lucide-react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { t } from '@/i18n';
import { currentLocale } from '@/i18n/server';

// /app/developers/credentials — preview screen for institution
// credentials. Mock-only by design at this stage: the table data is
// illustrative, every action button is disabled, and the disclaimer
// banner names the page as a preview surface. There is no backend call
// from this page.

export const dynamic = 'force-dynamic';

interface Row {
  institution: string;
  ruc: string;
  cadence: string;
  cert: string;
  clientId: string;
  scopes: string[];
  status: 'active' | 'pending';
}

export default async function CredentialsPage() {
  const locale = await currentLocale();
  const tr = (key: string) => t(locale, key);

  const previewDisclaimer = tr('pilot.preview_disclaimer');
  const previewOnly = tr('developers.credentials.preview_only');
  const pilotBadge = tr('pilot.badge');

  const rows: Row[] = [
    {
      institution: 'BANCO_DEMO_001',
      ruc: 'RUC 20100000001 · Tier 1',
      cadence: 'API NRT',
      cert: 'SHA-1 9F:23:A1:…:4B',
      clientId: 'cli_b001_pil_8f4e2',
      scopes: ['complaints:write', 'complaints:read', 'status:read'],
      status: 'active',
    },
    {
      institution: 'COOPAC_DEMO_002',
      ruc: 'RUC 20200000002 · Tier 2',
      cadence: 'MENSUAL',
      cert: 'SHA-1 2E:18:D6:…:71',
      clientId: 'cli_c002_pil_3a7c9',
      scopes: ['batch:upload', 'status:read'],
      status: 'active',
    },
    {
      institution: 'FINANCIERA_DEMO_003',
      ruc: 'RUC 20300000003 · Tier 2',
      cadence: 'SEMANAL',
      cert: '— (CSR recibido · pendiente firma)',
      clientId: '—',
      scopes: ['batch:upload', 'status:read'],
      status: 'pending',
    },
  ];

  const tbl = (k: string) => tr(`developers.credentials.table.${k}`);

  return (
    <main className="mx-auto max-w-7xl space-y-4 px-4 py-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-3xl">
          <h2 className="font-serif text-2xl font-semibold tracking-tight text-fg">
            {tr('developers.credentials.title')}
          </h2>
          <p className="mt-1 text-sm text-fg-muted">
            {tr('developers.credentials.subtitle')}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" disabled aria-disabled="true">
            <History className="h-3.5 w-3.5" aria-hidden="true" />
            {tr('developers.credentials.history_button')}
          </Button>
          <Button variant="default" size="sm" disabled aria-disabled="true">
            <Plus className="h-3.5 w-3.5" aria-hidden="true" />
            {tr('developers.credentials.request_button')}
          </Button>
          <Badge variant="role" className="border-brand-gold/40 bg-brand-gold/10 text-brand-navy">
            {pilotBadge}
          </Badge>
        </div>
      </header>

      <div
        role="status"
        className="flex items-center gap-2 rounded-sbs border border-border bg-surface-subtle px-3 py-2 text-xs text-fg-muted"
      >
        <Info className="h-3.5 w-3.5 text-brand-gold" aria-hidden="true" />
        <span>{previewDisclaimer}</span>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">
            {tr('developers.credentials.title')}
          </CardTitle>
        </CardHeader>
        <CardBody className="p-0">
          <div className="overflow-x-auto">
            <table className="min-w-full border-collapse text-xs">
              <thead className="bg-surface-subtle text-fg-muted">
                <tr>
                  <th scope="col" className="px-3 py-2 text-left font-mono uppercase tracking-wider">
                    {tbl('institution')}
                  </th>
                  <th scope="col" className="px-3 py-2 text-left font-mono uppercase tracking-wider">
                    {tbl('cadence')}
                  </th>
                  <th scope="col" className="px-3 py-2 text-left font-mono uppercase tracking-wider">
                    {tbl('cert')}
                  </th>
                  <th scope="col" className="px-3 py-2 text-left font-mono uppercase tracking-wider">
                    {tbl('client_id')}
                  </th>
                  <th scope="col" className="px-3 py-2 text-left font-mono uppercase tracking-wider">
                    {tbl('scopes')}
                  </th>
                  <th scope="col" className="px-3 py-2 text-left font-mono uppercase tracking-wider">
                    {tbl('status')}
                  </th>
                  <th scope="col" className="px-3 py-2 text-right font-mono uppercase tracking-wider">
                    {tbl('actions')}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {rows.map(r => (
                  <tr key={r.institution} className="align-top">
                    <td className="px-3 py-2">
                      <div className="font-medium text-fg">{r.institution}</div>
                      <div className="font-mono text-2xs text-fg-muted">{r.ruc}</div>
                    </td>
                    <td className="px-3 py-2">
                      <Badge variant="source">{r.cadence}</Badge>
                    </td>
                    <td className="px-3 py-2 font-mono tabular text-fg">{r.cert}</td>
                    <td className="px-3 py-2 font-mono tabular text-fg">{r.clientId}</td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-1">
                        {r.scopes.map(s => (
                          <span
                            key={s}
                            className="rounded-sbs border border-border bg-surface-subtle px-1.5 py-0.5 font-mono text-2xs text-fg"
                          >
                            {s}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      {r.status === 'active' ? (
                        <Badge variant="resolved">{tbl('status_active')}</Badge>
                      ) : (
                        <Badge variant="medium">{tbl('status_pending')}</Badge>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" size="sm" disabled aria-disabled="true">
                          {tbl('rotate')}
                        </Button>
                        <Button variant="ghost" size="sm" disabled aria-disabled="true">
                          {tbl('edit')}
                        </Button>
                        <Button variant="ghost" size="sm" disabled aria-disabled="true">
                          {tbl('revoke')}
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="border-t border-border bg-surface-subtle px-3 py-2 text-2xs text-fg-muted">
            {previewOnly}
          </p>
        </CardBody>
      </Card>
    </main>
  );
}
