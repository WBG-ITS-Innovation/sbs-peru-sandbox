/* eslint-disable i18next/no-literal-string */
'use client';

import { AlertTriangle, Bell, Building2, ChevronLeft, ChevronRight, ChevronRight as ChevR, ExternalLink, FileDown, Link2 } from 'lucide-react';
import Link from 'next/link';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from 'recharts';

import {
  Badge,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Sheet,
  SheetContent,
  SheetTitle,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui';
import type { Locale } from '@/i18n';
import { bi } from '@/lib/bi';
import { generateBriefPdf } from '@/lib/brief-pdf';
import { cn } from '@/lib/cn';
import { DSC_SAMPLE, FRAUD_LABEL_ES } from '@/lib/source-samples';

// View 2 — red flags. Reuses the real aggregate endpoint + the sources
// endpoint. Flags are COMPUTED from real metrics: high pending %, favor-bank
// skew, and social∩INDECOPI correlation (institution flagged by both feeds).

type Scope = 'entity' | 'group' | 'all';

interface PatternRow {
  motivo_code: string;
  submotivo: string | null;
  submotivo_2?: string | null;
  topic: string | null;
  institution_id?: string;
  institution_name?: string;
  cohort_id?: string;
  n_complaints: number;
  n_pending: number;
  n_resolved: number;
  n_favor_user: number;
  n_favor_bank: number;
  n_favor_partial: number;
  pct_favor_user: number | null;
  pct_favor_bank: number | null;
  pct_partial: number | null;
  complaint_ids?: string[];
}

interface Sources {
  social_by_indicator: { indicator: string; n: number }[];
  social_institution_codes: string[];
  social_total: number;
  indecopi: { institution_id: string; complaint_category: string; n: number }[];
  indecopi_institution_ids: string[];
}

const SCOPE_TABS: { id: Scope; es: string; en: string }[] = [
  { id: 'entity', es: 'Por entidad', en: 'By entity' },
  { id: 'group', es: 'Por grupo', en: 'By group' },
  { id: 'all', es: 'Todas las entidades', en: 'All entities' },
];

// Flag thresholds (documented so the demo can explain them honestly).
const PENDING_FLAG = 25; // % pending ≥ 25 → backlog flag
const BANK_FLAG = 50; // % favor-bank ≥ 50 and > favor-user → skew flag

function pendingPct(r: PatternRow): number {
  return r.n_complaints > 0 ? (100 * r.n_pending) / r.n_complaints : 0;
}

interface Flagged extends PatternRow {
  flags: string[];
}

const PAGE_SIZE = 15;

export function RedFlags({ locale }: { locale: Locale }) {
  const [scope, setScope] = useState<Scope>('entity');
  const [rows, setRows] = useState<PatternRow[]>([]);
  const [sources, setSources] = useState<Sources | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [tileFilter, setTileFilter] = useState<'all' | 'highrisk' | 'corr' | 'topinst'>('all');
  const [period, setPeriod] = useState<{ start: string | null; end: string | null } | null>(null);
  const [briefingId, setBriefingId] = useState<string | null>(null);
  const [detail, setDetail] = useState<{ row: Flagged; kind: string } | null>(null);
  const tableRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setLoading(true);
    fetch(`/app/api/aggregates/patterns?scope=${scope}`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((d: { rows?: PatternRow[] }) => setRows(d.rows ?? []))
      .catch(() => undefined)
      .finally(() => setLoading(false));
  }, [scope]);

  useEffect(() => {
    fetch('/app/api/aggregates/sources', { cache: 'no-store' })
      .then((r) => r.json())
      .then((d: Sources) => setSources(d))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    fetch('/app/api/aggregates/trend', { cache: 'no-store' })
      .then((r) => r.json())
      .then((d: { period?: { start: string | null; end: string | null } }) => setPeriod(d.period ?? null))
      .catch(() => undefined);
  }, []);

  async function downloadBrief(r: Flagged) {
    const id = `${r.institution_id ?? r.cohort_id ?? 'all'}-${r.motivo_code}-${r.submotivo ?? ''}`;
    setBriefingId(id);
    try {
      await generateBriefPdf(r, { period });
    } finally {
      setBriefingId(null);
    }
  }

  const correlationInsts = useMemo(() => {
    if (!sources) return new Set<string>();
    const social = new Set(sources.social_institution_codes);
    return new Set(sources.indecopi_institution_ids.filter((i) => social.has(i)));
  }, [sources]);

  const flagged: Flagged[] = useMemo(() => {
    const out: Flagged[] = [];
    for (const r of rows) {
      const flags: string[] = [];
      if (pendingPct(r) >= PENDING_FLAG && r.n_pending > 0) flags.push('pending');
      if (
        r.pct_favor_bank != null &&
        r.pct_favor_bank >= BANK_FLAG &&
        (r.pct_favor_user == null || r.pct_favor_bank > r.pct_favor_user)
      ) {
        flags.push('bank');
      }
      if (scope === 'entity' && r.institution_id && correlationInsts.has(r.institution_id)) {
        flags.push('corr');
      }
      if (flags.length) out.push({ ...r, flags });
    }
    out.sort((a, b) => b.flags.length - a.flags.length || b.n_complaints - a.n_complaints);
    return out;
  }, [rows, scope, correlationInsts]);

  // Tile metrics — all computed from the real flagged set.
  const metrics = useMemo(() => {
    const highRisk = flagged.filter((r) => r.flags.includes('bank') || r.flags.includes('corr'));
    const corr = flagged.filter((r) => r.flags.includes('corr'));
    const byInst = new Map<string, number>();
    for (const r of flagged) {
      const k = (scope === 'group' ? r.cohort_id : r.institution_name ?? r.institution_id) ?? '—';
      byInst.set(k, (byInst.get(k) ?? 0) + r.n_complaints);
    }
    const top = [...byInst.entries()].sort((a, b) => b[1] - a[1])[0] ?? null;
    return {
      highRiskCount: highRisk.length,
      corrCount: corr.length,
      corrInsts: [...new Set(corr.map((r) => r.institution_name ?? r.institution_id ?? '—'))],
      topInst: top ? { name: top[0], n: top[1] } : null,
    };
  }, [flagged, scope]);

  // Flags-by-type chart (computed from flagged).
  const flagsByType = useMemo(() => {
    let backlog = 0, bank = 0, corr = 0;
    for (const r of flagged) {
      if (r.flags.includes('pending')) backlog += 1;
      if (r.flags.includes('bank')) bank += 1;
      if (r.flags.includes('corr')) corr += 1;
    }
    return [
      { tipo: bi(locale, 'Backlog', 'Backlog'), n: backlog },
      { tipo: bi(locale, 'Sesgo entidad', 'Bank skew'), n: bank },
      { tipo: bi(locale, 'Social+INDECOPI', 'Social+INDECOPI'), n: corr },
    ];
  }, [flagged, locale]);

  const flagsBySource = useMemo(
    () => [
      { fuente: bi(locale, 'Reclamos', 'Complaints'), n: flagged.length },
      { fuente: bi(locale, 'Social', 'Social'), n: sources?.social_total ?? 0 },
      { fuente: 'INDECOPI', n: (sources?.indecopi ?? []).reduce((a, c) => a + c.n, 0) },
    ],
    [flagged, sources, locale],
  );

  // Apply the active tile filter, then paginate.
  const tileFiltered = useMemo(() => {
    if (tileFilter === 'highrisk') return flagged.filter((r) => r.flags.includes('bank') || r.flags.includes('corr'));
    if (tileFilter === 'corr') return flagged.filter((r) => r.flags.includes('corr'));
    if (tileFilter === 'topinst' && metrics.topInst) {
      const t = metrics.topInst.name;
      return flagged.filter((r) => ((scope === 'group' ? r.cohort_id : r.institution_name ?? r.institution_id) ?? '—') === t);
    }
    return flagged;
  }, [flagged, tileFilter, metrics, scope]);

  const totalRows = tileFiltered.length;
  const totalPages = Math.max(1, Math.ceil(totalRows / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pageRows = tileFiltered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  // The representative flagged pattern behind each notification card — the
  // single issue its detail panel and brief describe.
  const repRows = useMemo(() => {
    const highrisk = flagged.find((r) => r.flags.includes('bank') || r.flags.includes('corr')) ?? flagged[0] ?? null;
    const corr = flagged.find((r) => r.flags.includes('corr')) ?? null;
    let topinst: Flagged | null = null;
    if (metrics.topInst) {
      const t = metrics.topInst.name;
      topinst = flagged.find((r) => ((scope === 'group' ? r.cohort_id : r.institution_name ?? r.institution_id) ?? '—') === t) ?? null;
    }
    return { highrisk, topinst, corr } as Record<'highrisk' | 'topinst' | 'corr', Flagged | null>;
  }, [flagged, metrics, scope]);

  // Card click: pin the table filter + scroll, and open the issue detail.
  const openCard = (id: 'highrisk' | 'topinst' | 'corr', kind: string) => {
    setTileFilter(id);
    setPage(1);
    const rep = repRows[id];
    if (rep) setDetail({ row: rep, kind });
    tableRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const entityOf = (r: Flagged): string =>
    (scope === 'group' ? r.cohort_id : r.institution_name ?? r.institution_id) ?? '—';

  const showInst = scope !== 'all';
  const instHeader = scope === 'group' ? bi(locale, 'Cohorte', 'Cohort') : bi(locale, 'Entidad', 'Entity');

  const flagBadge = (f: string) => {
    if (f === 'pending')
      return <Badge key={f} variant="pending">{bi(locale, 'backlog', 'backlog')}</Badge>;
    if (f === 'bank')
      return <Badge key={f} variant="high">{bi(locale, 'sesgo a favor entidad', 'bank-favor skew')}</Badge>;
    return <Badge key={f} variant="high">{bi(locale, 'social+INDECOPI', 'social+INDECOPI')}</Badge>;
  };

  return (
    <section className="space-y-4">
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 text-red-600" aria-hidden="true" />
        <h2 className="text-lg font-semibold tracking-tight text-brand-navy">
          {bi(locale, 'Patrones con alerta roja', 'Red-flag patterns')}
        </h2>
        {flagged.length > 0 ? (
          <Badge variant="high" className="ml-1 inline-flex items-center gap-1">
            <Bell className="h-3 w-3" aria-hidden="true" />
            {bi(locale, `${flagged.length} alertas`, `${flagged.length} alerts`)}
          </Badge>
        ) : null}
      </div>

      {/* Notification cards — prominent, at the very top. Click → detail + filter + scroll. */}
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        {([
          { id: 'highrisk', Icon: AlertTriangle, label: bi(locale, 'Patrones de alto riesgo', 'High-risk patterns'), value: metrics.highRiskCount, brief: bi(locale, 'Sesgo a favor de la entidad o correlación cross-source.', 'Bank-favor skew or cross-source correlation.') },
          { id: 'topinst', Icon: Building2, label: bi(locale, 'Entidad más señalada', 'Top flagged institution'), value: metrics.topInst?.name ?? '—', brief: metrics.topInst ? bi(locale, `${metrics.topInst.n} reclamos en patrones marcados.`, `${metrics.topInst.n} complaints across flagged patterns.`) : bi(locale, 'Sin datos.', 'No data.') },
          { id: 'corr', Icon: Link2, label: bi(locale, 'Correlaciones cross-source', 'Cross-source correlations'), value: metrics.corrCount, brief: metrics.corrInsts.length ? bi(locale, `Social + INDECOPI: ${metrics.corrInsts.join(', ')}.`, `Social + INDECOPI: ${metrics.corrInsts.join(', ')}.`) : bi(locale, 'Sin correlaciones (solo alcance por entidad).', 'No correlations (entity scope only).') },
        ] as const).map((t) => {
          const Icon = t.Icon;
          const active = tileFilter === t.id;
          const rep = repRows[t.id];
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => openCard(t.id, t.label)}
              disabled={!rep}
              className={cn(
                'group relative flex flex-col rounded-sbs border border-l-4 border-red-200 bg-red-50/60 px-4 py-3 text-left shadow-sm transition-all hover:bg-red-50 hover:shadow-md disabled:opacity-50 disabled:hover:shadow-sm',
                active ? 'border-l-red-600 ring-2 ring-red-300' : 'border-l-red-600',
              )}
            >
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1.5 text-2xs font-bold uppercase tracking-wide text-red-700">
                  <Icon className="h-4 w-4" aria-hidden="true" />
                  {t.label}
                </span>
                <ChevR className="h-4 w-4 text-red-400 transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
              </div>
              <div className="mt-1 truncate text-xl font-bold tabular-nums text-brand-navy">{t.value}</div>
              <div className="text-2xs leading-snug text-fg-muted">{t.brief}</div>
              {rep ? (
                <div className="mt-1.5 text-2xs font-semibold text-red-700 underline-offset-2 group-hover:underline">
                  {bi(locale, 'Ver detalle →', 'View detail →')}
                </div>
              ) : null}
            </button>
          );
        })}
      </div>

      <div className="flex gap-1 border-b border-border">
        {SCOPE_TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setScope(t.id)}
            className={cn(
              'rounded-t-sbs border-b-2 px-3 py-1.5 text-sm font-medium transition-colors',
              scope === t.id ? 'border-red-600 text-brand-navy' : 'border-transparent text-fg-muted hover:text-fg',
            )}
          >
            {bi(locale, t.es, t.en)}
          </button>
        ))}
      </div>

      <p className="text-2xs italic text-fg-subtle">
        {bi(
          locale,
          `Reglas (sobre datos reales): % pendiente ≥ ${PENDING_FLAG}, % a favor de la entidad ≥ ${BANK_FLAG} y mayor que a favor del usuario, y correlación social+INDECOPI (institución señalada por ambas fuentes).`,
          `Rules (over real data): pending % ≥ ${PENDING_FLAG}, favor-bank % ≥ ${BANK_FLAG} and above favor-user, and social+INDECOPI correlation (institution flagged by both feeds).`,
        )}
      </p>

      {/* Flag charts */}
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Card className="p-2">
          <h3 className="mb-1 text-2xs font-semibold uppercase tracking-wide text-fg-subtle">{bi(locale, 'Alertas por tipo', 'Flags by type')}</h3>
          <div className="h-[160px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={flagsByType} layout="vertical" margin={{ top: 2, right: 12, bottom: 0, left: 6 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 9 }} />
                <YAxis type="category" dataKey="tipo" tick={{ fontSize: 9 }} width={110} />
                <RTooltip />
                <Bar dataKey="n" radius={[0, 2, 2, 0]}>
                  {flagsByType.map((d) => <Cell key={d.tipo} fill="#b91c1c" />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card className="p-2">
          <h3 className="mb-1 text-2xs font-semibold uppercase tracking-wide text-fg-subtle">{bi(locale, 'Señales por fuente (real)', 'Signals by source (real)')}</h3>
          <div className="h-[160px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={flagsBySource} layout="vertical" margin={{ top: 2, right: 12, bottom: 0, left: 6 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 9 }} />
                <YAxis type="category" dataKey="fuente" tick={{ fontSize: 9 }} width={110} />
                <RTooltip />
                <Bar dataKey="n" radius={[0, 2, 2, 0]} fill="#002244" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <div ref={tableRef}>
        {tileFilter !== 'all' ? (
          <button type="button" onClick={() => setTileFilter('all')} className="mb-1 text-2xs text-fg-link underline">
            {bi(locale, '× Quitar filtro de tile', '× Clear tile filter')}
          </button>
        ) : null}
        <Table>
          <TableHeader>
            <TableRow>
              {showInst ? <TableHead>{instHeader}</TableHead> : null}
              <TableHead>{bi(locale, 'Motivo', 'Motive')}</TableHead>
              <TableHead>{bi(locale, 'Submotivo', 'Submotive')}</TableHead>
              <TableHead className="text-right">{bi(locale, 'N°', 'N°')}</TableHead>
              <TableHead className="text-right">{bi(locale, '% pendiente', '% pending')}</TableHead>
              <TableHead className="text-right">{bi(locale, '% favor entidad', '% favor bank')}</TableHead>
              <TableHead>{bi(locale, 'Alertas', 'Flags')}</TableHead>
              <TableHead className="text-right">{bi(locale, 'Brief', 'Brief')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {pageRows.map((r, i) => (
              <TableRow key={`${r.institution_id ?? r.cohort_id ?? 'all'}-${r.motivo_code}-${r.submotivo}-${i}`}>
                {showInst ? (
                  <TableCell className="text-2xs text-fg">{scope === 'group' ? r.cohort_id : r.institution_name ?? r.institution_id}</TableCell>
                ) : null}
                <TableCell className="text-xs">{r.motivo_code}</TableCell>
                <TableCell className="text-xs text-fg-muted">{r.submotivo ?? '—'}</TableCell>
                <TableCell className="text-right font-mono tabular-nums">{r.n_complaints}</TableCell>
                <TableCell className="text-right font-mono tabular-nums text-[#9a6f00]">{pendingPct(r).toFixed(1)}%</TableCell>
                <TableCell className="text-right font-mono tabular-nums text-red-700">{r.pct_favor_bank == null ? '—' : `${r.pct_favor_bank.toFixed(1)}%`}</TableCell>
                <TableCell><div className="flex flex-wrap gap-1">{r.flags.map(flagBadge)}</div></TableCell>
                <TableCell className="text-right">
                  {(() => {
                    const id = `${r.institution_id ?? r.cohort_id ?? 'all'}-${r.motivo_code}-${r.submotivo ?? ''}`;
                    const busy = briefingId === id;
                    return (
                      <button
                        type="button"
                        onClick={() => downloadBrief(r)}
                        disabled={busy}
                        title={bi(locale, 'Generar brief PDF con los datos reales de este patrón', 'Generate a PDF brief from this pattern’s real data')}
                        className="inline-flex items-center gap-1 rounded-sbs border border-border bg-surface px-2 py-1 text-2xs font-medium text-brand-navy hover:bg-surface-subtle disabled:opacity-50"
                      >
                        <FileDown className="h-3 w-3" aria-hidden="true" />
                        {busy ? bi(locale, 'Generando…', 'Generating…') : bi(locale, 'Brief', 'Brief')}
                      </button>
                    );
                  })()}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {totalRows === 0 ? (
        <p className="py-4 text-center text-xs text-fg-muted">
          {loading ? bi(locale, 'Cargando…', 'Loading…') : bi(locale, 'Sin patrones marcados en este alcance.', 'No flagged patterns in this scope.')}
        </p>
      ) : (
        <div className="flex items-center justify-between gap-2">
          <span className="font-mono text-2xs tabular-nums text-fg-muted">
            {bi(locale, `${totalRows} patrones marcados · pág. ${safePage}/${totalPages}`, `${totalRows} flagged patterns · page ${safePage}/${totalPages}`)}
          </span>
          <div className="flex items-center gap-1">
            <button type="button" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={safePage <= 1} className="flex items-center gap-0.5 rounded-sbs border border-border bg-surface px-2 py-1 text-2xs disabled:opacity-40">
              <ChevronLeft className="h-3 w-3" aria-hidden="true" />{bi(locale, 'Anterior', 'Prev')}
            </button>
            <button type="button" onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={safePage >= totalPages} className="flex items-center gap-0.5 rounded-sbs border border-border bg-surface px-2 py-1 text-2xs disabled:opacity-40">
              {bi(locale, 'Siguiente', 'Next')}<ChevronRight className="h-3 w-3" aria-hidden="true" />
            </button>
          </div>
        </div>
      )}

      {/* Per-source tables */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{bi(locale, 'Redes sociales (real)', 'Social media (real)')}</CardTitle>
          </CardHeader>
          <CardBody>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{bi(locale, 'Indicador', 'Indicator')}</TableHead>
                  <TableHead className="text-right">{bi(locale, 'Señales', 'Signals')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(sources?.social_by_indicator ?? []).map((s) => (
                  <TableRow key={s.indicator}>
                    <TableCell className="text-xs">{FRAUD_LABEL_ES[s.indicator] ?? s.indicator}</TableCell>
                    <TableCell className="text-right font-mono tabular-nums">{s.n}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <p className="mt-2 text-2xs text-fg-subtle">
              {bi(
                locale,
                `${sources?.social_total ?? 0} señales · instituciones señaladas: ${sources?.social_institution_codes.join(', ') || '—'}.`,
                `${sources?.social_total ?? 0} signals · flagged institutions: ${sources?.social_institution_codes.join(', ') || '—'}.`,
              )}
            </p>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{bi(locale, 'Casos INDECOPI (real)', 'INDECOPI cases (real)')}</CardTitle>
          </CardHeader>
          <CardBody>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{bi(locale, 'Institución', 'Institution')}</TableHead>
                  <TableHead>{bi(locale, 'Categoría', 'Category')}</TableHead>
                  <TableHead className="text-right">{bi(locale, 'Casos', 'Cases')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(sources?.indecopi ?? []).map((c) => (
                  <TableRow key={`${c.institution_id}-${c.complaint_category}`}>
                    <TableCell className="font-mono text-2xs text-fg-muted">{c.institution_id}</TableCell>
                    <TableCell className="text-xs">{c.complaint_category}</TableCell>
                    <TableCell className="text-right font-mono tabular-nums">{c.n}</TableCell>
                  </TableRow>
                ))}
                {(sources?.indecopi?.length ?? 0) === 0 ? (
                  <TableRow><TableCell className="py-3 text-2xs text-fg-muted">{bi(locale, 'Sin casos.', 'No cases.')}</TableCell></TableRow>
                ) : null}
              </TableBody>
            </Table>
          </CardBody>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-sm">{bi(locale, 'SBS DSC — Atención al Ciudadano', 'SBS DSC — Citizen assistance')}</CardTitle>
            <Badge variant="pending" className="ml-2 border-brand-gold/60 bg-brand-gold/15 text-[#7a5b00]">
              {bi(locale, 'datos de muestra', 'sample data')}
            </Badge>
          </CardHeader>
          <CardBody>
            <div className="max-h-72 overflow-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{bi(locale, 'Fecha', 'Date')}</TableHead>
                    <TableHead>{bi(locale, 'Canal', 'Channel')}</TableHead>
                    <TableHead>{bi(locale, 'Tema', 'Topic')}</TableHead>
                    <TableHead className="text-right">{bi(locale, 'Consultas', 'Inquiries')}</TableHead>
                    <TableHead>{bi(locale, 'Estado', 'Status')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {DSC_SAMPLE.map((r) => (
                    <TableRow key={`${r.fecha}-${r.tema}`}>
                      <TableCell className="font-mono text-2xs text-fg-muted">{r.fecha}</TableCell>
                      <TableCell className="text-2xs">{r.canal}</TableCell>
                      <TableCell className="text-xs">{r.tema}</TableCell>
                      <TableCell className="text-right font-mono tabular-nums">{r.consultas}</TableCell>
                      <TableCell className="text-2xs text-fg-muted">{r.estado}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardBody>
        </Card>
      </div>

      {/* Issue detail — opened from a notification card. Shows the specific
          flagged pattern: institution, motivo, metrics, contributing
          complaints (clickable), and the Reclamito brief PDF. */}
      <Sheet open={detail != null} onOpenChange={(o) => { if (!o) setDetail(null); }}>
        <SheetContent closeLabel={bi(locale, 'Cerrar', 'Close')} className="overflow-y-auto">
          {detail ? (() => {
            const r = detail.row;
            const busy = briefingId === `${r.institution_id ?? r.cohort_id ?? 'all'}-${r.motivo_code}-${r.submotivo ?? ''}`;
            return (
              <div className="space-y-3 pr-6">
                <div className="flex items-center gap-1.5 text-2xs font-bold uppercase tracking-wide text-red-700">
                  <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
                  {detail.kind}
                </div>
                <SheetTitle className="text-base text-brand-navy">{entityOf(r)}</SheetTitle>
                <p className="font-mono text-2xs text-fg-subtle">
                  {r.motivo_code}{r.submotivo ? ` · ${r.submotivo}` : ''}{r.topic ? ` · ${r.topic}` : ''}
                </p>
                <div className="flex flex-wrap gap-1">{r.flags.map(flagBadge)}</div>

                <div className="grid grid-cols-2 gap-2 rounded-sbs border border-border bg-surface-subtle/40 p-2 text-2xs">
                  <div><span className="text-fg-muted">{bi(locale, 'N° reclamos', 'N° complaints')}: </span><span className="font-mono tabular-nums text-brand-navy">{r.n_complaints}</span></div>
                  <div><span className="text-fg-muted">{bi(locale, '% pendiente', '% pending')}: </span><span className="font-mono tabular-nums text-[#9a6f00]">{pendingPct(r).toFixed(1)}%</span></div>
                  <div><span className="text-fg-muted">{bi(locale, '% favor usuario', '% favor user')}: </span><span className="font-mono tabular-nums text-green-700">{r.pct_favor_user == null ? '—' : `${r.pct_favor_user.toFixed(1)}%`}</span></div>
                  <div><span className="text-fg-muted">{bi(locale, '% favor entidad', '% favor bank')}: </span><span className="font-mono tabular-nums text-red-700">{r.pct_favor_bank == null ? '—' : `${r.pct_favor_bank.toFixed(1)}%`}</span></div>
                </div>

                <p className="text-xs leading-relaxed text-fg">
                  {bi(
                    locale,
                    `Se identificaron ${r.n_complaints} reclamos en ${entityOf(r)} por "${r.motivo_code}"${r.submotivo ? ` (${r.submotivo})` : ''}. ${pendingPct(r).toFixed(1)}% permanecen pendientes${r.pct_favor_bank != null ? ` y ${r.pct_favor_bank.toFixed(1)}% se resolvieron a favor de la entidad` : ''}.`,
                    `Found ${r.n_complaints} complaints at ${entityOf(r)} for "${r.motivo_code}"${r.submotivo ? ` (${r.submotivo})` : ''}. ${pendingPct(r).toFixed(1)}% remain pending${r.pct_favor_bank != null ? ` and ${r.pct_favor_bank.toFixed(1)}% resolved in the institution's favour` : ''}.`,
                  )}
                </p>

                <div>
                  <p className="mb-1 text-2xs font-semibold uppercase tracking-wide text-fg-subtle">
                    {bi(locale, `Reclamos contribuyentes (${r.complaint_ids?.length ?? 0})`, `Contributing complaints (${r.complaint_ids?.length ?? 0})`)}
                  </p>
                  <ul className="flex flex-wrap gap-1.5">
                    {(r.complaint_ids ?? []).map((id) => (
                      <li key={id}>
                        <Link
                          href={`/processing/${id}`}
                          className="inline-flex items-center gap-1 rounded-sbs border border-border bg-surface-subtle px-2 py-0.5 font-mono text-2xs text-fg-link hover:border-brand-cyan"
                        >
                          {id}
                          <ExternalLink className="h-3 w-3" aria-hidden="true" />
                        </Link>
                      </li>
                    ))}
                    {(r.complaint_ids?.length ?? 0) === 0 ? (
                      <li className="text-2xs text-fg-muted">{bi(locale, 'Sin ids disponibles.', 'No ids available.')}</li>
                    ) : null}
                  </ul>
                </div>

                <button
                  type="button"
                  onClick={() => downloadBrief(r)}
                  disabled={busy}
                  className="inline-flex items-center gap-1.5 rounded-sbs border border-brand-navy bg-brand-navy px-3 py-2 text-xs font-medium text-fg-inverted hover:bg-brand-navy/90 disabled:opacity-50"
                >
                  <FileDown className="h-3.5 w-3.5" aria-hidden="true" />
                  {busy ? bi(locale, 'Generando…', 'Generating…') : bi(locale, 'Reclamito · Generar brief', 'Reclamito · Generate brief')}
                </button>
              </div>
            );
          })() : null}
        </SheetContent>
      </Sheet>
    </section>
  );
}
