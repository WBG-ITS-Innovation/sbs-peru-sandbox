// BFF: POST /app/api/aggregates/chat → data-grounded answers (NOT a live LLM).
// The on-prem/cloud LLM route is not available on this build (vLLM is not
// running; CloudProvider raises NotImplementedError), so this composes a real
// answer from live data: it queries /v1/internal/findings (severity/recency)
// and /v1/internal/aggregates/patterns (per-institution conduct metrics),
// parses the question intent, and returns a distinct numeric answer. Every
// figure is real; nothing is hardcoded.

import { NextResponse } from 'next/server';

import { internalGet } from '@/lib/api';

export const dynamic = 'force-dynamic';

interface FindingRow {
  complaint_id: string;
  institution_name: string;
  severity: string;
  received_at: string;
}

interface PatternRow {
  institution_name?: string;
  institution_id?: string;
  motivo_code: string;
  n_complaints: number;
  n_resolved: number;
  n_pending: number;
  n_favor_bank: number;
  pct_favor_bank: number | null;
}

interface InstStat {
  name: string;
  complaints: number;
  resolved: number;
  pending: number;
  favorBank: number;
}

function isHigh(s: string): boolean {
  const v = s.toLowerCase();
  return v === 'high' || v === 'alta';
}

function topInstitution(items: FindingRow[]): { name: string; count: number } {
  const counts = new Map<string, number>();
  for (const i of items) counts.set(i.institution_name, (counts.get(i.institution_name) ?? 0) + 1);
  let name = '—';
  let count = 0;
  for (const [n, c] of counts) if (c > count) ((name = n), (count = c));
  return { name, count };
}

// Per-institution conduct stats rolled up from the aggregate patterns.
function institutionStats(rows: PatternRow[]): InstStat[] {
  const m = new Map<string, InstStat>();
  for (const r of rows) {
    const name = r.institution_name ?? r.institution_id ?? '—';
    const s = m.get(name) ?? { name, complaints: 0, resolved: 0, pending: 0, favorBank: 0 };
    s.complaints += r.n_complaints;
    s.resolved += r.n_resolved;
    s.pending += r.n_pending;
    s.favorBank += r.n_favor_bank;
    m.set(name, s);
  }
  return [...m.values()];
}

const pct = (n: number, d: number): number | null => (d > 0 ? Math.round((1000 * n) / d) / 10 : null);

// Match a question against the real institution names; returns the matched
// stat if the question contains a distinctive token from one institution's
// name (e.g. "horizonte", "andes") — not the generic words.
const GENERIC = new Set(['banco', 'caja', 'coopac', 'cooperativa', 'financiera', 'del', 'de', 'la', 'el', 'peru', 'perú', 'sa', 's.a', 'edpyme', 'cmac', 'rural']);
function matchInstitution(q: string, stats: InstStat[]): InstStat | null {
  for (const s of stats) {
    const tokens = s.name.toLowerCase().split(/[^a-záéíóúñ0-9]+/).filter((t) => t.length >= 4 && !GENERIC.has(t));
    if (tokens.some((t) => q.includes(t))) return s;
  }
  return null;
}

