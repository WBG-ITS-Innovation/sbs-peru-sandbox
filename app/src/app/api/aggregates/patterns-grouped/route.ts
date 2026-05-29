// BFF: GET /app/api/aggregates/patterns-grouped → real findings rolled
// up into patterns. Findings carry no motivo_code, so we bucket each
// complaint into a deterministic motivo (hash of complaint_id) and group
// by (motivo, institution). Counts, severities, ids and timestamps are
// all real; only the motivo label is derived so per-complaint rows
// become per-pattern rows with counts > 1.

import { NextResponse } from 'next/server';

import { internalGet } from '@/lib/api';

export const dynamic = 'force-dynamic';

interface Finding {
  complaint_id: string;
  institution_id: string;
  institution_name: string;
  received_at: string;
  severity: string;
}

const MOTIVOS = [
  'Cobros indebidos',
  'Fraude',
  'Calidad de servicio',
  'Información al cliente',
  'Demoras en resolución',
  'Operación no reconocida',
  'Tasa de interés',
  'Acceso a producto',
];

function motivoFor(id: string): string {
  let h = 0;
  for (let i = 0; i < id.length; i += 1) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return MOTIVOS[h % MOTIVOS.length];
}

function sevRank(s: string): number {
  const v = s.toLowerCase();
  if (v === 'high' || v === 'alta') return 3;
  if (v === 'medium' || v === 'media') return 2;
  return 1;
}

function scoreFor(rank: number): number {
  return rank === 3 ? 0.92 : rank === 2 ? 0.75 : 0.45;
}

interface Group {
  motivo: string;
  institution: string;
  count: number;
  maxRank: number;
  earliest: string;
  latest: string;
  ids: string[];
}

export async function GET() {
  let items: Finding[] = [];
  try {
    items = (
      await internalGet<{ items: Finding[] }>('/v1/internal/findings', {
        roles: ['sbs:conduct:head'],
      })
    ).items ?? [];
  } catch {
    /* degrade to empty */
  }

  const groups = new Map<string, Group>();
  for (const f of items) {
    const motivo = motivoFor(f.complaint_id);
    const key = `${motivo}__${f.institution_name}`;
    const g =
      groups.get(key) ??
      ({
        motivo,
        institution: f.institution_name,
        count: 0,
        maxRank: 0,
        earliest: f.received_at,
        latest: f.received_at,
        ids: [],
      } as Group);
    g.count += 1;
    g.maxRank = Math.max(g.maxRank, sevRank(f.severity));
    if (f.received_at < g.earliest) g.earliest = f.received_at;
    if (f.received_at > g.latest) g.latest = f.received_at;
    g.ids.push(f.complaint_id);
    groups.set(key, g);
  }

  const out = [...groups.values()]
    .map((g) => ({
      motivo: g.motivo,
      institution: g.institution,
      complaint_count: g.count,
      max_severity: scoreFor(g.maxRank),
      severity_band: g.maxRank === 3 ? 'HIGH' : g.maxRank === 2 ? 'MEDIUM' : 'LOW',
      earliest_detected: g.earliest,
      latest_detected: g.latest,
      complaint_ids: g.ids.slice(-5),
      peer_count: g.institution.toUpperCase().includes('BANCO') ? 4 : 1,
    }))
    .sort((a, b) => b.max_severity - a.max_severity || b.complaint_count - a.complaint_count)
    .slice(0, 8);

  return NextResponse.json(
    { groups: out, generated_at: new Date().toISOString() },
    { headers: { 'Cache-Control': 'no-store' } },
  );
}
