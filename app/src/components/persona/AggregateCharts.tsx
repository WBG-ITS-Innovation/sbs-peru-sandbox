/* eslint-disable i18next/no-literal-string */
'use client';

import { useMemo, useState } from 'react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as RTooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { Card } from '@/components/ui';
import type { Locale } from '@/i18n';
import { bi } from '@/lib/bi';

// Cross-filtered chart row above the Tablas table. Every series is computed
// from the CURRENT scoped+filtered rows (passed in) — except the monthly,
// product, channel and outcome-over-time charts, which read the global /trend
// endpoint (time/product/channel are not dimensions of the aggregate rows);
// those are labelled accordingly. The "Construir gráfico" builder also runs
// over the filtered rows, so it stays in sync with the table and filters.

const NAVY = '#002244';
const CYAN = '#009FDA';
const GOLD = '#F5BD24';
const GREEN = '#15803d';
const RED = '#b91c1c';
const GRAY = '#94a3b8';

interface Row {
  motivo_code: string;
  submotivo?: string | null;
  topic?: string | null;
  institution_name?: string;
  cohort_id?: string;
  n_complaints: number;
  n_pending: number;
  n_favor_user: number;
  n_favor_bank: number;
  n_favor_partial: number;
}
interface MonthRow { month: string; complaints: number; social: number }
interface ProductRow { product_category: string; n_complaints: number }
interface ChannelRow { channel: string; n_complaints: number }
interface OutcomeMonthRow { month: string; user: number; bank: number; partial: number; pending: number }
interface Trend {
  by_month?: MonthRow[];
  by_product?: ProductRow[];
  by_channel?: ChannelRow[];
  by_outcome_month?: OutcomeMonthRow[];
  period?: { start: string | null; end: string | null } | null;
}

type Scope = 'entity' | 'group' | 'all';

function ChartCard({ title, children, note }: { title: string; children: React.ReactNode; note?: string }) {
  return (
    <Card className="p-2">
      <h3 className="mb-1 text-2xs font-semibold uppercase tracking-wide text-fg-subtle">{title}</h3>
      <div className="h-[200px] w-full">{children}</div>
      {note ? <p className="mt-1 text-2xs italic text-fg-subtle">{note}</p> : null}
    </Card>
  );
}

// ---- "Construir gráfico" builder ------------------------------------------
// A dropdown-driven chart over the filtered rows (real data). Pick a
// dimension, a metric, and a chart type. Not a full BI builder — three selects.

type BuilderDim = 'motivo' | 'entidad' | 'submotivo' | 'topic';
type BuilderMetric = 'count' | 'favor_user' | 'pending';
type BuilderChart = 'bar' | 'line';

function dimKey(r: Row, dim: BuilderDim, scope: Scope): string {
  switch (dim) {
    case 'motivo':
      return r.motivo_code;
    case 'entidad':
      return (scope === 'group' ? r.cohort_id : r.institution_name) ?? '—';
    case 'submotivo':
      return r.submotivo ?? '—';
    case 'topic':
      return r.topic ?? '—';
  }
}

