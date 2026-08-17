// SPDX-License-Identifier: Apache-2.0
// Cockpit insights board — replaces the live ingestion ticker that lived
// here. Pure SUCAVE-style supervisor analytics (institution / product /
// motivo / channel / severity / source mix) plus a granular complaint
// explorer with mini drag-style chart builder and pre-built suggestion
// shortcuts.
//
// The live "is SBS receiving traffic?" view is at /app/ingestion.
// The per-complaint live drilldown is at /app/processing.
/* eslint-disable i18next/no-literal-string */

'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  AlertTriangle,
  CircleHelp,
  Info,
  LayoutGrid,
  Sparkles,
  TrendingUp,
} from 'lucide-react';

import {
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Tooltip as InfoTooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui';
import type { Locale } from '@/i18n';
import { cn } from '@/lib/cn';

const NAVY = '#002244';
const CYAN = '#009FDA';
const GOLD = '#F5BD24';
const SLATE = '#6B7280';
const PIE = [CYAN, GOLD, NAVY, '#3B82F6', '#F97316', '#10B981', '#8B5CF6', '#EC4899'];

interface Insights {
  kpis?: {
    complaints_24h: number;
    complaints_7d: number;
    active_institutions: number;
    anomalies_active: number;
  };
  by_institution?: Array<{ institution_id: string; label: string; count: number }>;
  by_product?: Array<{ product: string; count: number }>;
  by_motivo?: Array<{ motivo: string; count: number }>;
  by_channel?: Array<{ channel: string; count: number; pct: number }>;
  by_severity?: Array<{ severity: string; count: number }>;
  by_source?: Array<{ source: string; count: number }>;
  hourly_24h?: Array<{ hour: string; count: number }>;
  daily_30d?: Array<{ day: string; count: number }>;
  granular?: Array<{
    complaint_id: string;
    institution: string;
    motivo: string;
    product: string;
    channel: string;
    severity: string;
    received_at: string;
  }>;
}

type GranularDim = 'institution' | 'motivo' | 'product' | 'channel' | 'severity';
type GranularChart = 'bar' | 'pie' | 'line';

const DIM_OPTIONS: Array<{ key: GranularDim; label_es: string; label_en: string }> = [
  { key: 'institution', label_es: 'Entidad', label_en: 'Institution' },
  { key: 'motivo', label_es: 'Motivo', label_en: 'Motive' },
  { key: 'product', label_es: 'Producto', label_en: 'Product' },
  { key: 'channel', label_es: 'Canal', label_en: 'Channel' },
  { key: 'severity', label_es: 'Severidad', label_en: 'Severity' },
];

const SUGGESTIONS = [
  { dim: 'institution' as GranularDim, chart: 'bar' as GranularChart, label_es: 'Reclamos por entidad', label_en: 'Complaints by institution' },
  { dim: 'motivo' as GranularDim, chart: 'bar' as GranularChart, label_es: 'Top motivos', label_en: 'Top motives' },
  { dim: 'channel' as GranularDim, chart: 'pie' as GranularChart, label_es: 'Mix de canales', label_en: 'Channel mix' },
  { dim: 'product' as GranularDim, chart: 'bar' as GranularChart, label_es: 'Productos más reclamados', label_en: 'Most-complained products' },
  { dim: 'severity' as GranularDim, chart: 'pie' as GranularChart, label_es: 'Distribución de severidad', label_en: 'Severity distribution' },
];

export function InsightsBoard({ locale }: { locale: Locale }) {
  const [data, setData] = useState<Insights | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [granDim, setGranDim] = useState<GranularDim>('institution');
  const [granChart, setGranChart] = useState<GranularChart>('bar');
  // Locale is resolved server-side and passed in, so the rendered language is
  // identical on the server and the client's first paint (no hydration drift).
  const es = locale !== 'en-US';

  useEffect(() => {
    let cancelled = false;
    const pull = async () => {
      try {
        const r = await fetch('/app/api/journey/insights', { cache: 'no-store' });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        if (!cancelled) {
          setData(await r.json());
          setError(null);
        }
      } catch (exc) {
        if (!cancelled) setError(String(exc));
      }
    };
    pull();
    const id = window.setInterval(pull, 8000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const granAgg = useMemo(() => {
    if (!data?.granular) return [];
    const m = new Map<string, number>();
    for (const r of data.granular) {
      const k = (r as Record<GranularDim, string>)[granDim];
      m.set(k, (m.get(k) || 0) + 1);
    }
    return Array.from(m.entries())
      .map(([k, v]) => ({ key: k, count: v }))
      .sort((a, b) => b.count - a.count);
  }, [data, granDim]);

  return (
    <div className="space-y-4">
      {error ? (
        <Card>
          <CardBody className="text-sm text-danger">Cockpit insights error: {error}</CardBody>
        </Card>
      ) : null}

      {/* KPIs */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiTile
          label={es ? 'Reclamos en 24h' : 'Complaints in 24h'}
          value={data?.kpis?.complaints_24h ?? '—'}
          icon={<TrendingUp className="h-4 w-4 text-brand-cyan" />}
          info="Suma de reclamos canónicos persistidos por SBS en las últimas 24 horas. Incluye Tier 1 NRT y Tier 2 batch."
        />
        <KpiTile
          label={es ? 'Reclamos en 7d' : 'Complaints in 7d'}
          value={data?.kpis?.complaints_7d ?? '—'}
          icon={<TrendingUp className="h-4 w-4 text-brand-navy" />}
          info="Volumen total de reclamos recibidos en los últimos 7 días. Útil para comparar tendencia semanal vs. picos diarios."
        />
        <KpiTile
          label={es ? 'Entidades activas (7d)' : 'Active entities (7d)'}
          value={data?.kpis?.active_institutions ?? '—'}
          icon={<LayoutGrid className="h-4 w-4 text-brand-navy" />}
          info="Número de instituciones distintas (SBS-NNNNNN) con al menos un reclamo en los últimos 7 días."
        />
        <KpiTile
          label={es ? 'Anomalías activas' : 'Active anomalies'}
          value={data?.kpis?.anomalies_active ?? '—'}
          icon={<AlertTriangle className="h-4 w-4 text-brand-gold" />}
          info="Reclamos cuyo composite_score (agente de investigación) supera el umbral 0.70. Se publican a la cabina para revisión humana."
          highlight={(data?.kpis?.anomalies_active ?? 0) > 0}
        />
      </div>

      {/* SUCAVE-style stats */}
      <div className="grid gap-3 lg:grid-cols-3">
        <ChartCard
          title={es ? 'Por entidad · top 10 (7d)' : 'By institution · top 10 (7d)'}
          info="Distribución de reclamos por institución supervisada en los últimos 7 días. Si una entidad concentra más del 50% sin explicación de cuota de mercado, es señal de revisar."
        >
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={data?.by_institution || []} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
              <XAxis type="number" tick={{ fontSize: 10, fill: SLATE }} allowDecimals={false} />
              <YAxis dataKey="label" type="category" tick={{ fontSize: 10, fill: NAVY }} width={140} />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 2 }} />
              <Bar dataKey="count" fill={NAVY} radius={[0, 2, 2, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title={es ? 'Por motivo · top 10 (7d)' : 'By motive · top 10 (7d)'}
          info="Códigos del Anexo C del Reglamento de Reclamos. Cobros indebidos suele ser el motivo más frecuente; un cambio brusco indica patrón emergente."
        >
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={data?.by_motivo || []} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
              <XAxis type="number" tick={{ fontSize: 10, fill: SLATE }} allowDecimals={false} />
              <YAxis dataKey="motivo" type="category" tick={{ fontSize: 10, fill: NAVY }} width={140} />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 2 }} />
              <Bar dataKey="count" fill={GOLD} radius={[0, 2, 2, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title={es ? 'Por producto (7d)' : 'By product (7d)'}
          info="Producto bancario al que se refiere el reclamo (Anexo B). Cuenta de ahorros + Tarjeta de crédito típicamente dominan."
        >
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={data?.by_product || []} margin={{ top: 4, right: 16, bottom: 24, left: -8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
              <XAxis dataKey="product" tick={{ fontSize: 9, fill: SLATE, angle: -25, textAnchor: 'end' }} interval={0} height={40} />
              <YAxis tick={{ fontSize: 10, fill: SLATE }} allowDecimals={false} />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 2 }} />
              <Bar dataKey="count" fill={CYAN} radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title={es ? 'Mix de canales' : 'Channel mix'}
          info="Canal por el que el cliente registró el reclamo (Anexo A). La página web y el aplicativo móvil tienden a dominar; el cambio hacia teléfono puede indicar problemas digitales."
        >
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={data?.by_channel || []} dataKey="count" nameKey="channel" cx="50%" cy="45%" innerRadius={35} outerRadius={70} paddingAngle={2}>
                {(data?.by_channel || []).map((_, i) => (
                  <Cell key={i} fill={PIE[i % PIE.length]} />
                ))}
              </Pie>
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 2 }} />
              <Legend wrapperStyle={{ fontSize: 9 }} verticalAlign="bottom" />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title={es ? 'Severidad' : 'Severity'}
          info="Severidad declarada por la institución al enviar el reclamo (LOW/MEDIUM/HIGH/CRITICAL). El agente Triage puede sobreescribirla con su recomendación."
        >
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={data?.by_severity || []} dataKey="count" nameKey="severity" cx="50%" cy="45%" innerRadius={35} outerRadius={70} paddingAngle={2}>
                {(data?.by_severity || []).map((s, i) => (
                  <Cell key={i} fill={severityColor(s.severity)} />
                ))}
              </Pie>
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 2 }} />
              <Legend wrapperStyle={{ fontSize: 9 }} verticalAlign="bottom" />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title={es ? 'Origen · Tier 1 NRT vs Tier 2 batch' : 'Source · Tier 1 NRT vs Tier 2 batch'}
          info="Tier 1 NRT (api_realtime) son reclamos enviados uno a uno por la institución vía la API granular. Tier 2 batch son envíos diarios CSV. La mayoría de bancos grandes usa Tier 1; cooperativas pequeñas usan Tier 2."
        >
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={data?.by_source || []} margin={{ top: 4, right: 16, bottom: 0, left: -8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
              <XAxis dataKey="source" tick={{ fontSize: 10, fill: SLATE }} />
              <YAxis tick={{ fontSize: 10, fill: SLATE }} allowDecimals={false} />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 2 }} />
              <Bar dataKey="count" fill={GOLD} radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <ChartCard
          title={es ? 'Volumen por hora · 24h' : 'Hourly volume · 24h'}
          info="Cada barra es una hora UTC. Picos sostenidos > 2× la media indican incidente o lanzamiento de producto reciente."
        >
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={data?.hourly_24h || []} margin={{ top: 4, right: 16, bottom: 0, left: -8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
              <XAxis dataKey="hour" tick={{ fontSize: 10, fill: SLATE }} />
              <YAxis tick={{ fontSize: 10, fill: SLATE }} allowDecimals={false} />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 2 }} />
              <Bar dataKey="count" fill={CYAN} radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title={es ? 'Volumen diario · 30d' : 'Daily volume · 30d'}
          info="Tendencia diaria del último mes. Útil para comparar con el reporte RR1 mensual SUCAVE."
        >
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={data?.daily_30d || []} margin={{ top: 4, right: 16, bottom: 0, left: -8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
              <XAxis dataKey="day" tick={{ fontSize: 10, fill: SLATE }} />
              <YAxis tick={{ fontSize: 10, fill: SLATE }} allowDecimals={false} />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 2 }} />
              <Line type="monotone" dataKey="count" stroke={NAVY} strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Granular explorer */}
      <Card className="border-brand-cyan/40">
        <CardHeader>
          <CardTitle className="flex items-center justify-between text-base">
            <span className="flex items-center gap-2">
              <LayoutGrid className="h-4 w-4 text-brand-cyan" />
              {es ? 'Explorador de datos granulares' : 'Granular data explorer'}
            </span>
            <span className="font-mono text-2xs text-fg-muted">
              {data?.granular?.length ?? 0} {es ? 'reclamos (últimos 7d)' : 'complaints (last 7d)'}
            </span>
          </CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          <div>
            <p className="mb-1 flex items-center gap-1 text-xs text-fg-muted">
              <Sparkles className="h-3 w-3 text-brand-gold" />
              {es ? 'Sugerencias' : 'Suggestions'}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {SUGGESTIONS.map((s) => (
                <button
                  key={`${s.dim}-${s.chart}`}
                  type="button"
                  onClick={() => {
                    setGranDim(s.dim);
                    setGranChart(s.chart);
                  }}
                  className={cn(
                    'rounded-sbs border px-2 py-1 text-xs transition-colors',
                    granDim === s.dim && granChart === s.chart
                      ? 'border-brand-cyan bg-brand-cyan/10 text-brand-navy'
                      : 'border-border bg-surface text-fg hover:bg-surface-subtle',
                  )}
                >
                  {es ? s.label_es : s.label_en}
                </button>
              ))}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3 rounded-sbs border border-border-subtle bg-surface-subtle px-3 py-2">
            <span className="text-xs font-medium text-fg-muted">
              {es ? 'Dimensión:' : 'Dimension:'}
            </span>
            {DIM_OPTIONS.map((d) => (
              <button
                key={d.key}
                type="button"
                onClick={() => setGranDim(d.key)}
                className={cn(
                  'rounded-sbs border px-2 py-0.5 text-xs',
                  granDim === d.key
                    ? 'border-brand-cyan bg-brand-cyan/10 text-brand-navy'
                    : 'border-border bg-surface text-fg hover:bg-surface-subtle',
                )}
              >
                {es ? d.label_es : d.label_en}
              </button>
            ))}
            <span className="ml-3 text-xs font-medium text-fg-muted">
              {es ? 'Tipo:' : 'Type:'}
            </span>
            {(['bar', 'pie', 'line'] as GranularChart[]).map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => setGranChart(c)}
                className={cn(
                  'rounded-sbs border px-2 py-0.5 text-xs',
                  granChart === c
                    ? 'border-brand-cyan bg-brand-cyan/10 text-brand-navy'
                    : 'border-border bg-surface text-fg hover:bg-surface-subtle',
                )}
              >
                {c === 'bar' ? (es ? 'Barras' : 'Bars') : c === 'pie' ? (es ? 'Pastel' : 'Pie') : (es ? 'Línea' : 'Line')}
              </button>
            ))}
          </div>

          <div className="h-64">
            <RenderGran chart={granChart} data={granAgg} />
          </div>

          <div className="max-h-64 overflow-auto rounded-sbs border border-border-subtle">
            <table className="w-full text-xs">
              <thead className="bg-surface-subtle text-fg-muted">
                <tr>
                  <th className="px-2 py-1.5 text-left font-mono uppercase tracking-wide">complaint_id</th>
                  <th className="px-2 py-1.5 text-left font-mono uppercase tracking-wide">{es ? 'Entidad' : 'Inst'}</th>
                  <th className="px-2 py-1.5 text-left font-mono uppercase tracking-wide">{es ? 'Motivo' : 'Motive'}</th>
                  <th className="px-2 py-1.5 text-left font-mono uppercase tracking-wide">{es ? 'Producto' : 'Product'}</th>
                  <th className="px-2 py-1.5 text-left font-mono uppercase tracking-wide">{es ? 'Canal' : 'Channel'}</th>
                  <th className="px-2 py-1.5 text-left font-mono uppercase tracking-wide">{es ? 'Severidad' : 'Severity'}</th>
                  <th className="px-2 py-1.5 text-left font-mono uppercase tracking-wide">{es ? 'Recibido' : 'Received'}</th>
                </tr>
              </thead>
              <tbody>
                {(data?.granular || []).slice(0, 50).map((g) => (
                  <tr key={g.complaint_id} className="border-t border-border-subtle hover:bg-surface-subtle">
                    <td className="px-2 py-1.5">
                      <Link
                        href={`/processing/${g.complaint_id}`}
                        className="font-mono text-brand-cyan hover:underline"
                      >
                        {g.complaint_id}
                      </Link>
                    </td>
                    <td className="px-2 py-1.5 font-mono text-2xs">{g.institution}</td>
                    <td className="px-2 py-1.5">{g.motivo}</td>
                    <td className="px-2 py-1.5 font-mono text-2xs">{g.product}</td>
                    <td className="px-2 py-1.5 text-2xs">{g.channel}</td>
                    <td className="px-2 py-1.5 font-mono text-2xs">{g.severity}</td>
                    <td className="px-2 py-1.5 font-mono text-2xs text-fg-muted">{g.received_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}

function KpiTile(props: {
  label: string;
  value: number | string;
  icon: React.ReactNode;
  info: string;
  highlight?: boolean;
}) {
  return (
    <TooltipProvider delayDuration={150}>
      <Card className={cn(props.highlight && 'border-brand-gold')}>
        <CardBody className="space-y-1 px-4 py-3">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-xs font-medium text-fg-muted">
              {props.icon}
              {props.label}
            </span>
            <InfoTooltip>
              <TooltipTrigger asChild>
                <button type="button" aria-label="Info" className="text-fg-muted hover:text-fg">
                  <CircleHelp className="h-3 w-3" />
                </button>
              </TooltipTrigger>
              <TooltipContent>{props.info}</TooltipContent>
            </InfoTooltip>
          </div>
          <p className="font-mono text-3xl font-semibold leading-none text-brand-navy">
            {props.value}
          </p>
        </CardBody>
      </Card>
    </TooltipProvider>
  );
}

function ChartCard(props: { title: string; info: string; children: React.ReactNode }) {
  return (
    <TooltipProvider delayDuration={150}>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-1.5 text-base">
            {props.title}
            <InfoTooltip>
              <TooltipTrigger asChild>
                <button type="button" aria-label="Explanation" className="rounded-full p-0.5 text-fg-muted hover:bg-surface-subtle hover:text-fg">
                  <Info className="h-3.5 w-3.5" />
                </button>
              </TooltipTrigger>
              <TooltipContent side="bottom" align="start">{props.info}</TooltipContent>
            </InfoTooltip>
          </CardTitle>
        </CardHeader>
        <CardBody>{props.children}</CardBody>
      </Card>
    </TooltipProvider>
  );
}

function severityColor(sev: string): string {
  switch (sev.toUpperCase()) {
    case 'CRITICAL':
      return '#DC2626';
    case 'HIGH':
      return GOLD;
    case 'MEDIUM':
      return CYAN;
    case 'LOW':
      return '#10B981';
    default:
      return SLATE;
  }
}

function RenderGran(props: {
  chart: GranularChart;
  data: Array<{ key: string; count: number }>;
}) {
  if (props.chart === 'pie') {
    return (
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={props.data} dataKey="count" nameKey="key" cx="50%" cy="50%" innerRadius={45} outerRadius={90} paddingAngle={2}>
            {props.data.map((_, i) => (
              <Cell key={i} fill={PIE[i % PIE.length]} />
            ))}
          </Pie>
          <Tooltip contentStyle={{ fontSize: 12, borderRadius: 2 }} />
          <Legend wrapperStyle={{ fontSize: 10 }} />
        </PieChart>
      </ResponsiveContainer>
    );
  }
  if (props.chart === 'line') {
    return (
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={props.data} margin={{ top: 4, right: 16, bottom: 0, left: -8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
          <XAxis dataKey="key" tick={{ fontSize: 10, fill: SLATE }} />
          <YAxis tick={{ fontSize: 10, fill: SLATE }} allowDecimals={false} />
          <Tooltip contentStyle={{ fontSize: 12, borderRadius: 2 }} />
          <Line type="monotone" dataKey="count" stroke={NAVY} strokeWidth={2} dot={{ r: 3 }} />
        </LineChart>
      </ResponsiveContainer>
    );
  }
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={props.data} margin={{ top: 4, right: 16, bottom: 24, left: -8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
        <XAxis dataKey="key" tick={{ fontSize: 10, fill: SLATE, angle: -20, textAnchor: 'end' }} interval={0} height={50} />
        <YAxis tick={{ fontSize: 10, fill: SLATE }} allowDecimals={false} />
        <Tooltip contentStyle={{ fontSize: 12, borderRadius: 2 }} />
        <Bar dataKey="count" fill={CYAN} radius={[2, 2, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
