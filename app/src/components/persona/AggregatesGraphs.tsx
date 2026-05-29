/* eslint-disable i18next/no-literal-string */
'use client';

import { useEffect, useState } from 'react';
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

import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui';
import type { Locale } from '@/i18n';
import { bi } from '@/lib/bi';

// Charts tab — every series reads the real /v1/internal/aggregates/trend
// endpoint (SQL over complaints + social_signals). No hardcoded numbers.

const NAVY = '#002244';
const CYAN = '#009FDA';
const GOLD = '#F5BD24';

interface MotivoRow {
  motivo_code: string;
  n_complaints: number;
  pct_of_all: number | null;
}
interface MonthRow {
  month: string;
  complaints: number;
  social: number;
}

export function AggregatesGraphs({
  locale,
  onPickMotivo,
}: {
  locale: Locale;
  onPickMotivo?: (motivo: string) => void;
}) {
  const [byMotivo, setByMotivo] = useState<MotivoRow[]>([]);
  const [byMonth, setByMonth] = useState<MonthRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/app/api/aggregates/trend', { cache: 'no-store' })
      .then((r) => r.json())
      .then((d: { by_motivo?: MotivoRow[]; by_month?: MonthRow[] }) => {
        setByMotivo(d.by_motivo ?? []);
        setByMonth(d.by_month ?? []);
      })
      .catch(() => undefined)
      .finally(() => setLoading(false));
  }, []);

  const topMotivo = byMotivo.length ? byMotivo[0].motivo_code : null;
  const socialMonths = byMonth.filter((m) => m.social > 0).map((m) => m.month);

  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
      {/* (a) Motivo distribution — horizontal bars, top highlighted, clickable */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{bi(locale, 'Motivos más reclamados', 'Most-complained motives')}</CardTitle>
        </CardHeader>
        <CardBody>
          {loading ? (
            <p className="py-8 text-center text-xs text-fg-muted">{bi(locale, 'Cargando…', 'Loading…')}</p>
          ) : byMotivo.length === 0 ? (
            <p className="py-8 text-center text-xs text-fg-muted">{bi(locale, 'Sin datos.', 'No data.')}</p>
          ) : (
            <>
              <div className="h-[320px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={byMotivo} layout="vertical" margin={{ top: 4, right: 16, bottom: 0, left: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" horizontal={false} />
                    <XAxis type="number" tick={{ fontSize: 10 }} />
                    <YAxis type="category" dataKey="motivo_code" tick={{ fontSize: 9 }} width={150} />
                    <RTooltip />
                    <Bar dataKey="n_complaints" radius={[0, 2, 2, 0]}>
                      {byMotivo.map((m) => (
                        <Cell
                          key={m.motivo_code}
                          fill={m.motivo_code === topMotivo ? CYAN : NAVY}
                          cursor={onPickMotivo ? 'pointer' : undefined}
                          onClick={() => onPickMotivo?.(m.motivo_code)}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <p className="mt-1 text-2xs italic text-fg-subtle">
                {onPickMotivo
                  ? bi(locale, 'Clic en una barra → filtra la pestaña Tablas por ese motivo.', 'Click a bar → filters the Tables tab by that motive.')
                  : bi(locale, 'Conteos reales sobre todos los reclamos.', 'Real counts over all complaints.')}
              </p>
            </>
          )}
        </CardBody>
      </Card>

      {/* (b) Trend over time — complaints + social overlay (dashed) */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{bi(locale, 'Volumen mensual de reclamos', 'Monthly complaint volume')}</CardTitle>
        </CardHeader>
        <CardBody>
          {loading ? (
            <p className="py-8 text-center text-xs text-fg-muted">{bi(locale, 'Cargando…', 'Loading…')}</p>
          ) : byMonth.length === 0 ? (
            <p className="py-8 text-center text-xs text-fg-muted">{bi(locale, 'Sin datos.', 'No data.')}</p>
          ) : (
            <>
              <div className="h-[320px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={byMonth} margin={{ top: 4, right: 16, bottom: 0, left: -12 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis dataKey="month" tick={{ fontSize: 9 }} />
                    <YAxis tick={{ fontSize: 10 }} width={32} />
                    <RTooltip />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <Line
                      type="monotone"
                      dataKey="complaints"
                      name={bi(locale, 'Reclamos', 'Complaints')}
                      stroke={NAVY}
                      strokeWidth={2}
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="social"
                      name={bi(locale, 'Señales sociales', 'Social signals')}
                      stroke={GOLD}
                      strokeWidth={2}
                      strokeDasharray="5 4"
                      dot={{ r: 2 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <p className="mt-1 text-2xs italic text-fg-subtle">
                {bi(
                  locale,
                  `Reclamos por fecha de recepción. Superpuesta (línea punteada dorada): señales en redes sociales (social_signals, real)${socialMonths.length ? ` — cobertura: ${socialMonths.join(', ')}` : ' — sin cobertura aún'}.`,
                  `Complaints by received date. Overlay (dashed gold): social-media signals (social_signals, real)${socialMonths.length ? ` — coverage: ${socialMonths.join(', ')}` : ' — no coverage yet'}.`,
                )}
              </p>
            </>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
