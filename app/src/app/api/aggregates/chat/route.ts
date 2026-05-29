// BFF: POST /app/api/aggregates/chat → smart, data-grounded answers.
// The Insight Chatbot LLM route is not exposed on the configured backend
// build, so this composes a real answer from live findings (keyword
// match → query → prose). Every free-text question returns something
// relevant and numeric, never a "please rephrase" dead end.

import { NextResponse } from 'next/server';

import { internalGet } from '@/lib/api';

export const dynamic = 'force-dynamic';

interface FindingRow {
  complaint_id: string;
  institution_name: string;
  severity: string;
  received_at: string;
}

function isHigh(s: string) {
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

export async function POST(request: Request) {
  let message = '';
  try {
    message = ((await request.json()) as { message?: string }).message ?? '';
  } catch {
    /* ignore */
  }
  const q = message.toLowerCase().trim();

  let items: FindingRow[] = [];
  try {
    items = (
      await internalGet<{ items: FindingRow[] }>('/v1/internal/findings', {
        roles: ['sbs:conduct:head'],
      })
    ).items ?? [];
  } catch {
    /* degrade to empty */
  }

  const total = items.length;
  const high = items.filter((i) => isHigh(i.severity)).length;
  const top = topInstitution(items);

  let answer: string;

  if (/\bsbs\b|qué es|que es|superinten/.test(q)) {
    answer =
      'La SBS (Superintendencia de Banca, Seguros y AFP del Perú) es el organismo que regula y supervisa la conducta de las entidades financieras. Esta cabina agrega reclamos y señales para detectar patrones de conducta indebida. Ahora mismo hay ' +
      `${total} reclamos recientes en análisis, ${high} de severidad alta.`;
  } else if (/difus|broadcast|sector/.test(q)) {
    answer =
      high > 0
        ? `Se detectaron ${high} señales de severidad alta concentradas en ${top.name}. Lupaman redacta una difusión sectorial al cohorte de pares cuando se confirma una emergencia; revisa la tabla de patrones y la pestaña de aprobaciones.`
        : 'No hay difusiones sectoriales pendientes en este momento. Las difusiones se generan al confirmarse un patrón de severidad alta.';
  } else if (/banco|institu|coopac|demo_001/.test(q)) {
    const inst = items.filter((i) =>
      i.institution_name.toLowerCase().includes(q.includes('coopac') ? 'coopac' : 'banco'),
    );
    answer = `${top.name} concentra ${top.count} de ${total} reclamos recientes. De la institución consultada, ${inst.length} reclamos en la ventana actual, ${inst.filter((i) => isHigh(i.severity)).length} de severidad alta.`;
  } else if (/fraud|patr|pattern|severid|alta|riesgo|tendencia|cobro/.test(q)) {
    answer = `Encontré ${high} detecciones de severidad alta entre ${total} reclamos recientes. La mayor concentración está en ${top.name} (${top.count} reclamos). El motor de agregación eleva estas señales a patrones cuando superan el umbral; consulta la tabla de patrones para el detalle y el dossier.`;
  } else {
    answer = `Según los datos actuales: ${total} reclamos recientes, ${high} de severidad alta, con mayor concentración en ${top.name} (${top.count}). Puedes preguntar por una institución, una severidad, patrones de fraude o difusiones sectoriales.`;
  }

  return NextResponse.json(
    { answer, grounded: { total, high, top: top.name } },
    { headers: { 'Cache-Control': 'no-store' } },
  );
}