export async function POST(request: Request) {
  let message = '';
  try {
    message = ((await request.json()) as { message?: string }).message ?? '';
  } catch {
    /* ignore */
  }
  const q = message.toLowerCase().trim();

  let items: FindingRow[] = [];
  let patterns: PatternRow[] = [];
  try {
    [items, patterns] = await Promise.all([
      internalGet<{ items: FindingRow[] }>('/v1/internal/findings', { roles: ['sbs:conduct:head'] })
        .then((d) => d.items ?? [])
        .catch(() => []),
      internalGet<{ rows: PatternRow[] }>('/v1/internal/aggregates/patterns?scope=entity', { roles: ['sbs:conduct:head'] })
        .then((d) => d.rows ?? [])
        .catch(() => []),
    ]);
  } catch {
    /* degrade to empty */
  }

  const total = items.length;
  const high = items.filter((i) => isHigh(i.severity)).length;
  const top = topInstitution(items);

  const stats = institutionStats(patterns);
  const byVolume = [...stats].sort((a, b) => b.complaints - a.complaints);
  // Worst by bank-favour skew, needing a minimum resolved sample so a single
  // resolved complaint can't read as "100% favour-bank".
  const byBank = stats
    .filter((s) => s.resolved >= 5)
    .map((s) => ({ s, skew: (s.favorBank / s.resolved) * 100 }))
    .sort((a, b) => b.skew - a.skew);
  const byPending = stats
    .filter((s) => s.complaints >= 5)
    .map((s) => ({ s, pend: (s.pending / s.complaints) * 100 }))
    .sort((a, b) => b.pend - a.pend);

  const named = matchInstitution(q, stats);

  let answer: string;

  if (/\bsbs\b|qué es|que es|superinten/.test(q)) {
    answer =
      'La SBS (Superintendencia de Banca, Seguros y AFP del Perú) regula y supervisa la conducta de las entidades financieras. Esta cabina agrega reclamos y señales para detectar patrones de conducta indebida. Ahora mismo hay ' +
      `${total} reclamos recientes en análisis, ${high} de severidad alta.`;
  } else if (/difus|broadcast|sector/.test(q)) {
    answer =
      high > 0
        ? `Se detectaron ${high} señales de severidad alta concentradas en ${top.name}. Lupaman redacta una difusión sectorial al cohorte de pares cuando se confirma una emergencia; revisa la tabla de patrones y la pestaña de aprobaciones.`
        : 'No hay difusiones sectoriales pendientes en este momento. Las difusiones se generan al confirmarse un patrón de severidad alta.';
  } else if (named) {
    const skew = pct(named.favorBank, named.resolved);
    const pend = pct(named.pending, named.complaints);
    answer =
      `${named.name}: ${named.complaints} reclamos agregados, ${named.resolved} resueltos. ` +
      `${pend == null ? '—' : `${pend}%`} pendientes` +
      `${skew == null ? '' : `, ${skew}% resueltos a favor de la entidad`}. ` +
      `Severidad alta reciente: ${items.filter((i) => isHigh(i.severity) && i.institution_name === named.name).length}.`;
  } else if (/peor|worst|ranking|más reclam|mas reclam|cuál.*(entidad|banco|financ|institu|coopac|caja)|cual.*(entidad|banco|financ|institu|coopac|caja)|mayor concentr|concentra/.test(q)) {
    if (byVolume.length === 0) {
      answer = 'Aún no hay datos agregados por institución para responder.';
    } else {
      const v = byVolume[0];
      const bank = byBank[0];
      const pend = byPending[0];
      answer =
        `Por volumen, la entidad con más reclamos es ${v.name} (${v.complaints}). ` +
        (bank ? `Por sesgo a favor de la entidad, la peor es ${bank.s.name} (${Math.round(bank.skew * 10) / 10}% de ${bank.s.resolved} resueltos a su favor). ` : '') +
        (pend ? `Por backlog, ${pend.s.name} lidera con ${Math.round(pend.pend * 10) / 10}% de reclamos pendientes.` : '');
    }
  } else if (/pendien|backlog|sin resolver|demora|atras/.test(q)) {
    const p = byPending[0];
    answer = p
      ? `El mayor backlog está en ${p.s.name}: ${Math.round(p.pend * 10) / 10}% de sus ${p.s.complaints} reclamos siguen pendientes (${p.s.pending} sin resolver).`
      : 'No hay suficientes reclamos agregados para calcular el backlog por institución.';
  } else if (/severid|alta|high|grave/.test(q)) {
    answer = `Hay ${high} reclamos de severidad alta entre ${total} recientes. La mayor concentración está en ${top.name} (${top.count}).`;
  } else if (/fraud|patr|pattern|riesgo|tendencia|cobro|correlaci/.test(q)) {
    answer = `Encontré ${high} detecciones de severidad alta entre ${total} reclamos recientes. La mayor concentración está en ${top.name} (${top.count} reclamos). El motor de agregación (Investigation + Lupaman) eleva estas señales a patrones cuando superan el umbral; consulta la tabla de patrones para el detalle.`;
  } else {
    const v = byVolume[0];
    answer =
      `Según los datos actuales: ${total} reclamos recientes, ${high} de severidad alta` +
      `${v ? `, con mayor volumen en ${v.name} (${v.complaints})` : ''}. ` +
      'Puedes preguntar por una institución, la peor entidad, el backlog (pendientes), una severidad, o patrones de fraude.';
  }

  return NextResponse.json(
    { answer, grounded: { total, high, top: top.name, institutions: stats.length } },
    { headers: { 'Cache-Control': 'no-store' } },
  );
}
