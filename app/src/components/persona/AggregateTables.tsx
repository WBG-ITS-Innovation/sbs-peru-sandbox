/* eslint-disable i18next/no-literal-string */
'use client';

import { ArrowDown, ArrowUp, ChevronDown, ChevronLeft, ChevronRight, Eye, EyeOff, ExternalLink, Filter, RefreshCw, X } from 'lucide-react';
import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  Badge,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Sheet,
  SheetContent,
  SheetTitle,
  SheetTrigger,
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

// View 1 — grouped-aggregate tables wired to GET /v1/internal/aggregates/patterns
// (via the /app/api/aggregates/patterns BFF). Every number is real, SQL-computed.
// Three source cards below: social = real (PII-suppressed telemetry), INDECOPI +
// SBS DSC = clearly-labelled sample (no real endpoint).

type Scope = 'entity' | 'group' | 'all';

interface PatternRow {
  motivo_code: string;
  submotivo: string | null;
  submotivo_2: string | null;
  topic: string | null;
  institution_id?: string;
  institution_name?: string;
  cohort_id?: string;
  segment?: string;
  size_tier?: string;
  n_complaints: number;
  n_pending: number;
  n_resolved: number;
  n_favor_user: number;
  n_favor_bank: number;
  n_favor_partial: number;
  pct_of_all: number | null;
  pct_favor_user: number | null;
  pct_favor_bank: number | null;
  pct_partial: number | null;
  complaint_ids?: string[];
}

const SCOPE_TABS: { id: Scope; es: string; en: string }[] = [
  { id: 'entity', es: 'Por entidad', en: 'By entity' },
  { id: 'group', es: 'Por grupo', en: 'By group' },
  { id: 'all', es: 'Todas las entidades', en: 'All entities' },
];

function pendingPct(r: PatternRow): number | null {
  return r.n_complaints > 0 ? (100 * r.n_pending) / r.n_complaints : null;
}

function fmtPct(v: number | null): string {
  return v == null ? '—' : `${v.toFixed(1)}%`;
}

const PAGE_SIZE = 20;

// WBG palette favour/pending coding — green favor-user, red favor-bank,
// gold pending. Dark shades so they stay readable on white + zebra rows.
const COL_USER = 'text-right font-mono tabular-nums text-green-700';
const COL_BANK = 'text-right font-mono tabular-nums text-red-700';
const COL_PARTIAL = 'text-right font-mono tabular-nums text-fg-muted';
const COL_PENDING = 'text-right font-mono tabular-nums text-[#9a6f00]'; // gold
const COL_NUM = 'text-right font-mono tabular-nums';

// Stable anonymisation mask: institution_id → "ENT-xxxx" (deterministic,
// consistent across rows/tabs). A redaction-on-demand action, not a reveal.
function maskEntity(institutionId: string): string {
  let h = 0;
  for (let i = 0; i < institutionId.length; i += 1) h = (h * 31 + institutionId.charCodeAt(i)) >>> 0;
  return `ENT-${h.toString(16).slice(0, 4).padStart(4, '0')}`;
}

// ---- main-table columns -----------------------------------------------------

type SortKey =
  | 'inst'
  | 'motivo_code'
  | 'submotivo'
  | 'submotivo_2'
  | 'topic'
  | 'n_complaints'
  | 'pct_of_all'
  | 'pct_favor_user'
  | 'pct_favor_bank'
  | 'pct_partial'
  | 'pct_pending';

function accessor(key: SortKey, r: PatternRow): string | number | null {
  switch (key) {
    case 'inst':
      return r.institution_id ?? r.cohort_id ?? '';
    case 'motivo_code':
      return r.motivo_code;
    case 'submotivo':
      return r.submotivo;
    case 'submotivo_2':
      return r.submotivo_2;
    case 'topic':
      return r.topic;
    case 'n_complaints':
      return r.n_complaints;
    case 'pct_of_all':
      return r.pct_of_all;
    case 'pct_favor_user':
      return r.pct_favor_user;
    case 'pct_favor_bank':
      return r.pct_favor_bank;
    case 'pct_partial':
      return r.pct_partial;
    case 'pct_pending':
      return pendingPct(r);
  }
}

