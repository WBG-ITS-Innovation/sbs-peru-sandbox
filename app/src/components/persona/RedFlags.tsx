/* eslint-disable i18next/no-literal-string */
'use client';

import { AlertTriangle } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import {
  Badge,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui';
import type { Locale } from '@/i18n';
import { bi } from '@/lib/bi';
import { cn } from '@/lib/cn';

// View 2 — red flags. Reuses the real aggregate endpoint + the sources
// endpoint. Flags are COMPUTED from real metrics: high pending %, favor-bank
// skew, and social∩INDECOPI correlation (institution flagged by both feeds).

type Scope = 'entity' | 'group' | 'all';

interface PatternRow {
  motivo_code: string;
  submotivo: string | null;
  topic: string | null;
  institution_id?: string;
  institution_name?: string;
  cohort_id?: string;
  n_complaints: number;
  n_pending: number;
  n_resolved: number;
  pct_favor_user: number | null;
  pct_favor_bank: number | null;
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

const FRAUD_LABEL_ES: Record<string, string> = {
  PHISHING_KEYWORD: 'Phishing',
  SCAM_KEYWORD: 'Estafa',
  FAKE_APP_KEYWORD: 'Aplicación falsa',
  FAKE_AGENT_KEYWORD: 'Agente falso',
  UNAUTHORIZED_FEE_KEYWORD: 'Cargo no autorizado',
  UNAUTHORIZED_CHARGE_KEYWORD: 'Consumo no autorizado',
};

const DSC_SAMPLE = [
  { tema: 'Demora en atención de reclamo', consultas: 22, estado: 'En seguimiento' },
  { tema: 'Suplantación / fraude', consultas: 11, estado: 'Derivado a conducta' },
  { tema: 'Cobros no reconocidos', consultas: 8, estado: 'En seguimiento' },
];

function pendingPct(r: PatternRow): number {
  return r.n_complaints > 0 ? (100 * r.n_pending) / r.n_complaints : 0;
}

interface Flagged extends PatternRow {
  flags: string[];
}

export function RedFlags({ locale }: { locale: Locale }) {
  const [scope, setScope] = useState<Scope>('entity');
  const [rows, setRows] = useState<PatternRow[]>([]);
  const [sources, setSources] = useState<Sources | null>(null);
  const [loading, setLoading] = useState(true);

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
          </TableRow>
        </TableHeader>
        <TableBody>
          {flagged.map((r, i) => (
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
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {flagged.length === 0 ? (
        <p className="py-4 text-center text-xs text-fg-muted">
          {loading ? bi(locale, 'Cargando…', 'Loading…') : bi(locale, 'Sin patrones marcados en este alcance.', 'No flagged patterns in this scope.')}
        </p>
      ) : null}

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
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{bi(locale, 'Tema', 'Topic')}</TableHead>
                  <TableHead className="text-right">{bi(locale, 'Consultas', 'Inquiries')}</TableHead>
                  <TableHead>{bi(locale, 'Estado', 'Status')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {DSC_SAMPLE.map((r) => (
                  <TableRow key={r.tema}>
                    <TableCell className="text-xs">{r.tema}</TableCell>
                    <TableCell className="text-right font-mono tabular-nums">{r.consultas}</TableCell>
                    <TableCell className="text-2xs text-fg-muted">{r.estado}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardBody>
        </Card>
      </div>
    </section>
  );
}