function ChartBuilder({ locale, rows, scope }: { locale: Locale; rows: Row[]; scope: Scope }) {
  const [dim, setDim] = useState<BuilderDim>('motivo');
  const [metric, setMetric] = useState<BuilderMetric>('count');
  const [chart, setChart] = useState<BuilderChart>('bar');

  // Entidad becomes "cohorte" under group scope; hide it under all scope
  // (no institution dimension there) by falling back to motivo.
  const effectiveDim: BuilderDim = scope === 'all' && dim === 'entidad' ? 'motivo' : dim;

  const data = useMemo(() => {
    const acc = new Map<string, { n: number; pending: number; user: number; bank: number; partial: number }>();
    for (const r of rows) {
      const k = dimKey(r, effectiveDim, scope);
      const e = acc.get(k) ?? { n: 0, pending: 0, user: 0, bank: 0, partial: 0 };
      e.n += r.n_complaints;
      e.pending += r.n_pending;
      e.user += r.n_favor_user;
      e.bank += r.n_favor_bank;
      e.partial += r.n_favor_partial;
      acc.set(k, e);
    }
    const out = [...acc.entries()].map(([key, v]) => {
      const resolved = v.user + v.bank + v.partial;
      const value =
        metric === 'count'
          ? v.n
          : metric === 'favor_user'
            ? (resolved > 0 ? Math.round((1000 * v.user) / resolved) / 10 : 0)
            : (v.n > 0 ? Math.round((1000 * v.pending) / v.n) / 10 : 0);
      return { key, value };
    });
    out.sort((a, b) => b.value - a.value);
    return out.slice(0, 12);
  }, [rows, effectiveDim, scope, metric]);

  const metricLabel =
    metric === 'count'
      ? bi(locale, 'Conteo', 'Count')
      : metric === 'favor_user'
        ? bi(locale, '% favor usuario', '% favor user')
        : bi(locale, '% pendiente', '% pending');
  const isPct = metric !== 'count';

  const dimOpts: { id: BuilderDim; label: string }[] = [
    { id: 'motivo', label: bi(locale, 'Motivo', 'Motive') },
    { id: 'entidad', label: scope === 'group' ? bi(locale, 'Cohorte', 'Cohort') : bi(locale, 'Entidad', 'Institution') },
    { id: 'submotivo', label: bi(locale, 'Submotivo', 'Submotive') },
    { id: 'topic', label: bi(locale, 'Topic', 'Topic') },
  ];

  const Select = <T extends string>({ value, onChange, opts }: { value: T; onChange: (v: T) => void; opts: { id: T; label: string }[] }) => (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as T)}
      className="rounded-sbs border border-border bg-surface px-2 py-1 text-xs text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
    >
      {opts.map((o) => (
        <option key={o.id} value={o.id}>{o.label}</option>
      ))}
    </select>
  );

  return (
    <Card className="border-brand-cyan/40 p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <h3 className="mr-1 text-sm font-semibold text-brand-navy">{bi(locale, 'Construir gráfico', 'Build a chart')}</h3>
        <span className="text-2xs text-fg-subtle">{bi(locale, 'Dimensión', 'Dimension')}</span>
        <Select value={effectiveDim} onChange={setDim} opts={scope === 'all' ? dimOpts.filter((o) => o.id !== 'entidad') : dimOpts} />
        <span className="text-2xs text-fg-subtle">{bi(locale, 'Métrica', 'Metric')}</span>
        <Select
          value={metric}
          onChange={setMetric}
          opts={[
            { id: 'count', label: bi(locale, 'Conteo', 'Count') },
            { id: 'favor_user', label: bi(locale, '% favor usuario', '% favor user') },
            { id: 'pending', label: bi(locale, '% pendiente', '% pending') },
          ]}
        />
        <span className="text-2xs text-fg-subtle">{bi(locale, 'Tipo', 'Type')}</span>
        <Select
          value={chart}
          onChange={setChart}
          opts={[
            { id: 'bar', label: bi(locale, 'Barras', 'Bars') },
            { id: 'line', label: bi(locale, 'Línea', 'Line') },
          ]}
        />
      </div>
      <div className="h-[240px] w-full">
        {data.length === 0 ? (
          <p className="py-8 text-center text-xs text-fg-muted">{bi(locale, 'Sin datos para los filtros actuales.', 'No data for the current filters.')}</p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            {chart === 'line' ? (
              <LineChart data={data} margin={{ top: 4, right: 16, bottom: 40, left: -8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="key" tick={{ fontSize: 8, angle: -25, textAnchor: 'end' }} interval={0} height={60} />
                <YAxis tick={{ fontSize: 9 }} width={34} unit={isPct ? '%' : undefined} />
                <RTooltip formatter={(v) => [isPct ? `${v}%` : v, metricLabel]} />
                <Line type="monotone" dataKey="value" name={metricLabel} stroke={NAVY} strokeWidth={2} dot={{ r: 2 }} />
              </LineChart>
            ) : (
              <BarChart data={data} layout="vertical" margin={{ top: 2, right: 16, bottom: 0, left: 6 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 9 }} unit={isPct ? '%' : undefined} />
                <YAxis type="category" dataKey="key" tick={{ fontSize: 8 }} width={140} />
                <RTooltip formatter={(v) => [isPct ? `${v}%` : v, metricLabel]} />
                <Bar dataKey="value" name={metricLabel} radius={[0, 2, 2, 0]} fill={CYAN} />
              </BarChart>
            )}
          </ResponsiveContainer>
        )}
      </div>
      <p className="mt-1 text-2xs italic text-fg-subtle">
        {bi(locale, 'Calculado sobre las filas filtradas (datos reales).', 'Computed over the filtered rows (real data).')}
      </p>
    </Card>
  );
}

export function AggregateCharts({
  locale,
  rows,
  scope,
  trend,
  selectedMotivos,
  onToggleMotivo,
}: {
  locale: Locale;
  rows: Row[];
  scope: Scope;
  trend: Trend | null;
  selectedMotivos: Set<string>;
  onToggleMotivo: (m: string) => void;
}) {
  const byMotivo = useMemo(() => {
    const m = new Map<string, number>();
    for (const r of rows) m.set(r.motivo_code, (m.get(r.motivo_code) ?? 0) + r.n_complaints);
    return [...m.entries()].map(([motivo_code, n]) => ({ motivo_code, n })).sort((a, b) => b.n - a.n);
  }, [rows]);

  const outcomeByMotivo = useMemo(() => {
    const m = new Map<string, { motivo_code: string; user: number; bank: number; partial: number; pending: number }>();
    for (const r of rows) {
      const e = m.get(r.motivo_code) ?? { motivo_code: r.motivo_code, user: 0, bank: 0, partial: 0, pending: 0 };
      e.user += r.n_favor_user; e.bank += r.n_favor_bank; e.partial += r.n_favor_partial; e.pending += r.n_pending;
      m.set(r.motivo_code, e);
    }
    return [...m.values()].sort((a, b) => (b.user + b.bank + b.partial + b.pending) - (a.user + a.bank + a.partial + a.pending)).slice(0, 6);
  }, [rows]);

  const byInst = useMemo(() => {
    const key = (r: Row) => (scope === 'group' ? r.cohort_id : scope === 'all' ? r.motivo_code : r.institution_name) ?? '—';
    const m = new Map<string, number>();
    for (const r of rows) m.set(key(r), (m.get(key(r)) ?? 0) + r.n_complaints);
    return [...m.entries()].map(([name, n]) => ({ name, n })).sort((a, b) => b.n - a.n).slice(0, 8);
  }, [rows, scope]);

  const topMotivo = byMotivo[0]?.motivo_code ?? null;
  const byMonth = trend?.by_month ?? [];
  const byProduct = trend?.by_product ?? [];
  const byChannel = trend?.by_channel ?? [];
  const byOutcomeMonth = trend?.by_outcome_month ?? [];
  const periodLabel = trend?.period?.start && trend?.period?.end
    ? `${trend.period.start} → ${trend.period.end}`
    : bi(locale, 'periodo único', 'single period');
  const instTitle = scope === 'group' ? bi(locale, 'Top cohortes por volumen', 'Top cohorts by volume') : scope === 'all' ? bi(locale, 'Top motivos por volumen', 'Top motives by volume') : bi(locale, 'Top entidades por volumen', 'Top institutions by volume');

  return (
    <div className="space-y-2">
      <ChartBuilder locale={locale} rows={rows} scope={scope} />

      <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
        {/* 1. Motivo distribution — click to filter */}
        <ChartCard title={bi(locale, 'Distribución por motivo (clic = filtrar)', 'Motive distribution (click = filter)')}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={byMotivo} layout="vertical" margin={{ top: 2, right: 12, bottom: 0, left: 6 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 9 }} />
              <YAxis type="category" dataKey="motivo_code" tick={{ fontSize: 8 }} width={120} />
              <RTooltip cursor={{ fill: 'rgba(0,159,218,0.06)' }} />
              <Bar
                dataKey="n"
                radius={[0, 2, 2, 0]}
                cursor="pointer"
                background={{ fill: 'rgba(148,163,184,0.10)', radius: 2 }}
                onClick={(d: { motivo_code?: string; payload?: { motivo_code?: string } }) => {
                  const code = d?.payload?.motivo_code ?? d?.motivo_code;
                  if (code) onToggleMotivo(code);
                }}
              >
                {byMotivo.map((d) => (
                  <Cell
                    key={d.motivo_code}
                    fill={selectedMotivos.has(d.motivo_code) ? GOLD : d.motivo_code === topMotivo ? CYAN : NAVY}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* 2. Monthly volume + social overlay (global) */}
        <ChartCard
          title={bi(locale, 'Volumen mensual + señales sociales', 'Monthly volume + social signals')}
          note={bi(locale, 'Global (la serie temporal no se filtra por alcance). Línea punteada: social_signals (real).', 'Global (time series is not scope-filtered). Dashed: social_signals (real).')}
        >
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={byMonth} margin={{ top: 2, right: 12, bottom: 0, left: -16 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="month" tick={{ fontSize: 8 }} />
              <YAxis tick={{ fontSize: 9 }} width={28} />
              <RTooltip />
              <Legend wrapperStyle={{ fontSize: 9 }} />
              <Line type="monotone" dataKey="complaints" name={bi(locale, 'Reclamos', 'Complaints')} stroke={NAVY} strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="social" name={bi(locale, 'Social', 'Social')} stroke={GOLD} strokeWidth={2} strokeDasharray="5 4" dot={{ r: 2 }} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* 3. Outcome split stacked (per top motivo) */}
        <ChartCard title={bi(locale, 'Resultado por motivo (usuario/entidad/parcial/pendiente)', 'Outcome by motive (user/bank/partial/pending)')}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={outcomeByMotivo} layout="vertical" margin={{ top: 2, right: 12, bottom: 0, left: 6 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 9 }} />
              <YAxis type="category" dataKey="motivo_code" tick={{ fontSize: 8 }} width={120} />
              <RTooltip />
              <Legend wrapperStyle={{ fontSize: 9 }} />
              <Bar dataKey="user" name={bi(locale, 'Usuario', 'User')} stackId="o" fill={GREEN} />
              <Bar dataKey="bank" name={bi(locale, 'Entidad', 'Bank')} stackId="o" fill={RED} />
              <Bar dataKey="partial" name={bi(locale, 'Parcial', 'Partial')} stackId="o" fill={GRAY} />
              <Bar dataKey="pending" name={bi(locale, 'Pendiente', 'Pending')} stackId="o" fill={GOLD} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* 4. Top institutions/cohorts by volume */}
        <ChartCard title={instTitle}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={byInst} layout="vertical" margin={{ top: 2, right: 12, bottom: 0, left: 6 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 9 }} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 8 }} width={120} />
              <RTooltip />
              <Bar dataKey="n" radius={[0, 2, 2, 0]}>
                {byInst.map((d, i) => (
                  <Cell key={d.name} fill={i === 0 ? CYAN : NAVY} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* 5. Productos by period (global) */}
        <ChartCard
          title={bi(locale, 'Reclamos por producto', 'Complaints by product')}
          note={bi(locale, `Periodo: ${periodLabel} (un solo periodo en los datos).`, `Period: ${periodLabel} (single period in the data).`)}
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={byProduct} layout="vertical" margin={{ top: 2, right: 12, bottom: 0, left: 6 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 9 }} />
              <YAxis type="category" dataKey="product_category" tick={{ fontSize: 8 }} width={120} />
              <RTooltip />
              <Bar dataKey="n_complaints" radius={[0, 2, 2, 0]} fill={NAVY} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* 6. By channel (global) */}
        <ChartCard
          title={bi(locale, 'Reclamos por canal', 'Complaints by channel')}
          note={bi(locale, 'Global (canal de recepción del reclamo).', 'Global (complaint reception channel).')}
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={byChannel} layout="vertical" margin={{ top: 2, right: 12, bottom: 0, left: 6 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 9 }} />
              <YAxis type="category" dataKey="channel" tick={{ fontSize: 8 }} width={120} />
              <RTooltip />
              <Bar dataKey="n_complaints" radius={[0, 2, 2, 0]} fill={CYAN} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* 7. Outcome over time (global, stacked area) */}
        <ChartCard
          title={bi(locale, 'Resultado en el tiempo', 'Outcome over time')}
          note={bi(locale, 'Global · resoluciones por mes (usuario/entidad/parcial/pendiente).', 'Global · resolutions per month (user/bank/partial/pending).')}
        >
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={byOutcomeMonth} margin={{ top: 2, right: 12, bottom: 0, left: -16 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="month" tick={{ fontSize: 8 }} />
              <YAxis tick={{ fontSize: 9 }} width={28} />
              <RTooltip />
              <Legend wrapperStyle={{ fontSize: 9 }} />
              <Area type="monotone" dataKey="user" name={bi(locale, 'Usuario', 'User')} stackId="t" stroke={GREEN} fill={GREEN} fillOpacity={0.7} />
              <Area type="monotone" dataKey="bank" name={bi(locale, 'Entidad', 'Bank')} stackId="t" stroke={RED} fill={RED} fillOpacity={0.7} />
              <Area type="monotone" dataKey="partial" name={bi(locale, 'Parcial', 'Partial')} stackId="t" stroke={GRAY} fill={GRAY} fillOpacity={0.7} />
              <Area type="monotone" dataKey="pending" name={bi(locale, 'Pendiente', 'Pending')} stackId="t" stroke={GOLD} fill={GOLD} fillOpacity={0.7} />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
    </div>
  );
}
