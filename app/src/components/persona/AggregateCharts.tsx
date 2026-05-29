/* eslint-disable i18next/no-literal-string */
'use client';

import { useMemo } from 'react';
import {
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
// from the CURRENT scoped+filtered rows (passed in) — except the monthly and
// product charts, which read the global /trend endpoint (time/product are not
// dimensions of the aggregate rows); those are labelled accordingly.

const NAVY = '#002244';
const CYAN = '#009FDA';
const GOLD = '#F5BD24';
const GREEN = '#15803d';
const RED = '#b91c1c';
const GRAY = '#94a3b8';

interface Row {
  motivo_code: string;
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
interface Trend { by_month?: MonthRow[]; by_product?: ProductRow[]; period?: { start: string | null; end: string | null } | null }

function ChartCard({ title, children, note }: { title: string; children: React.ReactNode; note?: string }) {
  return (
    <Card className="p-2">
      <h3 className="mb-1 text-2xs font-semibold uppercase tracking-wide text-fg-subtle">{title}</h3>
      <div className="h-[200px] w-full">{children}</div>
      {note ? <p className="mt-1 text-2xs italic text-fg-subtle">{note}</p> : null}
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
  scope: 'entity' | 'group' | 'all';
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
  const periodLabel = trend?.period?.start && trend?.period?.end
    ? `${trend.period.start} → ${trend.period.end}`
    : bi(locale, 'periodo único', 'single period');
  const instTitle = scope === 'group' ? bi(locale, 'Top cohortes por volumen', 'Top cohorts by volume') : scope === 'all' ? bi(locale, 'Top motivos por volumen', 'Top motives by volume') : bi(locale, 'Top entidades por volumen', 'Top institutions by volume');

  return (
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
    </div>
  );
}
