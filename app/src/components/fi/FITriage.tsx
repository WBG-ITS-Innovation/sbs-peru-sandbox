/* eslint-disable i18next/no-literal-string */
'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { ArrowLeft, ArrowRight, CheckCircle2, Circle } from 'lucide-react';

import { cn } from '@/lib/cn';

interface Props {
  row: Record<string, unknown>;
  rowIndex: number;
}

const GROUP1 = [
  ['COD_REC', 'Código del reclamo'],
  ['TID_CLI', 'Tipo de documento'],
  ['NRO_CLI', 'Número de documento'],
  ['NCL_CLI', 'Nombre del cliente'],
  ['COD_CLI', 'Código de cliente'],
  ['FEC_ING', 'Fecha de ingreso'],
  ['CNL_ING', 'Canal de ingreso'],
  ['CNL_OPE', 'Canal de operación'],
  ['UBI_REC', 'Ubigeo'],
  ['PRD_SBS', 'Producto SBS'],
  ['MOT_SBS', 'Motivo SBS'],
  ['SUB_SBS', 'Submotivo SBS'],
  ['DET_REC', 'Detalle del reclamo'],
  ['EMPRESA', 'Entidad reportante'],
] as const;

const GROUP2 = [
  ['FEC_AMP', 'Fecha de ampliación'],
  ['CNL_AMP', 'Canal de ampliación'],
  ['FEC_RES', 'Fecha de resolución'],
  ['CNL_PAC', 'Canal de pago al cliente'],
  ['TIP_RES', 'Tipo de resolución'],
  ['DET_RES', 'Detalle de la resolución'],
  ['PRD_EMP', 'Producto interno'],
  ['EST_REC', 'Estado del reclamo'],
  ['COD_PRV', 'Reclamo previo'],
  ['MNT_PEN_REC', 'Monto pendiente'],
] as const;

const GROUP3 = [
  ['BAN_SEG', 'Bancaseguros'],
  ['PRD_SBS_SEG', 'Producto SBS bancaseguros'],
  ['MOT_SBS_SEG', 'Motivo SBS bancaseguros'],
  ['SUB_SBS_SEG', 'Submotivo SBS bancaseguros'],
] as const;

export function FITriage({ row, rowIndex }: Props) {
  const [mappedThrough, setMappedThrough] = useState(0);
  useEffect(() => {
    setMappedThrough(0);
    const timers: ReturnType<typeof setTimeout>[] = [];
    GROUP1.forEach((_, i) => {
      timers.push(setTimeout(() => setMappedThrough((n) => n + 1), 50 * (i + 1)));
    });
    return () => timers.forEach((t) => clearTimeout(t));
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Link
          href="/fi/banco-demo-001/inbox"
          className="inline-flex items-center gap-1 text-sm text-[#2C3E50] hover:underline"
        >
          <ArrowLeft className="h-4 w-4" />
          Volver a la bandeja
        </Link>
      </div>

      <div>
        <h1 className="text-xl font-semibold text-[#2C3E50]">
          Sistema interno de gestión de reclamos
        </h1>
        <p className="text-sm text-[#2C3E50]/70">
          Normalizando los campos del cliente al formato Anexo 1-A
          (Res. SBS 4036-2022) antes de enviar a la Superintendencia.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[420px_1fr]">
        <aside className="space-y-3">
          <div className="rounded-md border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Cliente
            </p>
            <p className="mt-1 text-sm font-medium text-[#2C3E50]">
              {String(row.NCL_CLI || '—')}
            </p>
            <p className="text-xs text-slate-500">
              {String(row.TID_CLI || '')} {String(row.NRO_CLI || '')}
            </p>
            <hr className="my-3 border-slate-100" />
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Canal · Fecha
            </p>
            <p className="mt-1 text-sm text-[#2C3E50]">
              {String(row.CNL_ING || '—')} · {String(row.FEC_ING || '—')}
            </p>
            <hr className="my-3 border-slate-100" />
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Mensaje del cliente
            </p>
            <p className="mt-1 whitespace-pre-wrap text-xs leading-relaxed text-[#2C3E50]/85">
              {String(row.DET_REC || '—')}
            </p>
          </div>
        </aside>

        <div className="space-y-3">
          <FieldGroup
            title="Auto-mapeados desde el correo"
            fields={GROUP1}
            row={row}
            mappedThrough={mappedThrough}
            animated
          />
          <FieldGroup
            title="Resolución pendiente"
            fields={GROUP2}
            row={row}
            mappedThrough={0}
            animated={false}
          />
          <FieldGroup
            title="Bancaseguros (si aplica)"
            fields={GROUP3}
            row={row}
            mappedThrough={0}
            animated={false}
          />

          <div className="flex justify-end">
            <Link
              href={`/fi/banco-demo-001/submit/${rowIndex}`}
              className="inline-flex items-center gap-2 rounded-md bg-[#2C3E50] px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-[#2C3E50]/90"
            >
              Firmar y enviar a SBS
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

function FieldGroup(props: {
  title: string;
  fields: ReadonlyArray<readonly [string, string]>;
  row: Record<string, unknown>;
  mappedThrough: number;
  animated: boolean;
}) {
  const { title, fields, row, mappedThrough, animated } = props;
  return (
    <div className="rounded-md border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-200 bg-slate-50 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-slate-600">
        {title}
      </div>
      <div className="grid grid-cols-1 gap-2 px-4 py-3 md:grid-cols-2">
        {fields.map(([key, label], idx) => {
          const raw = row[key];
          const value =
            raw === undefined || raw === null || raw === '' ? '—' : String(raw);
          const done = animated && idx < mappedThrough;
          return (
            <div
              key={key}
              className={cn(
                'flex items-start gap-2 rounded-sm border border-slate-100 bg-slate-50 px-2.5 py-1.5 text-xs transition-opacity',
                animated && !done && 'opacity-40',
              )}
            >
              {done ? (
                <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-600" />
              ) : (
                <Circle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-300" />
              )}
              <div className="min-w-0 flex-1">
                <p className="font-mono text-2xs uppercase tracking-wide text-slate-500">
                  {key}
                </p>
                <p className="truncate font-medium text-[#2C3E50]" title={value}>
                  {value}
                </p>
                <p className="text-2xs text-slate-400">{label}</p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
