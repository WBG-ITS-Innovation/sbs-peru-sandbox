/* eslint-disable i18next/no-literal-string */
// Three real-data charts that the 2026-05-27 SBS demo asks for on the
// cockpit. Fetches from /app/api/journey/stats (which shells out to a
// thin psycopg script). All charts use the SBS palette tokens.

'use client';

import { useEffect, useState } from 'react';
import {
  Bar,
  BarChart,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui';

interface Stats {
  hourly_24h?: Array<{ hour: string; count: number }>;
  by_channel?: Array<{ channel: string; count: number; pct: number }>;
  top_motivos?: Array<{ motivo: string; count: number }>;
}

const NAVY = '#002244';
const CYAN = '#009FDA';
const GOLD = '#F5BD24';
const SLATE = '#6B7280';

const PIE_COLORS = [CYAN, GOLD, NAVY, '#3B82F6', '#F97316', SLATE];

export function DemoCharts() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetch('/app/api/journey/stats', { cache: 'no-store' })
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return (await r.json()) as Stats;
      })
      .then((s) => {
        if (!cancelled) setStats(s);
      })
      .catch((e) => {
        if (!cancelled) setError(String(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <Card>
        <CardBody className="text-sm text-fg-muted">
          {/* eslint-disable-next-line i18next/no-literal-string */}
          Estadísticas no disponibles: <span className="font-mono">{error}</span>
        </CardBody>
      </Card>
    );
  }
  if (!stats) {
    return (
      <Card>
        {/* eslint-disable-next-line i18next/no-literal-string */}
        <CardBody className="text-sm text-fg-muted">Cargando estadísticas…</CardBody>
      </Card>
    );
  }

  return (
    <div className="grid gap-3 lg:grid-cols-3">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {/* eslint-disable-next-line i18next/no-literal-string */}
            Reclamos · últimas 24 horas
          </CardTitle>
        </CardHeader>
        <CardBody className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={stats.hourly_24h || []} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
              <XAxis dataKey="hour" tick={{ fontSize: 10, fill: SLATE }} />
              <YAxis tick={{ fontSize: 10, fill: SLATE }} allowDecimals={false} />
              <Tooltip
                contentStyle={{ fontSize: 12, borderRadius: 2 }}
                labelStyle={{ color: NAVY }}
              />
              <Bar dataKey="count" fill={CYAN} radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {/* eslint-disable-next-line i18next/no-literal-string */}
            Distribución por canal de ingreso
          </CardTitle>
        </CardHeader>
        <CardBody className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={stats.by_channel || []}
                dataKey="count"
                nameKey="channel"
                cx="50%"
                cy="50%"
                innerRadius={40}
                outerRadius={70}
                paddingAngle={2}
              >
                {(stats.by_channel || []).map((_, i) => (
                  <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{ fontSize: 12, borderRadius: 2 }}
                formatter={(value, _name, item) => {
                  const pct = (item?.payload as { pct?: number } | undefined)?.pct ?? 0;
                  return [`${String(value)} (${pct}%)`, ''];
                }}
              />
              <Legend
                verticalAlign="bottom"
                height={36}
                wrapperStyle={{ fontSize: 10 }}
              />
            </PieChart>
          </ResponsiveContainer>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {/* eslint-disable-next-line i18next/no-literal-string */}
            Top 5 motivos · esta semana
          </CardTitle>
        </CardHeader>
        <CardBody className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={stats.top_motivos || []}
              layout="vertical"
              margin={{ top: 4, right: 16, bottom: 4, left: 16 }}
            >
              <XAxis type="number" tick={{ fontSize: 10, fill: SLATE }} allowDecimals={false} />
              <YAxis
                dataKey="motivo"
                type="category"
                tick={{ fontSize: 10, fill: NAVY }}
                width={140}
              />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 2 }} />
              <Bar dataKey="count" fill={GOLD} radius={[0, 2, 2, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </CardBody>
      </Card>
    </div>
  );
}
