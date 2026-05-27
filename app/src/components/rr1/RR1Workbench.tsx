// RR1 SUCAVE-style workbench.
//
// Tabs across the three workbook sheets (Empresa, Producto, Motivo)
// rendered as scrollable tables, with conditional-formatting colour
// scales applied per cell. Beneath the table is a "Build your own
// chart" panel: pick rows from the active sheet, pick chart type
// (line / bar / heatmap / stacked area), and the visualization
// renders against the same 12 monthly columns.
//
// Heatmap is hand-rolled CSS-grid (Recharts has no native heatmap).
// All other types use Recharts already installed for the cockpit.
/* eslint-disable i18next/no-literal-string */

'use client';

import { useMemo, useState } from 'react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { ArrowUpDown, Filter } from 'lucide-react';

import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui';
import type { Locale } from '@/i18n';
import { cn } from '@/lib/cn';

interface SheetData {
  label_col: string;
  months: string[];
  rows: Array<{ label: string; values: Array<number | null>; total: number }>;
}

interface RR1Data {
  source: string;
  generated_at: string;
  sheets: Record<string, SheetData>;
}

interface Props {
  locale: Locale;
  data: RR1Data;
}

type SheetKey = 'Empresa' | 'Producto' | 'Motivo';
type ChartType = 'line' | 'bar' | 'heatmap' | 'area';

const NAVY = '#002244';
const CYAN = '#009FDA';
const GOLD = '#F5BD24';
const PIE = [CYAN, GOLD, NAVY, '#3B82F6', '#F97316', '#10B981', '#8B5CF6', '#EC4899'];

