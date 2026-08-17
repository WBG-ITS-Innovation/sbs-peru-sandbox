// SPDX-License-Identifier: Apache-2.0
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { BarChart3, Download, FileSpreadsheet, Sparkles } from 'lucide-react';

import { SESSION_COOKIE } from '@/auth/cookies';
import { getSession } from '@/auth/session';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { PageHeader } from '@/components/shell/PageHeader';
import { t } from '@/i18n';
import { currentLocale } from '@/i18n/server';

// /app/analytics — supervisor pilot preview. Statistical reports as the
// transition target away from SUCAVE. This page is intentionally a
// preview: all controls show a "Vista previa · no conectado al flujo
// operativo actual" disclaimer and the buttons are disabled. No backend
// calls are made from this page; every value is illustrative.

export const dynamic = 'force-dynamic';

const CHANNELS = ['API NRT', 'INDECOPI', 'Internal', 'Plavia', 'Social'] as const;
const MATRIX_ROWS: { code: string; key: string; vals: number[]; pct: string }[] = [
  { code: '304', key: 'motivo_304', vals: [42, 8, 6, 2, 11], pct: '94%' },
  { code: '211', key: 'motivo_211', vals: [18, 4, 11, 1, 3], pct: '88%' },
  { code: '502', key: 'motivo_502', vals: [12, 6, 3, 0, 1], pct: '91%' },
  { code: '118', key: 'motivo_118', vals: [3, 1, 7, 0, 0], pct: '82%' },
  { code: '402', key: 'motivo_402', vals: [2, 0, 5, 0, 0], pct: '96%' },
  { code: '999', key: 'motivo_999', vals: [6, 12, 8, 14, 21], pct: '—' },
];
const TOP_MOTIVOS = [
  { code: '304', label: 'motivo_304', count: 69, delta: '+18%', up: true },
  { code: '211', label: 'motivo_211', count: 37, delta: '+4%', up: true },
  { code: '999', label: 'motivo_999', count: 61, delta: '−9%', up: false },
  { code: '502', label: 'motivo_502', count: 22, delta: '−2%', up: false },
  { code: '118', label: 'motivo_118', count: 11, delta: '+1%', up: true },
];
const TOP_PRODUCTS: { name: string; v: number; p: string }[] = [
  { name: 'Cuenta de ahorros', v: 118, p: '30.7%' },
  { name: 'Tarjeta de crédito', v: 92, p: '24.0%' },
  { name: 'Crédito vehicular', v: 54, p: '14.1%' },
  { name: 'Crédito hipotecario', v: 41, p: '10.7%' },
  { name: 'Crédito de consumo', v: 36, p: '9.4%' },
  { name: 'Aportes (CTS / AFP)', v: 24, p: '6.3%' },
];

function heatClass(v: number): string {
  if (v >= 30) return 'bg-brand-cyan/40 text-brand-navy font-semibold';
  if (v >= 15) return 'bg-brand-cyan/25 text-brand-navy';
  if (v >= 6) return 'bg-brand-cyan/15 text-fg';
  if (v >= 1) return 'bg-brand-cyan/5 text-fg';
  return 'text-fg-subtle';
}

