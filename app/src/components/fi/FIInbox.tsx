/* eslint-disable i18next/no-literal-string */
'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { ChevronRight, Mail, Star } from 'lucide-react';

import { cn } from '@/lib/cn';

interface EmailRow {
  COD_REC?: string;
  NCL_CLI?: string;
  CNL_ING?: string;
  PRD_SBS?: string;
  MOT_SBS?: string;
  DET_REC?: string;
  __institution: string;
  __sheet: string;
}

interface Props {
  emails: Array<Record<string, unknown>>;
  goldenComplaintId: string;
}

function truncate(s: string | undefined, n: number): string {
  const v = (s || '').trim();
  return v.length > n ? `${v.slice(0, n)}…` : v;
}

function subjectFor(row: EmailRow): string {
  const prd = (row.PRD_SBS || '').trim();
  const mot = (row.MOT_SBS || '').trim();
  if (prd && mot) return `${prd} — ${mot}`;
  return prd || mot || 'Reclamo de cliente';
}

function channelStyle(raw?: string): string {
  const s = (raw || '').toLowerCase();
  if (s.includes('web')) return 'bg-blue-100 text-blue-800 border-blue-200';
  if (s.includes('tele')) return 'bg-amber-100 text-amber-800 border-amber-200';
  if (s.includes('oficina') || s.includes('domicilio'))
    return 'bg-purple-100 text-purple-800 border-purple-200';
  if (s.includes('app') || s.includes('aplicativo'))
    return 'bg-emerald-100 text-emerald-800 border-emerald-200';
  return 'bg-slate-100 text-slate-700 border-slate-200';
}

export function FIInbox({ emails, goldenComplaintId: _goldenComplaintId }: Props) {
  const rows = emails as unknown as EmailRow[];

  // The golden complaint is the highest-quality row for the demo. We
  // surface "the highest-stake-looking email" — for the data shape this
  // means the first row that mentions a credit card narrative; falls
  // back to the first row.
  const goldenRowIdx = useMemo(() => {
    const idx = rows.findIndex((r) =>
      (r.DET_REC || '').toLowerCase().includes('cargo no reconocido') ||
      (r.PRD_SBS || '').toLowerCase().includes('tarjeta'),
    );
    return idx >= 0 ? idx : 0;
  }, [rows]);

  const [visibleCount, setVisibleCount] = useState(4);
  useEffect(() => {
    if (visibleCount >= rows.length) return;
    const id = setTimeout(() => setVisibleCount((n) => n + 1), 5000);
    return () => clearTimeout(id);
  }, [visibleCount, rows.length]);

  // Pin the golden row at the top; show staggered arrival for the rest.
  const golden = rows[goldenRowIdx];
  const rest = rows
    .map((r, i) => ({ row: r, idx: i }))
    .filter(({ idx }) => idx !== goldenRowIdx)
    .slice(0, visibleCount);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-[#2C3E50]">
          Bandeja de reclamos — Atención al cliente
        </h1>
        <p className="text-sm text-[#2C3E50]/70">
          Reclamos recibidos por el canal del cliente. El equipo de Atención
          procesa cada caso y lo eleva a SBS según corresponda.
        </p>
      </div>

      <Link
        href={`/fi/banco-demo-001/triage/${goldenRowIdx}`}
        className="block rounded-md border-2 border-amber-400 bg-amber-50 px-4 py-3 shadow-sm transition-colors hover:bg-amber-100"
      >
        <div className="mb-1 flex items-center gap-2">
          <Star className="h-4 w-4 fill-amber-500 text-amber-500" />
          <span className="rounded-sm bg-amber-500 px-2 py-0.5 text-xs font-semibold text-white">
            ★ Recomendado para demo
          </span>
          <span className={cn('rounded-sm border px-1.5 py-0.5 text-2xs', channelStyle(golden?.CNL_ING))}>
            {golden?.CNL_ING || '—'}
          </span>
        </div>
        <p className="text-sm font-medium text-[#2C3E50]">
          {golden?.NCL_CLI || '—'} — {subjectFor(golden)}
        </p>
        <p className="mt-0.5 text-xs text-[#2C3E50]/70">
          {truncate(golden?.DET_REC, 180)}
        </p>
      </Link>

      <div className="rounded-md border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 bg-slate-50 px-4 py-2 text-xs font-medium uppercase tracking-wide text-slate-600">
          Otros reclamos en bandeja
        </div>
        <ul role="list" className="divide-y divide-slate-100">
          {rest.length === 0 ? (
            <li className="p-6 text-sm text-slate-500">Cargando bandeja…</li>
          ) : null}
          {rest.map(({ row, idx }) => (
            <li key={`${row.COD_REC}-${idx}`}>
              <Link
                href={`/fi/banco-demo-001/triage/${idx}`}
                className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-slate-50"
              >
                <Mail className="h-4 w-4 shrink-0 text-slate-400" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium text-slate-800">
                      {row.NCL_CLI || '—'}
                    </span>
                    <span
                      className={cn(
                        'rounded-sm border px-1.5 py-0.5 text-2xs',
                        channelStyle(row.CNL_ING),
                      )}
                    >
                      {row.CNL_ING || '—'}
                    </span>
                  </div>
                  <p className="truncate text-sm text-slate-700">{subjectFor(row)}</p>
                  <p className="truncate text-xs text-slate-500">
                    {truncate(row.DET_REC, 120)}
                  </p>
                </div>
                <ChevronRight className="h-4 w-4 shrink-0 text-slate-400" />
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