export function RR1Workbench({ locale, data }: Props) {
  const es = locale === 'es-PE';
  const [activeSheet, setActiveSheet] = useState<SheetKey>('Empresa');
  const [filter, setFilter] = useState('');
  const [sortDesc, setSortDesc] = useState(true);

  const sheet = data.sheets[activeSheet];

  // Top-N row IDs auto-selected for the chart so the page renders something
  // immediately on tab change.
  const sortedRows = useMemo(() => {
    const arr = [...sheet.rows];
    arr.sort((a, b) => (sortDesc ? b.total - a.total : a.total - b.total));
    return arr;
  }, [sheet.rows, sortDesc]);

  const visibleRows = useMemo(() => {
    if (!filter.trim()) return sortedRows;
    const f = filter.trim().toLowerCase();
    return sortedRows.filter((r) => r.label.toLowerCase().includes(f));
  }, [sortedRows, filter]);

  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(sortedRows.slice(0, 5).map((r) => r.label)),
  );
  const [chartType, setChartType] = useState<ChartType>('line');

  // Reset selection when tab changes.
  const handleTabChange = (k: SheetKey) => {
    if (k === activeSheet) return;
    setActiveSheet(k);
    setFilter('');
    const top5 = [...data.sheets[k].rows]
      .sort((a, b) => b.total - a.total)
      .slice(0, 5)
      .map((r) => r.label);
    setSelected(new Set(top5));
  };

  const toggle = (label: string) => {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  };

  // Build the data shape Recharts wants: one row per month with
  // numbered series for each selected label.
  const chartData = useMemo(() => {
    return sheet.months.map((m, mi) => {
      const obj: Record<string, string | number> = { month: m };
      for (const r of sheet.rows) {
        if (selected.has(r.label)) {
          obj[r.label] = r.values[mi] ?? 0;
        }
      }
      return obj;
    });
  }, [sheet, selected]);

  const maxVal = useMemo(() => {
    let m = 0;
    for (const r of sheet.rows) {
      if (selected.has(r.label)) {
        for (const v of r.values) {
          if (v !== null && v > m) m = v;
        }
      }
    }
    return m || 1;
  }, [sheet, selected]);

  // Conditional formatting in the table.
  const cellMax = useMemo(() => {
    let m = 0;
    for (const r of visibleRows) {
      for (const v of r.values) {
        if (v !== null && v > m) m = v;
      }
    }
    return m || 1;
  }, [visibleRows]);

  return (
    <div className="space-y-4">
      {/* Tabs */}
      <nav className="flex gap-1 border-b border-border">
        {(['Empresa', 'Producto', 'Motivo'] as const).map((k) => (
          <button
            key={k}
            type="button"
            onClick={() => handleTabChange(k)}
            className={cn(
              '-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors',
              activeSheet === k
                ? 'border-brand-cyan text-brand-navy'
                : 'border-transparent text-fg-muted hover:text-fg',
            )}
          >
            {es ? labelFor(k, 'es') : labelFor(k, 'en')}
            <span className="ml-2 font-mono text-2xs text-fg-muted">
              {data.sheets[k].rows.length}
            </span>
          </button>
        ))}
      </nav>

      {/* Table + filters */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between text-base">
            <span>{sheet.label_col || activeSheet}</span>
            <div className="flex items-center gap-2">
              <div className="relative">
                <Filter className="pointer-events-none absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-fg-muted" />
                <input
                  type="search"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  placeholder={es ? 'Filtrar…' : 'Filter…'}
                  className="h-8 w-44 rounded-sbs border border-border bg-surface pl-7 pr-2 text-xs focus:border-brand-cyan focus:outline-none"
                />
              </div>
              <button
                type="button"
                onClick={() => setSortDesc((s) => !s)}
                className="inline-flex h-8 items-center gap-1 rounded-sbs border border-border-strong bg-surface px-2 text-xs text-fg hover:bg-surface-subtle"
              >
                <ArrowUpDown className="h-3 w-3" />
                {sortDesc ? (es ? 'Mayor a menor' : 'Highest first') : es ? 'Menor a mayor' : 'Lowest first'}
              </button>
            </div>
          </CardTitle>
        </CardHeader>
        <CardBody>
          <div className="overflow-x-auto">
            <table className="w-full border-separate border-spacing-0 text-xs">
              <thead className="sticky top-0 bg-surface">
                <tr>
                  <th className="sticky left-0 z-10 border-b border-border bg-surface px-2 py-1.5 text-left font-mono uppercase tracking-wide text-fg-muted">
                    <input type="checkbox" disabled className="invisible" />
                  </th>
                  <th className="sticky left-6 z-10 border-b border-border bg-surface px-2 py-1.5 text-left font-mono uppercase tracking-wide text-fg-muted">
                    {sheet.label_col || activeSheet}
                  </th>
                  {sheet.months.map((m) => (
                    <th
                      key={m}
                      className="border-b border-border bg-surface px-2 py-1.5 text-right font-mono uppercase tracking-wide text-fg-muted"
                    >
                      {m}
                    </th>
                  ))}
                  <th className="border-b border-border bg-surface-subtle px-2 py-1.5 text-right font-mono uppercase tracking-wide text-brand-navy">
                    Total
                  </th>
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((r) => {
                  const isSelected = selected.has(r.label);
                  return (
                    <tr
                      key={r.label}
                      className={cn(
                        'transition-colors hover:bg-surface-subtle',
                        isSelected && 'bg-brand-cyan/5',
                      )}
                    >
                      <td className="sticky left-0 z-10 border-b border-border-subtle bg-inherit px-2 py-1.5">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggle(r.label)}
                          className="h-3.5 w-3.5"
                        />
                      </td>
                      <td className="sticky left-6 z-10 max-w-[220px] truncate border-b border-border-subtle bg-inherit px-2 py-1.5 font-medium text-fg" title={r.label}>
                        {r.label}
                      </td>
                      {r.values.map((v, vi) => (
                        <td
                          key={vi}
                          className="border-b border-border-subtle px-2 py-1.5 text-right font-mono tabular-nums"
                          style={
                            v
                              ? {
                                  backgroundColor: `rgba(0, 159, 218, ${Math.min(0.55, v / cellMax)})`,
                                  color: v / cellMax > 0.45 ? '#fff' : NAVY,
                                }
                              : undefined
                          }
                        >
                          {v != null ? v.toLocaleString() : '—'}
                        </td>
                      ))}
                      <td className="border-b border-border-subtle bg-surface-subtle px-2 py-1.5 text-right font-mono font-semibold tabular-nums text-brand-navy">
                        {r.total.toLocaleString()}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="mt-2 font-mono text-2xs text-fg-muted">
            {visibleRows.length} / {sheet.rows.length} {es ? 'filas' : 'rows'} ·{' '}
            {selected.size} {es ? 'seleccionadas para gráfico' : 'selected for chart'}
          </p>
        </CardBody>
      </Card>

      {/* Chart builder */}
      <Card className="border-brand-cyan/40">
        <CardHeader>
          <CardTitle className="text-base">
            {es ? 'Construye tu visualización' : 'Build your visualization'}
          </CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium text-fg-muted">
              {es ? 'Tipo de gráfico' : 'Chart type'}:
            </span>
            {(['line', 'bar', 'area', 'heatmap'] as ChartType[]).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setChartType(t)}
                className={cn(
                  'inline-flex h-8 items-center rounded-sbs border px-3 text-xs font-medium transition-colors',
                  chartType === t
                    ? 'border-brand-cyan bg-brand-cyan/10 text-brand-navy'
                    : 'border-border bg-surface text-fg hover:bg-surface-subtle',
                )}
              >
                {chartLabel(t, es)}
              </button>
            ))}
          </div>

          {selected.size === 0 ? (
            <p className="text-sm text-fg-muted">
              {es
                ? 'Marca al menos una fila en la tabla para verla en el gráfico.'
                : 'Tick at least one row in the table to chart it.'}
            </p>
          ) : (
            <div className="h-80">
              <RenderChart
                type={chartType}
                data={chartData}
                series={Array.from(selected)}
                months={sheet.months}
                maxVal={maxVal}
              />
            </div>
          )}

          <p className="text-2xs text-fg-muted">
            {es
              ? 'Datos reales del workbook RR1 2025. Cambia las filas seleccionadas o el tipo de gráfico para explorar.'
              : 'Real data from the RR1 2025 workbook. Change the selected rows or the chart type to explore.'}
          </p>
        </CardBody>
      </Card>
    </div>
  );
}

