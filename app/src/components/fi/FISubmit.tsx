/* eslint-disable i18next/no-literal-string */
'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowRight,
  CheckCircle2,
  Circle,
  Loader2,
  XCircle,
} from 'lucide-react';

import { cn } from '@/lib/cn';

interface Props {
  row: Record<string, unknown>;
  csrfToken: string;
}

type StepStatus = 'idle' | 'running' | 'done' | 'error';

interface Step {
  id: number;
  label: string;
  detail: string;
  status: StepStatus;
}

export function FISubmit({ row, csrfToken }: Props) {
  const [steps, setSteps] = useState<Step[]>([
    { id: 1, label: 'Presentando certificado mTLS', detail: '', status: 'idle' },
    { id: 2, label: 'Obteniendo token OAuth', detail: '', status: 'idle' },
    { id: 3, label: 'Firmando con HMAC SHA-256', detail: '', status: 'idle' },
    { id: 4, label: 'Generando Idempotency-Key', detail: '', status: 'idle' },
    { id: 5, label: 'POST /v1/sandbox/complaints/granular', detail: '', status: 'idle' },
  ]);
  const [error, setError] = useState<string | null>(null);
  const [complaintId, setComplaintId] = useState<string | null>(null);
  const submittedRef = useRef(false);

  const update = useCallback((id: number, patch: Partial<Step>) => {
    setSteps((s) => s.map((st) => (st.id === id ? { ...st, ...patch } : st)));
  }, []);

  useEffect(() => {
    if (submittedRef.current) return;
    submittedRef.current = true;

    // Visual pacing — reveal steps progressively even though the real
    // submission fires in parallel. When the API returns, we overwrite
    // each step's detail with the real value.
    const timers: ReturnType<typeof setTimeout>[] = [];
    timers.push(setTimeout(() => update(1, { status: 'running' }), 50));
    timers.push(setTimeout(() => update(2, { status: 'running' }), 850));
    timers.push(setTimeout(() => update(3, { status: 'running' }), 1450));
    timers.push(setTimeout(() => update(4, { status: 'running' }), 2050));
    timers.push(setTimeout(() => update(5, { status: 'running' }), 2350));

    const body = {
      institution_complaint_id: row.COD_REC,
      tid_cli: row.TID_CLI,
      nro_cli: row.NRO_CLI,
      ncl_cli: row.NCL_CLI,
      cod_cli: row.COD_CLI,
      received_at: row.FEC_ING,
      channel_in: row.CNL_ING,
      channel_operation: row.CNL_OPE,
      ubigeo: row.UBI_REC,
      product: row.PRD_SBS,
      motive: row.MOT_SBS,
      submotive: row.SUB_SBS,
      narrative: row.DET_REC,
      severity: 'HIGH',
    };

    fetch('/app/api/journey/submit', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-sbs-csrf': csrfToken,
      },
      body: JSON.stringify(body),
    })
      .then(async (r) => {
        const json = (await r.json()) as {
          ok?: boolean;
          error?: string;
          trace?: Record<string, unknown>;
        };
        const trace = json.trace || {};
        const thumb = String(trace.mtls_thumbprint || '');
        const cn = String(trace.mtls_cn || 'BANCO_DEMO_001');
        update(1, {
          status: 'done',
          detail: `CN=${cn} · thumbprint ${thumb.slice(0, 16)}…`,
        });
        update(2, {
          status: 'done',
          detail: `scope=${trace.oauth_scope || '—'} · exp=${trace.oauth_exp || '—'}`,
        });
        update(3, {
          status: 'done',
          detail: `${(trace.hmac_signature_prefix as string) || ''}…`,
        });
        update(4, {
          status: 'done',
          detail: String(trace.idempotency_key || '—'),
        });
        if (json.ok && trace.complaint_id) {
          update(5, {
            status: 'done',
            detail: `HTTP ${trace.http_status} · complaint_id=${trace.complaint_id}`,
          });
          setComplaintId(String(trace.complaint_id));
        } else {
          update(5, {
            status: 'error',
            detail: `HTTP ${trace.http_status || '—'} · ${json.error || 'fallo en la submisión'}`,
          });
          setError(json.error || 'submission failed');
        }
      })
      .catch((exc) => {
        update(5, { status: 'error', detail: String(exc) });
        setError(String(exc));
      });

    return () => timers.forEach((t) => clearTimeout(t));
  }, [row, csrfToken, update]);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-[#2C3E50]">
          Enviando reclamo a SBS — cadena de autenticación
        </h1>
        <p className="text-sm text-[#2C3E50]/70">
          mTLS · OAuth 2.0 client_credentials · HMAC SHA-256 · Idempotency-Key.
          Cada paso se ejecuta en vivo contra la API sandbox de la SBS.
        </p>
      </div>

      <ol className="space-y-2">
        {steps.map((s) => (
          <li
            key={s.id}
            className={cn(
              'flex items-start gap-3 rounded-md border bg-white px-4 py-3 shadow-sm',
              s.status === 'done' && 'border-emerald-200 bg-emerald-50/60',
              s.status === 'error' && 'border-rose-300 bg-rose-50',
              s.status === 'running' && 'border-[#2C3E50]/30',
            )}
          >
            <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center">
              {s.status === 'done' ? (
                <CheckCircle2 className="h-5 w-5 text-emerald-600" />
              ) : s.status === 'error' ? (
                <XCircle className="h-5 w-5 text-rose-600" />
              ) : s.status === 'running' ? (
                <Loader2 className="h-5 w-5 animate-spin text-[#2C3E50]" />
              ) : (
                <Circle className="h-5 w-5 text-slate-300" />
              )}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-[#2C3E50]">{s.label}</p>
              <p className="break-all font-mono text-xs text-slate-600">
                {s.detail || ' '}
              </p>
            </div>
          </li>
        ))}
      </ol>

      {error ? (
        <div className="rounded-md border border-rose-300 bg-rose-50 p-4 text-sm">
          <p className="font-semibold text-rose-700">
            La cadena de autenticación falló
          </p>
          <p className="mt-1 font-mono text-xs text-rose-900">{error}</p>
        </div>
      ) : null}

      {complaintId ? (
        <div className="rounded-md border-2 border-emerald-300 bg-emerald-50 p-4">
          <p className="text-sm font-semibold text-emerald-900">
            ✓ Reclamo recibido por la SBS
          </p>
          <p className="mt-1 font-mono text-xs text-emerald-900">
            complaint_id={complaintId}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Link
              href={`/demo-journey?complaint_id=${encodeURIComponent(complaintId)}`}
              className="inline-flex items-center gap-2 rounded-md bg-[#002244] px-4 py-2 text-sm font-medium text-white shadow hover:bg-[#002244]/90"
            >
              Ver recepción en SBS
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/fi/banco-demo-001/inbox"
              className="inline-flex items-center gap-2 rounded-md border border-[#2C3E50]/30 bg-white px-4 py-2 text-sm font-medium text-[#2C3E50] hover:bg-slate-50"
            >
              Volver a la bandeja
            </Link>
          </div>
        </div>
      ) : null}
    </div>
  );
}