// ---- lightweight multi-select (native checkboxes, click-outside) ------------

function MultiSelect({
  label,
  options,
  selected,
  onToggle,
  disabled,
}: {
  label: string;
  options: string[];
  selected: Set<string>;
  onToggle: (value: string) => void;
  disabled?: Set<string>;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, [open]);
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={cn(
          'flex items-center gap-1 rounded-sbs border px-2.5 py-1 text-xs font-medium',
          selected.size > 0
            ? 'border-brand-cyan bg-brand-cyan/10 text-brand-navy'
            : 'border-border bg-surface text-fg hover:bg-surface-subtle',
        )}
      >
        {label}
        {selected.size > 0 ? <span className="font-mono">· {selected.size}</span> : null}
        <ChevronDown className="h-3 w-3" aria-hidden="true" />
      </button>
      {open ? (
        <div className="absolute z-30 mt-1 max-h-64 w-60 overflow-auto rounded-sbs border border-border bg-surface p-1 shadow-lg">
          {options.length === 0 ? (
            <p className="px-2 py-1 text-2xs text-fg-muted">—</p>
          ) : (
            options.map((o) => {
              const isDisabled = disabled?.has(o) ?? false;
              return (
                <label
                  key={o}
                  className={cn(
                    'flex items-center gap-2 rounded-sbs px-2 py-1 text-xs',
                    isDisabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer hover:bg-surface-subtle',
                  )}
                >
                  <input
                    type="checkbox"
                    className="h-3.5 w-3.5 accent-brand-cyan"
                    checked={selected.has(o)}
                    disabled={isDisabled}
                    onChange={() => !isDisabled && onToggle(o)}
                  />
                  <span className="truncate">{o}</span>
                </label>
              );
            })
          )}
        </div>
      ) : null}
    </div>
  );
}

// ---- sample source data (NO real endpoint — badged "datos de muestra") ------

const INDECOPI_SAMPLE = [
  { categoria: 'Cobros indebidos', institucion: 'BANCO_DEMO_001', casos: 14, resumen: 'Comisiones no informadas en tarjeta de crédito.' },
  { categoria: 'Operación no reconocida', institucion: 'FINANCIERA_DEMO_003', casos: 9, resumen: 'Consumos en comercios del exterior.' },
  { categoria: 'Métodos abusivos de cobranza', institucion: 'COOPAC_DEMO_002', casos: 6, resumen: 'Llamadas fuera de horario permitido.' },
  { categoria: 'Falta de información', institucion: 'BANCO_DEMO_001', casos: 4, resumen: 'Condiciones del crédito no entregadas.' },
];

const DSC_SAMPLE = [
  { tema: 'Demora en atención de reclamo', consultas: 22, estado: 'En seguimiento', resumen: 'Plazos de respuesta superiores a 15 días hábiles.' },
  { tema: 'Información sobre comisiones', consultas: 17, estado: 'Atendido', resumen: 'Orientación sobre tarifario vigente.' },
  { tema: 'Suplantación / fraude', consultas: 11, estado: 'Derivado', resumen: 'Casos derivados a la unidad de conducta de mercado.' },
  { tema: 'Acceso a productos', consultas: 5, estado: 'Atendido', resumen: 'Consultas sobre requisitos de apertura.' },
];

// Social sample (used when the ops social_health endpoint is unreachable —
// it is NOT mounted in this build). Columns the card requests: tendencia,
// menciones, instituciones detectadas, indicador.
const SOCIAL_SAMPLE = [
  { tendencia: 'Tarjeta clonada', menciones: 142, instituciones: 3, indicador: 'Phishing' },
  { tendencia: 'App falsa de banca', menciones: 87, instituciones: 2, indicador: 'Aplicación falsa' },
  { tendencia: 'Llamadas suplantando ejecutivos', menciones: 64, instituciones: 4, indicador: 'Agente falso' },
  { tendencia: 'Cobros no reconocidos', menciones: 39, instituciones: 2, indicador: 'Consumo no autorizado' },
];