function labelFor(k: SheetKey, lang: 'es' | 'en'): string {
  const map: Record<SheetKey, { es: string; en: string }> = {
    Empresa: { es: 'Por entidad', en: 'By entity' },
    Producto: { es: 'Por producto', en: 'By product' },
    Motivo: { es: 'Por motivo', en: 'By motive' },
  };
  return map[k][lang];
}

function chartLabel(t: ChartType, es: boolean): string {
  if (t === 'line') return es ? 'Línea' : 'Line';
  if (t === 'bar') return es ? 'Barras' : 'Bars';
  if (t === 'area') return es ? 'Área apilada' : 'Stacked area';
  return es ? 'Mapa de calor' : 'Heatmap';
}

function RenderChart(props: {
  type: ChartType;
  data: Array<Record<string, string | number>>;
  series: string[];
  months: string[];
  maxVal: number;
}) {
  const { type, data, series, months, maxVal } = props;
  if (type === 'heatmap') {
    return <Heatmap data={data} series={series} months={months} max={maxVal} />;
  }
  if (type === 'bar') {
    return (
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: -8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
          <XAxis dataKey="month" tick={{ fontSize: 10, fill: '#6B7280' }} />
          <YAxis tick={{ fontSize: 10, fill: '#6B7280' }} allowDecimals={false} />
          <Tooltip contentStyle={{ fontSize: 12, borderRadius: 2 }} />
          <Legend wrapperStyle={{ fontSize: 10 }} />
          {series.map((s, i) => (
            <Bar key={s} dataKey={s} fill={PIE[i % PIE.length]} radius={[2, 2, 0, 0]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    );
  }
  if (type === 'area') {
    return (
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: -8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
          <XAxis dataKey="month" tick={{ fontSize: 10, fill: '#6B7280' }} />
          <YAxis tick={{ fontSize: 10, fill: '#6B7280' }} allowDecimals={false} />
          <Tooltip contentStyle={{ fontSize: 12, borderRadius: 2 }} />
          <Legend wrapperStyle={{ fontSize: 10 }} />
          {series.map((s, i) => (
            <Area
              key={s}
              type="monotone"
              dataKey={s}
              stackId="1"
              stroke={PIE[i % PIE.length]}
              fill={PIE[i % PIE.length]}
              fillOpacity={0.6}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    );
  }
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: -8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
        <XAxis dataKey="month" tick={{ fontSize: 10, fill: '#6B7280' }} />
        <YAxis tick={{ fontSize: 10, fill: '#6B7280' }} allowDecimals={false} />
        <Tooltip contentStyle={{ fontSize: 12, borderRadius: 2 }} />
        <Legend wrapperStyle={{ fontSize: 10 }} />
        {series.map((s, i) => (
          <Line
            key={s}
            type="monotone"
            dataKey={s}
            stroke={PIE[i % PIE.length]}
            strokeWidth={2}
            dot={{ r: 2 }}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

function Heatmap(props: {
  data: Array<Record<string, string | number>>;
  series: string[];
  months: string[];
  max: number;
}) {
  const { data, series, months, max } = props;
  return (
    <div className="h-full overflow-auto">
      <table className="w-full border-separate border-spacing-0.5 text-xs">
        <thead>
          <tr>
            <th className="sticky left-0 bg-surface px-2 py-1 text-left font-mono uppercase tracking-wide text-fg-muted">
              series
            </th>
            {months.map((m) => (
              <th key={m} className="px-2 py-1 text-center font-mono text-fg-muted">
                {m}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {series.map((s) => (
            <tr key={s}>
              <th className="sticky left-0 max-w-[220px] truncate bg-surface px-2 py-1 text-left text-fg" title={s}>
                {s}
              </th>
              {data.map((row, ri) => {
                const v = Number(row[s] || 0);
                const intensity = Math.min(1, v / max);
                return (
                  <td
                    key={ri}
                    className="rounded-sm px-2 py-1 text-center font-mono tabular-nums"
                    style={{
                      backgroundColor: `rgba(0, 159, 218, ${0.05 + intensity * 0.85})`,
                      color: intensity > 0.45 ? '#fff' : '#002244',
                    }}
                    title={`${s} · ${months[ri]} = ${v.toLocaleString()}`}
                  >
                    {v ? v.toLocaleString() : ''}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