export default async function AnalyticsPage() {
  const sessionId = (await cookies()).get(SESSION_COOKIE)?.value;
  const session = getSession(sessionId);
  if (!session) {
    redirect('/login');
  }

  const locale = await currentLocale();
  const tr = (key: string) => t(locale, key);

  const pilotBadge = tr('pilot.badge');
  const previewOnly = tr('analytics.preview_only');

  const kpis = [
    { label: tr('analytics.kpis.total_complaints'), value: '384' },
    { label: tr('analytics.kpis.resolved_on_time'), value: '91.4%' },
    { label: tr('analytics.kpis.active_institutions'), value: '2' },
    { label: tr('analytics.kpis.sucave_match'), value: '98%' },
  ];

  const cadence = [
    {
      label: tr('analytics.cadence.api_nrt.label'),
      detail: tr('analytics.cadence.api_nrt.detail'),
      count: 12,
    },
    {
      label: tr('analytics.cadence.daily.label'),
      detail: tr('analytics.cadence.daily.detail'),
      count: 38,
    },
    {
      label: tr('analytics.cadence.weekly_monthly.label'),
      detail: tr('analytics.cadence.weekly_monthly.detail'),
      count: 150,
    },
    {
      label: tr('analytics.cadence.quarterly.label'),
      detail: tr('analytics.cadence.quarterly.detail'),
      count: 47,
    },
  ];

  const rowTotal = (vals: number[]) => vals.reduce((a, b) => a + b, 0);
  const colTotal = (i: number) => MATRIX_ROWS.reduce((acc, r) => acc + r.vals[i], 0);
  const grandTotal = MATRIX_ROWS.reduce((acc, r) => acc + rowTotal(r.vals), 0);

  return (
    <main className="flex flex-col">
      <PageHeader
        breadcrumb={['Supervisión', 'Analítica', tr('analytics.subtabs.rr1')]}
        title={tr('analytics.title')}
        subtitle={tr('analytics.subtitle')}
        right={
          <Badge variant="role" className="border-brand-gold/40 bg-brand-gold/10 text-brand-navy">
            {pilotBadge}
          </Badge>
        }
      />

      <div className="mx-auto w-full max-w-7xl space-y-3 px-6 py-4">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {kpis.map(k => (
            <Card key={k.label} className="border-border">
              <CardBody className="px-4 py-3">
                <p className="font-mono text-2xs uppercase tracking-wider text-fg-muted">
                  {k.label}
                </p>
                <p className="mt-1 font-mono text-3xl font-semibold leading-none tabular text-brand-navy">
                  {k.value}
                </p>
              </CardBody>
            </Card>
          ))}
        </div>

        <nav aria-label="RR subtabs" className="flex gap-1 border-b border-border">
          {(['rr1', 'rr2', 'rr3'] as const).map((id, i) => (
            <span
              key={id}
              className={
                'flex items-center gap-2 px-3 py-2 text-xs ' +
                (i === 0
                  ? 'border-b-2 border-brand-cyan font-medium text-fg'
                  : 'text-fg-muted')
              }
            >
              <span className="font-mono text-2xs uppercase tracking-wider text-brand-cyan">
                {id.toUpperCase()}
              </span>
              {tr(`analytics.subtabs.${id}`).split('·').slice(1).join('·').trim() ||
                tr(`analytics.subtabs.${id}`)}
            </span>
          ))}
        </nav>

        {/* RR1 matrix */}
        <Card className="border-border">
          <CardHeader className="border-b border-border px-4 py-2.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <CardTitle className="font-mono text-2xs font-semibold uppercase tracking-wider text-brand-navy">
                {tr('analytics.matrix.title')}
              </CardTitle>
              <span className="font-mono text-2xs uppercase tracking-wider text-fg-muted">
                {tr('analytics.matrix.subtitle')}
              </span>
            </div>
          </CardHeader>
          <CardBody className="overflow-x-auto p-0">
            <table className="min-w-full border-collapse font-mono text-xs">
              <thead className="bg-surface-subtle text-fg-muted">
                <tr>
                  <th scope="col" className="px-3 py-2 text-left uppercase tracking-wider">
                    {tr('analytics.matrix.motivo_col')}
                  </th>
                  {CHANNELS.map(ch => (
                    <th
                      key={ch}
                      scope="col"
                      className="px-2 py-2 text-right uppercase tracking-wider"
                    >
                      {ch}
                    </th>
                  ))}
                  <th scope="col" className="bg-brand-cyan/10 px-2 py-2 text-right uppercase tracking-wider text-brand-navy">
                    {tr('analytics.matrix.total_row')}
                  </th>
                  <th scope="col" className="bg-brand-cyan/10 px-2 py-2 text-right uppercase tracking-wider text-brand-navy">
                    %
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {MATRIX_ROWS.map(r => (
                  <tr key={r.code}>
                    <td className="px-3 py-1.5 text-left">
                      <span className="mr-2 font-semibold text-brand-navy">{r.code}</span>
                      <span className="font-sans text-xs text-fg">{tr(`analytics.matrix.${r.key}`)}</span>
                    </td>
                    {r.vals.map((v, i) => (
                      <td
                        key={i}
                        className={'px-2 py-1.5 text-right tabular ' + heatClass(v)}
                      >
                        {v > 0 ? v : '—'}
                      </td>
                    ))}
                    <td className="bg-brand-cyan/10 px-2 py-1.5 text-right font-semibold tabular text-brand-navy">
                      {rowTotal(r.vals)}
                    </td>
                    <td className="bg-brand-cyan/10 px-2 py-1.5 text-right tabular text-fg">
                      {r.pct}
                    </td>
                  </tr>
                ))}
                <tr className="bg-surface-subtle">
                  <td className="px-3 py-2 text-left font-semibold uppercase tracking-wider text-brand-navy">
                    {tr('analytics.matrix.total_row')}
                  </td>
                  {CHANNELS.map((_, i) => (
                    <td
                      key={i}
                      className="px-2 py-2 text-right font-semibold tabular text-brand-navy"
                    >
                      {colTotal(i)}
                    </td>
                  ))}
                  <td className="bg-brand-cyan/20 px-2 py-2 text-right font-semibold tabular text-brand-navy">
                    {grandTotal}
                  </td>
                  <td className="bg-brand-cyan/20 px-2 py-2 text-right tabular text-fg">
                    91%
                  </td>
                </tr>
              </tbody>
            </table>
          </CardBody>
        </Card>

        {/* Products + Motivos */}
        <div className="grid gap-3 lg:grid-cols-2">
          <Card className="border-border">
            <CardHeader className="border-b border-border px-4 py-2.5">
              <CardTitle className="font-mono text-2xs font-semibold uppercase tracking-wider text-brand-navy">
                {tr('analytics.products.title')}
              </CardTitle>
              <p className="font-mono text-2xs uppercase tracking-wider text-fg-muted">
                {tr('analytics.products.subtitle')}
              </p>
            </CardHeader>
            <CardBody className="px-4 py-3">
              <ul className="space-y-1.5 text-xs">
                {TOP_PRODUCTS.map(p => (
                  <li key={p.name} className="flex items-center gap-2">
                    <span className="w-36 truncate text-fg">{p.name}</span>
                    <span className="flex-1">
                      <span
                        className="block h-2 rounded-sbs bg-brand-cyan"
                        style={{ width: `${Math.min(100, (p.v / 118) * 100)}%` }}
                        aria-hidden="true"
                      />
                    </span>
                    <span className="w-20 text-right font-mono tabular text-fg">
                      {p.v}{' '}
                      <span className="text-fg-muted">· {p.p}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </CardBody>
          </Card>

          <Card className="border-border">
            <CardHeader className="border-b border-border px-4 py-2.5">
              <CardTitle className="font-mono text-2xs font-semibold uppercase tracking-wider text-brand-navy">
                {tr('analytics.motivos.title')}
              </CardTitle>
              <p className="font-mono text-2xs uppercase tracking-wider text-fg-muted">
                {tr('analytics.motivos.subtitle')}
              </p>
            </CardHeader>
            <CardBody className="p-0">
              <table className="min-w-full border-collapse font-mono text-xs">
                <thead className="bg-surface-subtle text-fg-muted">
                  <tr>
                    <th className="px-2 py-1.5 text-left uppercase tracking-wider">
                      {tr('analytics.motivos.rank_col')}
                    </th>
                    <th className="px-2 py-1.5 text-left uppercase tracking-wider">
                      {tr('analytics.motivos.code_col')}
                    </th>
                    <th className="px-2 py-1.5 text-left uppercase tracking-wider">
                      {tr('analytics.motivos.label_col')}
                    </th>
                    <th className="px-2 py-1.5 text-right uppercase tracking-wider">
                      {tr('analytics.motivos.count_col')}
                    </th>
                    <th className="px-2 py-1.5 text-right uppercase tracking-wider">
                      {tr('analytics.motivos.delta_col')}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {TOP_MOTIVOS.map((m, i) => (
                    <tr key={m.code}>
                      <td className="px-2 py-1.5 text-fg-muted">{i + 1}</td>
                      <td className="px-2 py-1.5 font-semibold text-brand-navy">{m.code}</td>
                      <td className="px-2 py-1.5 font-sans text-xs text-fg">
                        {tr(`analytics.matrix.${m.label}`)}
                      </td>
                      <td className="px-2 py-1.5 text-right font-semibold tabular text-brand-navy">
                        {m.count}
                      </td>
                      <td
                        className={
                          'px-2 py-1.5 text-right tabular ' +
                          (m.up ? 'text-severity-high-fg' : 'text-severity-low-fg')
                        }
                      >
                        {m.up ? '▲ ' : '▼ '}
                        {m.delta}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardBody>
          </Card>
        </div>

        {/* Cadencia coverage strip */}
        <Card className="border-border">
          <CardHeader className="border-b border-border px-4 py-2.5">
            <CardTitle className="font-mono text-2xs font-semibold uppercase tracking-wider text-brand-navy">
              {tr('analytics.cadence.title')}
            </CardTitle>
            <p className="font-mono text-2xs uppercase tracking-wider text-fg-muted">
              {tr('analytics.cadence.subtitle')}
            </p>
          </CardHeader>
          <CardBody className="p-0">
            <div className="grid grid-cols-2 divide-x divide-border-subtle sm:grid-cols-4">
              {cadence.map(c => (
                <div key={c.label} className="border-t border-border-subtle px-4 py-3 first:border-t-0 sm:border-t-0">
                  <p className="font-mono text-2xs uppercase tracking-wider text-brand-cyan">
                    {c.label}
                  </p>
                  <p className="mt-1 font-mono text-2xl font-semibold leading-none tabular text-brand-navy">
                    {c.count}
                  </p>
                  <p className="mt-1 text-xs text-fg-muted">{c.detail}</p>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>

        {/* Export panel */}
        <Card className="border-border">
          <CardHeader className="border-b border-border px-4 py-2.5">
            <CardTitle className="flex items-center gap-2 font-mono text-2xs font-semibold uppercase tracking-wider text-brand-navy">
              <Sparkles className="h-3.5 w-3.5 text-brand-gold" aria-hidden="true" />
              {tr('analytics.export_report')}
            </CardTitle>
          </CardHeader>
          <CardBody className="px-4 py-3">
            <div className="grid gap-2 sm:grid-cols-2">
              <Button variant="default" size="sm" disabled aria-disabled="true">
                <FileSpreadsheet className="h-3.5 w-3.5" aria-hidden="true" />
                {tr('analytics.export_report')}
              </Button>
              <Button variant="outline" size="sm" disabled aria-disabled="true">
                <Download className="h-3.5 w-3.5" aria-hidden="true" />
                {tr('analytics.download_csv')}
              </Button>
              <Button variant="outline" size="sm" disabled aria-disabled="true" className="sm:col-span-2">
                <BarChart3 className="h-3.5 w-3.5" aria-hidden="true" />
                {tr('analytics.compare_label')}
              </Button>
            </div>
            <p className="mt-3 text-2xs text-fg-muted">{previewOnly}</p>
          </CardBody>
        </Card>
      </div>
    </main>
  );
}