const FRAUD_LABEL_ES: Record<string, string> = {
  PHISHING_KEYWORD: 'Phishing',
  SCAM_KEYWORD: 'Estafa',
  FAKE_APP_KEYWORD: 'Aplicación falsa',
  FAKE_AGENT_KEYWORD: 'Agente falso',
  UNAUTHORIZED_FEE_KEYWORD: 'Cargo no autorizado',
  UNAUTHORIZED_CHARGE_KEYWORD: 'Consumo no autorizado',
};

interface SocialHealth {
  available: boolean;
  fraud_indicator_counts_7d?: Record<string, number>;
  signal_count_24h_by_source?: Record<string, number>;
  total_signals_7d?: number;
  entity_resolution_match_rate?: number | null;
}

function SampleBadge({ locale }: { locale: Locale }) {
  return (
    <Badge variant="pending" className="ml-2 border-brand-gold/60 bg-brand-gold/15 text-[#7a5b00]">
      {bi(locale, 'datos de muestra', 'sample data')}
    </Badge>
  );
}

// ---- the view ---------------------------------------------------------------

export function AggregateTables({ locale }: { locale: Locale }) {
  const [scope, setScope] = useState<Scope>('entity');
  const [rows, setRows] = useState<PatternRow[]>([]);
  const [total, setTotal] = useState(0);
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [errored, setErrored] = useState(false);

  const [sortKey, setSortKey] = useState<SortKey>('n_complaints');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  // Filters (client-side — the endpoint only takes `scope`).
  const [fMotivo, setFMotivo] = useState<Set<string>>(new Set());
  const [fSubmotivo, setFSubmotivo] = useState<Set<string>>(new Set());
  const [fTopic, setFTopic] = useState<Set<string>>(new Set());
  const [fEstado, setFEstado] = useState<Set<string>>(new Set());
  const [fResultado, setFResultado] = useState<Set<string>>(new Set());
  const [fInst, setFInst] = useState<Set<string>>(new Set());

  const [social, setSocial] = useState<SocialHealth | null>(null);

  // Anonymisation is a redaction-on-demand action (default OFF = real names).
  // React state → persists across tab switches, resets on a fresh session.
  const [anonymize, setAnonymize] = useState(false);
  const [page, setPage] = useState(1);

  const load = useCallback(() => {
    setLoading(true);
    setErrored(false);
    fetch(`/app/api/aggregates/patterns?scope=${scope}`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((d: { rows?: PatternRow[]; total_in_scope?: number; generated_at?: string; error?: string }) => {
        setRows(d.rows ?? []);
        setTotal(d.total_in_scope ?? 0);
        setGeneratedAt(d.generated_at ?? null);
        if (d.error) setErrored(true);
      })
      .catch(() => setErrored(true))
      .finally(() => setLoading(false));
  }, [scope]);

  useEffect(() => {
    // Institution/cohort options differ per scope, so reset filters on switch.
    setFMotivo(new Set());
    setFSubmotivo(new Set());
    setFTopic(new Set());
    setFEstado(new Set());
    setFResultado(new Set());
    setFInst(new Set());
    load();
  }, [load]);

  useEffect(() => {
    fetch('/app/api/aggregates/social', { cache: 'no-store' })
      .then((r) => r.json())
      .then((d: SocialHealth) => setSocial(d))
      .catch(() => setSocial({ available: false }));
  }, []);

  // Sorting / filtering / scope change resets to page 1 (not anonymise —
  // that only relabels, it doesn't change the row set or order).
  useEffect(() => {
    setPage(1);
  }, [scope, sortKey, sortDir, fMotivo, fSubmotivo, fTopic, fEstado, fResultado, fInst]);

  // Distinct option lists (from all fetched rows, stable while scope fixed).
  const opt = useMemo(() => {
    const u = (sel: (r: PatternRow) => string | null | undefined) =>
      Array.from(new Set(rows.map(sel).filter((x): x is string => !!x))).sort();
    return {
      motivo: u((r) => r.motivo_code),
      submotivo: u((r) => r.submotivo),
      topic: u((r) => r.topic),
      inst: u((r) => (scope === 'group' ? r.cohort_id : r.institution_id)),
    };
  }, [rows, scope]);

  const estadoOptions = [
    bi(locale, 'atendido', 'resolved'),
    bi(locale, 'pendiente', 'pending'),
    bi(locale, 'en proceso (no disp.)', 'in progress (n/a)'),
  ];
  const estadoDisabled = new Set([estadoOptions[2]]);
  const resultadoOptions = [
    bi(locale, 'favor usuario', 'favor user'),
    bi(locale, 'favor entidad', 'favor bank'),
    bi(locale, 'parcial', 'partial'),
  ];

  const filtered = useMemo(() => {
    return rows.filter((r) => {
      if (fMotivo.size && !fMotivo.has(r.motivo_code)) return false;
      if (fSubmotivo.size && !(r.submotivo && fSubmotivo.has(r.submotivo))) return false;
      if (fTopic.size && !(r.topic && fTopic.has(r.topic))) return false;
      if (fInst.size) {
        const v = scope === 'group' ? r.cohort_id : r.institution_id;
        if (!v || !fInst.has(v)) return false;
      }
      if (fEstado.size) {
        // Endpoint exposes resolved (atendido) vs pending only; en_proceso disabled.
        const wantAtendido = fEstado.has(estadoOptions[0]);
        const wantPendiente = fEstado.has(estadoOptions[1]);
        const ok = (wantAtendido && r.n_resolved > 0) || (wantPendiente && r.n_pending > 0);
        if (!ok) return false;
      }
      if (fResultado.size) {
        const ok =
          (fResultado.has(resultadoOptions[0]) && r.n_favor_user > 0) ||
          (fResultado.has(resultadoOptions[1]) && r.n_favor_bank > 0) ||
          (fResultado.has(resultadoOptions[2]) && r.n_favor_partial > 0);
        if (!ok) return false;
      }
      return true;
    });
  }, [rows, fMotivo, fSubmotivo, fTopic, fInst, fEstado, fResultado, scope, estadoOptions, resultadoOptions]);

  const sorted = useMemo(() => {
    const dir = sortDir === 'desc' ? -1 : 1;
    return [...filtered].sort((a, b) => {
      const av = accessor(sortKey, a);
      const bv = accessor(sortKey, b);
      if (av == null && bv == null) return 0;
      if (av == null) return 1; // nulls always last
      if (bv == null) return -1;
      if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir;
      return String(av).localeCompare(String(bv)) * dir;
    });
  }, [filtered, sortKey, sortDir]);

  const activeFilters =
    fMotivo.size + fSubmotivo.size + fTopic.size + fEstado.size + fResultado.size + fInst.size;

  // Pagination (client-side). safePage guards a stale page after filtering.
  const totalRows = sorted.length;
  const totalPages = Math.max(1, Math.ceil(totalRows / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pageRows = sorted.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);
  const firstIdx = totalRows === 0 ? 0 : (safePage - 1) * PAGE_SIZE + 1;
  const lastIdx = Math.min(safePage * PAGE_SIZE, totalRows);

  // Entity column label: real name (entity) / cohort (group), masked on demand.
  const entityLabel = (r: PatternRow): string => {
    if (scope === 'group') return r.cohort_id ?? '—';
    const id = r.institution_id ?? '';
    return anonymize ? maskEntity(id) : r.institution_name ?? id;
  };

  const toggle = (set: Set<string>, setter: (s: Set<string>) => void, v: string) => {
    const next = new Set(set);
    next.has(v) ? next.delete(v) : next.add(v);
    setter(next);
  };
  const clearAll = () => {
    setFMotivo(new Set());
    setFSubmotivo(new Set());
    setFTopic(new Set());
    setFEstado(new Set());
    setFResultado(new Set());
    setFInst(new Set());
  };

  const setSort = (k: SortKey) => {
    if (k === sortKey) setSortDir((d) => (d === 'desc' ? 'asc' : 'desc'));
    else {
      setSortKey(k);
      setSortDir(typeof accessor(k, rows[0] ?? ({} as PatternRow)) === 'number' ? 'desc' : 'asc');
    }
  };

  const SortHead = ({ k, label, numeric }: { k: SortKey; label: string; numeric?: boolean }) => (
    <TableHead className={numeric ? 'text-right' : ''}>
      <button
        type="button"
        onClick={() => setSort(k)}
        className={cn('inline-flex items-center gap-1 hover:text-brand-navy', numeric && 'flex-row-reverse')}
      >
        {label}
        {sortKey === k ? (
          sortDir === 'desc' ? <ArrowDown className="h-3 w-3" /> : <ArrowUp className="h-3 w-3" />
        ) : null}
      </button>
    </TableHead>
  );

  const showInst = scope !== 'all';
  const instHeader = scope === 'group' ? bi(locale, 'Cohorte', 'Cohort') : bi(locale, 'Entidad', 'Entity');

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-brand-navy">
            {bi(locale, 'Agregados de reclamos por motivo', 'Complaint aggregates by motive')}
          </h2>
          <p className="text-2xs italic text-fg-muted">
            {loading
              ? bi(locale, 'Cargando datos reales…', 'Loading real data…')
              : errored
                ? bi(locale, 'Datos no disponibles (endpoint).', 'Data unavailable (endpoint).')
                : bi(
                    locale,
                    `Datos reales · ${total} reclamos en alcance · SQL en vivo`,
                    `Real data · ${total} complaints in scope · live SQL`,
                  )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setAnonymize((a) => !a)}
            aria-pressed={anonymize}
            title={bi(locale, 'Oculta los nombres de las entidades', 'Masks entity names')}
            className={cn(
              'flex items-center gap-1 rounded-sbs border px-2.5 py-1 text-xs font-medium',
              anonymize
                ? 'border-brand-navy bg-brand-navy text-fg-inverted'
                : 'border-border bg-surface text-fg hover:bg-surface-subtle',
            )}
          >
            {anonymize ? <EyeOff className="h-3.5 w-3.5" aria-hidden="true" /> : <Eye className="h-3.5 w-3.5" aria-hidden="true" />}
            {bi(locale, 'Anonimizar nombres', 'Anonymize names')}
          </button>
          <button
            type="button"
            onClick={load}
            className="flex items-center gap-1 rounded-sbs border border-border bg-surface px-2.5 py-1 text-xs hover:bg-surface-subtle"
          >
            <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} aria-hidden="true" />
            {bi(locale, 'Actualizar', 'Refresh')}
          </button>
        </div>
      </div>

      {/* A — scope tabs */}
      <div className="flex gap-1 border-b border-border">
        {SCOPE_TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setScope(t.id)}
            className={cn(
              'rounded-t-sbs border-b-2 px-3 py-1.5 text-sm font-medium transition-colors',
              scope === t.id
                ? 'border-brand-cyan text-brand-navy'
                : 'border-transparent text-fg-muted hover:text-fg',
            )}
          >
            {bi(locale, t.es, t.en)}
          </button>
        ))}
      </div>

      {/* C — filters */}
      <div className="flex flex-wrap items-center gap-2 rounded-sbs border border-border bg-surface-subtle/50 p-2">
        <span className="flex items-center gap-1 text-2xs font-medium uppercase tracking-wide text-fg-subtle">
          <Filter className="h-3 w-3" aria-hidden="true" />
          {bi(locale, 'Filtros', 'Filters')}
        </span>
        <MultiSelect label={bi(locale, 'Motivo', 'Motive')} options={opt.motivo} selected={fMotivo} onToggle={(v) => toggle(fMotivo, setFMotivo, v)} />
        <MultiSelect label={bi(locale, 'Submotivo', 'Submotive')} options={opt.submotivo} selected={fSubmotivo} onToggle={(v) => toggle(fSubmotivo, setFSubmotivo, v)} />
        <MultiSelect label={bi(locale, 'Topic', 'Topic')} options={opt.topic} selected={fTopic} onToggle={(v) => toggle(fTopic, setFTopic, v)} />
        <MultiSelect label={bi(locale, 'Estado', 'Status')} options={estadoOptions} selected={fEstado} onToggle={(v) => toggle(fEstado, setFEstado, v)} disabled={estadoDisabled} />
        <MultiSelect label={bi(locale, 'Resultado', 'Outcome')} options={resultadoOptions} selected={fResultado} onToggle={(v) => toggle(fResultado, setFResultado, v)} />
        {showInst ? (
          <MultiSelect label={instHeader} options={opt.inst} selected={fInst} onToggle={(v) => toggle(fInst, setFInst, v)} />
        ) : null}
        {activeFilters > 0 ? (
          <button
            type="button"
            onClick={clearAll}
            className="ml-auto flex items-center gap-1 rounded-sbs border border-border bg-surface px-2 py-1 text-2xs text-fg-muted hover:text-fg"
          >
            <X className="h-3 w-3" aria-hidden="true" />
            {bi(locale, `Limpiar (${activeFilters})`, `Clear (${activeFilters})`)}
          </button>
        ) : null}
      </div>

      {/* B — main table */}
      <Table>
        <TableHeader>
          <TableRow>
            {showInst ? <SortHead k="inst" label={instHeader} /> : null}
            <SortHead k="motivo_code" label={bi(locale, 'Motivo', 'Motive')} />
            <SortHead k="submotivo" label={bi(locale, 'Submotivo', 'Submotive')} />
            <SortHead k="submotivo_2" label={bi(locale, 'Submotivo 2', 'Submotive 2')} />
            <SortHead k="topic" label={bi(locale, 'Topic / Tendencia', 'Topic / Trend')} />
            <SortHead k="n_complaints" label={bi(locale, 'N° reclamos', 'N° complaints')} numeric />
            <SortHead k="pct_of_all" label={bi(locale, '% del total', '% of total')} numeric />
            <SortHead k="pct_favor_user" label={bi(locale, '% favor usuario', '% favor user')} numeric />
            <SortHead k="pct_favor_bank" label={bi(locale, '% favor entidad', '% favor bank')} numeric />
            <SortHead k="pct_partial" label={bi(locale, '% parcial', '% partial')} numeric />
            <SortHead k="pct_pending" label={bi(locale, '% pendiente', '% pending')} numeric />
            <TableHead className="text-right">{bi(locale, 'Acción', 'Action')}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {pageRows.map((r, i) => (
            <TableRow key={`${r.institution_id ?? r.cohort_id ?? 'all'}-${r.motivo_code}-${r.submotivo}-${r.topic}-${i}`}>
              {showInst ? (
                <TableCell className="max-w-[200px] truncate text-2xs text-fg" title={entityLabel(r)}>
                  {entityLabel(r)}
                </TableCell>
              ) : null}
              <TableCell className="text-xs">{r.motivo_code}</TableCell>
              <TableCell className="text-xs text-fg-muted">{r.submotivo ?? '—'}</TableCell>
              <TableCell className="max-w-[280px] truncate text-xs text-fg-muted" title={r.submotivo_2 ?? undefined}>
                {r.submotivo_2 ?? '—'}
              </TableCell>
              <TableCell className="text-xs">{r.topic ?? '—'}</TableCell>
              <TableCell className={COL_NUM}>{r.n_complaints}</TableCell>
              <TableCell className={cn(COL_NUM, 'text-fg-muted')}>{fmtPct(r.pct_of_all)}</TableCell>
              <TableCell className={COL_USER}>{fmtPct(r.pct_favor_user)}</TableCell>
              <TableCell className={COL_BANK}>{fmtPct(r.pct_favor_bank)}</TableCell>
              <TableCell className={COL_PARTIAL}>{fmtPct(r.pct_partial)}</TableCell>
              <TableCell className={COL_PENDING}>{fmtPct(pendingPct(r))}</TableCell>
              <TableCell className="text-right">
                <Sheet>
                  <SheetTrigger asChild>
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 rounded-sbs border border-border bg-surface px-2 py-0.5 text-2xs text-brand-navy hover:border-brand-cyan"
                    >
                      {bi(locale, 'Ver reclamos', 'View complaints')}
                    </button>
                  </SheetTrigger>
                  <SheetContent closeLabel={bi(locale, 'Cerrar', 'Close')} className="overflow-y-auto">
                    <SheetTitle>
                      {r.motivo_code}
                      {r.submotivo ? ` · ${r.submotivo}` : ''}
                      {showInst ? ` · ${entityLabel(r)}` : ''}
                    </SheetTitle>
                    <p className="mt-0.5 font-mono text-2xs text-fg-subtle">
                      {r.topic ?? '—'}
                      {r.submotivo_2 ? ` · ${r.submotivo_2}` : ''}
                    </p>
                    <p className="mt-2 text-xs text-fg-muted">
                      {bi(
                        locale,
                        `${r.n_complaints} reclamos en este grupo${(r.complaint_ids?.length ?? 0) < r.n_complaints ? ` (mostrando ${r.complaint_ids?.length ?? 0})` : ''}. Clic para abrir el detalle.`,
                        `${r.n_complaints} complaints in this group${(r.complaint_ids?.length ?? 0) < r.n_complaints ? ` (showing ${r.complaint_ids?.length ?? 0})` : ''}. Click to open the detail.`,
                      )}
                    </p>
                    <ul className="mt-2 flex flex-wrap gap-1.5">
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
                  </SheetContent>
                </Sheet>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {totalRows === 0 ? (
        <p className="py-4 text-center text-xs text-fg-muted">
          {loading ? bi(locale, 'Cargando…', 'Loading…') : bi(locale, 'Sin filas para los filtros actuales.', 'No rows for the current filters.')}
        </p>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="font-mono text-2xs tabular-nums text-fg-muted">
            {bi(locale, `${firstIdx}–${lastIdx} de ${totalRows}`, `${firstIdx}–${lastIdx} of ${totalRows}`)}
          </span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={safePage <= 1}
              className="flex items-center gap-0.5 rounded-sbs border border-border bg-surface px-2 py-1 text-2xs disabled:opacity-40"
            >
              <ChevronLeft className="h-3 w-3" aria-hidden="true" />
              {bi(locale, 'Anterior', 'Prev')}
            </button>
            {Array.from({ length: totalPages }, (_, i) => i + 1)
              .filter((p) => p === 1 || p === totalPages || Math.abs(p - safePage) <= 1)
              .reduce<(number | '…')[]>((acc, p) => {
                const prev = acc[acc.length - 1];
                if (typeof prev === 'number' && p - prev > 1) acc.push('…');
                acc.push(p);
                return acc;
              }, [])
              .map((p, idx) =>
                p === '…' ? (
                  <span key={`gap-${idx}`} className="px-1 text-2xs text-fg-subtle">…</span>
                ) : (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setPage(p)}
                    aria-current={p === safePage}
                    className={cn(
                      'min-w-[1.75rem] rounded-sbs border px-2 py-1 text-2xs font-mono tabular-nums',
                      p === safePage
                        ? 'border-brand-navy bg-brand-navy text-fg-inverted'
                        : 'border-border bg-surface text-fg hover:bg-surface-subtle',
                    )}
                  >
                    {p}
                  </button>
                ),
              )}
            <button
              type="button"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={safePage >= totalPages}
              className="flex items-center gap-0.5 rounded-sbs border border-border bg-surface px-2 py-1 text-2xs disabled:opacity-40"
            >
              {bi(locale, 'Siguiente', 'Next')}
              <ChevronRight className="h-3 w-3" aria-hidden="true" />
            </button>
          </div>
        </div>
      )}
      <p className="text-2xs italic text-fg-subtle">
        {bi(
          locale,
          'Filtros aplicados en cliente sobre las filas devueltas. % favor sobre reclamos resueltos; "—" = sin resueltos. El endpoint agrega por resultado: "en proceso" no se separa de "pendiente".',
          'Filters applied client-side over returned rows. Favour % over resolved complaints; "—" = none resolved. The endpoint aggregates by outcome: "in progress" is not separable from "pending".',
        )}
      </p>

      {/* D — source tables */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        {/* Social — REAL (no badge) */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-sm">{bi(locale, 'Tendencias en redes sociales (Lupaman)', 'Social-media trends (Lupaman)')}</CardTitle>
            {social && !social.available ? <SampleBadge locale={locale} /> : null}
          </CardHeader>
          <CardBody>
            {social && social.available ? (
              <>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{bi(locale, 'Indicador', 'Indicator')}</TableHead>
                      <TableHead className="text-right">{bi(locale, 'Menciones (7d)', 'Mentions (7d)')}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {Object.entries(social.fraud_indicator_counts_7d ?? {})
                      .sort((a, b) => b[1] - a[1])
                      .map(([k, v]) => (
                        <TableRow key={k}>
                          <TableCell className="text-xs">{FRAUD_LABEL_ES[k] ?? k}</TableCell>
                          <TableCell className="text-right font-mono tabular-nums">{v}</TableCell>
                        </TableRow>
                      ))}
                  </TableBody>
                </Table>
                <p className="mt-2 text-2xs text-fg-subtle">
                  {bi(
                    locale,
                    `Total 7d: ${social.total_signals_7d ?? 0} · fuentes: ${Object.keys(social.signal_count_24h_by_source ?? {}).join(', ') || '—'}. Tema e institución se omiten por el contrato de PII.`,
                    `7d total: ${social.total_signals_7d ?? 0} · sources: ${Object.keys(social.signal_count_24h_by_source ?? {}).join(', ') || '—'}. Topic/institution suppressed by the PII contract.`,
                  )}
                </p>
              </>
            ) : social == null ? (
              <p className="py-3 text-2xs text-fg-muted">{bi(locale, 'Cargando…', 'Loading…')}</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{bi(locale, 'Tendencia', 'Trend')}</TableHead>
                    <TableHead className="text-right">{bi(locale, 'Menciones', 'Mentions')}</TableHead>
                    <TableHead className="text-right">{bi(locale, 'Instituciones', 'Institutions')}</TableHead>
                    <TableHead>{bi(locale, 'Indicador', 'Indicator')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {SOCIAL_SAMPLE.map((r) => (
                    <TableRow key={r.tendencia}>
                      <TableCell className="text-xs">{r.tendencia}</TableCell>
                      <TableCell className="text-right font-mono tabular-nums">{r.menciones}</TableCell>
                      <TableCell className="text-right font-mono tabular-nums">{r.instituciones}</TableCell>
                      <TableCell className="text-2xs text-fg-muted">{r.indicador}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardBody>
        </Card>

        {/* INDECOPI — SAMPLE */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-sm">{bi(locale, 'Casos INDECOPI', 'INDECOPI cases')}</CardTitle>
            <SampleBadge locale={locale} />
          </CardHeader>
          <CardBody>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{bi(locale, 'Categoría', 'Category')}</TableHead>
                  <TableHead>{bi(locale, 'Institución', 'Institution')}</TableHead>
                  <TableHead className="text-right">{bi(locale, 'Casos', 'Cases')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {INDECOPI_SAMPLE.map((r) => (
                  <TableRow key={`${r.categoria}-${r.institucion}`}>
                    <TableCell className="text-xs">{r.categoria}</TableCell>
                    <TableCell className="font-mono text-2xs text-fg-muted">{r.institucion}</TableCell>
                    <TableCell className="text-right font-mono tabular-nums">{r.casos}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardBody>
        </Card>

        {/* SBS DSC — SAMPLE */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-sm">{bi(locale, 'SBS DSC — Atención al Ciudadano', 'SBS DSC — Citizen assistance')}</CardTitle>
            <SampleBadge locale={locale} />
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
