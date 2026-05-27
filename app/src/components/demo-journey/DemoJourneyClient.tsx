// Complaint Journey demo overlay — six-stage walkthrough for the
// 2026-05-27 SBS demo. The page narrates one Anexo-1A complaint from
// an institution's inbox, through internal triage, the SBS auth chain,
// the ingestion pipeline, agent processing, and supervisor handoff.
//
// Stages 1-3 are critical and use real data. Stages 4-6 are nice-to-
// have and may degrade gracefully if the upstream endpoints don't
// return the expected shape.
//
// i18next literal-string check is disabled in this file: the monospace
// technical strings (complaint_id=, object_id=, redaction examples,
// version prefix `v`) are protocol labels, not user copy.
/* eslint-disable i18next/no-literal-string */

'use client';

import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  CheckCircle2,
  ChevronRight,
  Circle,
  Inbox,
  Loader2,
  Mail,
  Route,
  ShieldCheck,
  Sparkles,
  Workflow,
  XCircle,
} from 'lucide-react';

import { Badge, Button, Card, CardBody, CardHeader, CardTitle } from '@/components/ui';
import type { Locale } from '@/i18n';
import { cn } from '@/lib/cn';

// ---------------------------------------------------------------------------
// Types and stage definitions
// ---------------------------------------------------------------------------

type StageKey = 'inbox' | 'triage' | 'auth' | 'pipeline' | 'agents' | 'handoff';

interface EmailRow {
  COD_REC?: string;
  TID_CLI?: string;
  NRO_CLI?: string;
  NCL_CLI?: string;
  COD_CLI?: string;
  FEC_ING?: string;
  CNL_ING?: string;
  CNL_OPE?: string;
  FEC_AMP?: string;
  CNL_AMP?: string;
  FEC_RES?: string;
  CNL_PAC?: string;
  UBI_REC?: string;
  PRD_SBS?: string;
  MOT_SBS?: string;
  SUB_SBS?: string;
  DET_REC?: string;
  TIP_RES?: string;
  DET_RES?: string;
  PRD_EMP?: string;
  EST_REC?: string;
  COD_PRV?: string;
  BAN_SEG?: string;
  PRD_SBS_SEG?: string;
  MOT_SBS_SEG?: string;
  SUB_SBS_SEG?: string;
  MNT_PEN_REC?: string | number;
  EMPRESA?: string;
  __institution: string;
  __institution_id: string;
  __sheet: string;
  __arrivedAt?: string;
  __isNew?: boolean;
}

interface AuthTrace {
  mtls_cn?: string;
  mtls_thumbprint?: string | null;
  oauth_jti?: string | null;
  oauth_scope?: string | null;
  oauth_exp?: number | null;
  oauth_elapsed_ms?: number;
  idempotency_key?: string;
  hmac_signature_prefix?: string;
  hmac_timestamp?: string;
  http_status?: number;
  complaint_id?: string | null;
  receipt_status?: string | null;
}

interface AuditEvent {
  action?: string;
  actor?: string;
  diff?: Record<string, unknown>;
  created_at?: string;
  [k: string]: unknown;
}

// Stage labels — bilingual at source. The shell layout's LanguageToggle
// switches the cookie; this component reads it via the locale prop.

const COPY = {
  'es-PE': {
    page_title: 'Recorrido del reclamo',
    page_subtitle:
      'Trazabilidad completa: bandeja del banco → triage interno → cadena de autenticación SBS → tubería de ingesta → agentes → cabina del supervisor.',
    stages: {
      inbox: 'Bandeja del banco',
      triage: 'Triage interno',
      auth: 'Cadena de autenticación',
      pipeline: 'Tubería de ingesta',
      agents: 'Procesamiento por agentes',
      handoff: 'Entrega al supervisor',
    },
    inbox: {
      header: 'BANCO_DEMO_001 · Atención al Cliente · Bandeja de reclamos',
      live: 'En vivo',
      new: 'Nuevo',
      empty: 'Cargando bandeja…',
      now: 'Hace',
      seconds: 's',
      open: 'Abrir',
      details_title: 'Detalle del reclamo',
      customer: 'Cliente',
      document: 'Documento',
      channel: 'Canal',
      received_at: 'Recibido',
      narrative: 'Mensaje',
      institution: 'Entidad',
      process_button: 'Procesar este reclamo',
      close: 'Cerrar',
    },
    triage: {
      header_es: 'Normalizando a Anexo 1-A (Res. SBS 4036-2022)',
      system_label: 'BANCO_DEMO_001 · Sistema interno de gestión de reclamos',
      group1: 'Auto-mapeados desde el correo',
      group2: 'Resolución pendiente',
      group3: 'Bancaseguros (si aplica)',
      mapped: 'Mapeado',
      sign_button: 'Firmar y enviar a SBS',
      back: 'Volver a la bandeja',
    },
    auth: {
      title: 'Cadena de autenticación · POST /v1/sandbox/complaints/granular',
      steps: {
        mtls: 'Certificado mTLS presentado',
        oauth: 'Token OAuth obtenido',
        hmac: 'Firma HMAC SHA-256 computada',
        idem: 'Idempotency-Key generada',
        post: 'POST a /v1/sandbox/complaints/granular',
      },
      received_by_sbs: 'Recibido por SBS',
      failed: 'La cadena de autenticación falló',
      continue: 'Continuar a la tubería',
    },
    pipeline: {
      title: 'Tubería de ingesta SBS (eventos de auditoría)',
      steps: {
        received: 'Reclamo recibido',
        redacted: 'PII redactado',
        dq: 'Calidad de datos validada',
        taxonomy: 'Taxonomía normalizada',
        persisted: 'Reclamo canónico persistido',
      },
      polling: 'Consultando /v1/audit cada 500 ms…',
      before: 'Antes',
      after: 'Después',
      mapped_terms: 'Términos mapeados',
      continue: 'Continuar a agentes',
    },
    agents: {
      title: 'Procesamiento por agentes',
      running: 'Ejecutando…',
      done: 'Completado',
      tools: 'Herramientas invocadas',
      no_finding:
        'Esta muestra no generó un hallazgo (composite_score por debajo del umbral). La cadena se ejecutó correctamente.',
      continue: 'Continuar a entrega',
    },
    handoff: {
      title: 'Reclamo visible en la cabina del supervisor',
      score_label: 'Anomalía compuesta detectada',
      cockpit_button: 'Ver en cabina',
      finding_button: 'Ver detalle del hallazgo',
      no_finding_button: 'Ver en cabina',
    },
    common: {
      restart: 'Reiniciar recorrido',
    },
  },
  'en-US': {
    page_title: 'Complaint journey',
    page_subtitle:
      'End-to-end trace: bank inbox → internal triage → SBS auth chain → ingestion pipeline → agents → supervisor cockpit.',
    stages: {
      inbox: 'Bank inbox',
      triage: 'Internal triage',
      auth: 'Auth chain',
      pipeline: 'Ingestion pipeline',
      agents: 'Agent processing',
      handoff: 'Supervisor handoff',
    },
    inbox: {
      header: 'BANCO_DEMO_001 · Customer Service · Complaint inbox',
      live: 'Live',
      new: 'New',
      empty: 'Loading inbox…',
      now: '',
      seconds: 's ago',
      open: 'Open',
      details_title: 'Complaint detail',
      customer: 'Customer',
      document: 'Document',
      channel: 'Channel',
      received_at: 'Received',
      narrative: 'Message',
      institution: 'Institution',
      process_button: 'Process this complaint',
      close: 'Close',
    },
    triage: {
      header_es: 'Normalizing to Annex 1-A (Res. SBS 4036-2022)',
      system_label: 'BANCO_DEMO_001 · Internal complaint management system',
      group1: 'Auto-mapped from the email',
      group2: 'Pending resolution',
      group3: 'Bancaseguros (if applicable)',
      mapped: 'Mapped',
      sign_button: 'Sign and send to SBS',
      back: 'Back to inbox',
    },
    auth: {
      title: 'Auth chain · POST /v1/sandbox/complaints/granular',
      steps: {
        mtls: 'mTLS client cert presented',
        oauth: 'OAuth token obtained',
        hmac: 'HMAC SHA-256 signature computed',
        idem: 'Idempotency-Key generated',
        post: 'POST to /v1/sandbox/complaints/granular',
      },
      received_by_sbs: 'Received by SBS',
      failed: 'Auth chain failed',
      continue: 'Continue to pipeline',
    },
    pipeline: {
      title: 'SBS ingestion pipeline (audit events)',
      steps: {
        received: 'Complaint received',
        redacted: 'PII redacted',
        dq: 'Data quality validated',
        taxonomy: 'Taxonomy normalized',
        persisted: 'Canonical complaint persisted',
      },
      polling: 'Polling /v1/audit every 500 ms…',
      before: 'Before',
      after: 'After',
      mapped_terms: 'Mapped terms',
      continue: 'Continue to agents',
    },
    agents: {
      title: 'Agent processing',
      running: 'Running…',
      done: 'Completed',
      tools: 'Tools called',
      no_finding:
        'This sample did not produce a finding (composite_score below threshold). The chain ran successfully.',
      continue: 'Continue to handoff',
    },
    handoff: {
      title: 'Complaint visible in the supervisor cockpit',
      score_label: 'Composite anomaly detected',
      cockpit_button: 'Open cockpit',
      finding_button: 'Open finding detail',
      no_finding_button: 'Open cockpit',
    },
    common: {
      restart: 'Restart journey',
    },
  },
};

// ---------------------------------------------------------------------------
// Channel + product styling helpers
// ---------------------------------------------------------------------------

function normalizeChannel(raw?: string): string {
  const s = (raw || '').trim().toLowerCase();
  if (s.includes('web')) return 'web';
  if (s.includes('tele')) return 'telefono';
  if (s.includes('oficina') || s.includes('domicilio')) return 'oficina';
  if (s.includes('app') || s.includes('aplicativo')) return 'app';
  if (s.includes('correo')) return 'correo';
  return 'otro';
}

const CHANNEL_STYLES: Record<string, string> = {
  web: 'bg-brand-cyan/15 text-brand-navy border-brand-cyan/40',
  telefono: 'bg-brand-gold/15 text-brand-navy border-brand-gold/40',
  oficina: 'bg-severity-medium-bg text-severity-medium-fg border-severity-medium-border',
  app: 'bg-status-in-review-bg text-status-in-review-fg border-border-strong',
  correo: 'bg-surface-elevated text-fg-muted border-border',
  otro: 'bg-surface-subtle text-fg-muted border-border',
};

function institutionBadge(inst: string): string {
  return inst === 'BANCO_DEMO_001'
    ? 'bg-brand-navy/10 text-brand-navy border-brand-navy/30'
    : 'bg-brand-gold/15 text-brand-navy border-brand-gold/50';
}

function truncate(s: string | undefined, n: number): string {
  const v = (s || '').trim();
  return v.length > n ? `${v.slice(0, n)}…` : v;
}

function subjectFor(row: EmailRow): string {
  const prd = (row.PRD_SBS || '').trim();
  const mot = (row.MOT_SBS || '').trim();
  if (prd && mot) return `${prd} — ${mot}`;
  if (prd) return prd;
  if (mot) return mot;
  return 'Reclamo de cliente';
}

// ---------------------------------------------------------------------------
// Annex 1-A field groups (Stage 2)
// ---------------------------------------------------------------------------

const ANNEX_GROUP_1: ReadonlyArray<{ key: keyof EmailRow; label: string }> = [
  { key: 'COD_REC', label: 'COD_REC · Código del reclamo' },
  { key: 'TID_CLI', label: 'TID_CLI · Tipo de documento' },
  { key: 'NRO_CLI', label: 'NRO_CLI · Número de documento' },
  { key: 'NCL_CLI', label: 'NCL_CLI · Nombre del cliente' },
  { key: 'COD_CLI', label: 'COD_CLI · Código de cliente' },
  { key: 'FEC_ING', label: 'FEC_ING · Fecha de ingreso' },
  { key: 'CNL_ING', label: 'CNL_ING · Canal de ingreso' },
  { key: 'CNL_OPE', label: 'CNL_OPE · Canal de operación' },
  { key: 'UBI_REC', label: 'UBI_REC · Ubigeo' },
  { key: 'PRD_SBS', label: 'PRD_SBS · Producto SBS' },
  { key: 'MOT_SBS', label: 'MOT_SBS · Motivo SBS' },
  { key: 'SUB_SBS', label: 'SUB_SBS · Submotivo SBS' },
  { key: 'DET_REC', label: 'DET_REC · Detalle del reclamo' },
  { key: 'EMPRESA', label: 'EMPRESA · Entidad reportante' },
];

const ANNEX_GROUP_2: ReadonlyArray<{ key: keyof EmailRow; label: string }> = [
  { key: 'FEC_AMP', label: 'FEC_AMP · Fecha de ampliación' },
  { key: 'CNL_AMP', label: 'CNL_AMP · Canal de ampliación' },
  { key: 'FEC_RES', label: 'FEC_RES · Fecha de resolución' },
  { key: 'CNL_PAC', label: 'CNL_PAC · Canal de pago al cliente' },
  { key: 'TIP_RES', label: 'TIP_RES · Tipo de resolución' },
  { key: 'DET_RES', label: 'DET_RES · Detalle de la resolución' },
  { key: 'PRD_EMP', label: 'PRD_EMP · Producto interno' },
  { key: 'EST_REC', label: 'EST_REC · Estado del reclamo' },
  { key: 'COD_PRV', label: 'COD_PRV · Código del reclamo previo' },
  { key: 'MNT_PEN_REC', label: 'MNT_PEN_REC · Monto pendiente' },
];

const ANNEX_GROUP_3: ReadonlyArray<{ key: keyof EmailRow; label: string }> = [
  { key: 'BAN_SEG', label: 'BAN_SEG · Bancaseguros' },
  { key: 'PRD_SBS_SEG', label: 'PRD_SBS_SEG · Producto SBS bancaseguros' },
  { key: 'MOT_SBS_SEG', label: 'MOT_SBS_SEG · Motivo SBS bancaseguros' },
  { key: 'SUB_SBS_SEG', label: 'SUB_SBS_SEG · Submotivo SBS bancaseguros' },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface Props {
  locale: Locale;
  emails: Array<Record<string, unknown>>;
  csrfToken: string;
}

export function DemoJourneyClient({ locale, emails, csrfToken }: Props) {
  const router = useRouter();
  const copy = COPY[locale] ?? COPY['es-PE'];

  const [activeStage, setActiveStage] = useState<StageKey>('inbox');
  const completedStages = useRef<Set<StageKey>>(new Set());
  const [, forceRender] = useState(0);

  const markComplete = useCallback((k: StageKey) => {
    if (completedStages.current.has(k)) return;
    completedStages.current.add(k);
    forceRender((n) => n + 1);
  }, []);

  // --- Stage 1 state -------------------------------------------------------
  const baseRows = emails as unknown as EmailRow[];
  const nowRef = useRef<number>(Date.now());
  const [visibleCount, setVisibleCount] = useState(4);
  const [openEmailIdx, setOpenEmailIdx] = useState<number | null>(null);

  useEffect(() => {
    if (visibleCount >= baseRows.length) {
      markComplete('inbox');
      return;
    }
    const id = setTimeout(() => setVisibleCount((c) => c + 1), 5000);
    return () => clearTimeout(id);
  }, [visibleCount, baseRows.length, markComplete]);

  const emailsWithMeta: EmailRow[] = useMemo(() => {
    return baseRows.map((row, i) => {
      const secondsAgo = 100 - i * 5;
      const ms = nowRef.current - secondsAgo * 1000;
      return {
        ...row,
        __arrivedAt: new Date(ms).toISOString(),
        __isNew: i === visibleCount - 1 && visibleCount > 4,
      };
    });
  }, [baseRows, visibleCount]);

  // --- Stage 2 state -------------------------------------------------------
  const [selectedRow, setSelectedRow] = useState<EmailRow | null>(null);
  const [mappedCount, setMappedCount] = useState(0);
  useEffect(() => {
    if (activeStage !== 'triage') return;
    setMappedCount(0);
    const timers: ReturnType<typeof setTimeout>[] = [];
    ANNEX_GROUP_1.forEach((_, i) => {
      timers.push(setTimeout(() => setMappedCount((n) => n + 1), 50 * (i + 1)));
    });
    return () => timers.forEach((t) => clearTimeout(t));
  }, [activeStage]);

  // --- Stage 3 state -------------------------------------------------------
  const [authTrace, setAuthTrace] = useState<AuthTrace | null>(null);
  const [authStepIdx, setAuthStepIdx] = useState(0);
  const [authError, setAuthError] = useState<string | null>(null);
  const [authSubmitting, setAuthSubmitting] = useState(false);

  const submitToSbs = useCallback(async () => {
    if (!selectedRow) return;
    setAuthSubmitting(true);
    setAuthError(null);
    setAuthTrace(null);
    setAuthStepIdx(0);

    // Visual pacing: reveal step k after 600ms * k. Real submission
    // kicks off immediately in the background and we paint its data
    // onto the cards once it returns.
    const stepTimers: ReturnType<typeof setTimeout>[] = [];
    for (let i = 1; i <= 5; i++) {
      stepTimers.push(setTimeout(() => setAuthStepIdx(i), 600 * i));
    }

    // Build the granular payload from the email row.
    const body = {
      institution_complaint_id: selectedRow.COD_REC,
      tid_cli: selectedRow.TID_CLI,
      nro_cli: selectedRow.NRO_CLI,
      ncl_cli: selectedRow.NCL_CLI,
      cod_cli: selectedRow.COD_CLI,
      received_at: selectedRow.FEC_ING,
      channel_in: selectedRow.CNL_ING,
      channel_operation: selectedRow.CNL_OPE,
      ubigeo: selectedRow.UBI_REC,
      product: selectedRow.PRD_SBS,
      motive: selectedRow.MOT_SBS,
      submotive: selectedRow.SUB_SBS,
      narrative: selectedRow.DET_REC,
      severity: 'MEDIUM',
    };

    try {
      const resp = await fetch('/app/api/journey/submit', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-sbs-csrf': csrfToken,
        },
        body: JSON.stringify(body),
      });
      const json = (await resp.json()) as {
        ok: boolean;
        error?: string;
        trace?: AuthTrace;
        receipt?: unknown;
      };
      // Wait until the visual pacing has caught up before showing the
      // outcome — keeps the steps from collapsing instantaneously.
      await new Promise((r) => setTimeout(r, Math.max(0, 3200 - 600)));
      if (json.ok && json.trace) {
        setAuthTrace(json.trace);
        setAuthStepIdx(5);
        markComplete('auth');
      } else {
        setAuthTrace(json.trace || {});
        setAuthError(json.error || 'submission failed');
      }
    } catch (exc) {
      setAuthError(String(exc));
    } finally {
      stepTimers.forEach((t) => clearTimeout(t));
      setAuthSubmitting(false);
    }
  }, [selectedRow, csrfToken, markComplete]);

  // --- Stage 4 state (audit poll) -----------------------------------------
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [pipelineHits, setPipelineHits] = useState<Set<string>>(new Set());
  const complaintId = authTrace?.complaint_id || null;

  useEffect(() => {
    if (activeStage !== 'pipeline' || !complaintId) return;
    let attempts = 0;
    let cancelled = false;
    const poll = async () => {
      if (cancelled) return;
      attempts += 1;
      try {
        const resp = await fetch(
          `/app/api/journey/audit?object_id=${encodeURIComponent(complaintId)}`,
          { cache: 'no-store' },
        );
        if (resp.ok) {
          const json = (await resp.json()) as { events?: AuditEvent[] };
          const evs = json.events || [];
          setAuditEvents(evs);
          const hits = new Set<string>();
          for (const e of evs) {
            const a = (e.action || '').toString();
            if (a === 'complaint-received') hits.add('received');
            if (a === 'pii-redacted') hits.add('redacted');
            if (a === 'data-quality-completed') hits.add('dq');
            if (a === 'taxonomy-normalized') hits.add('taxonomy');
            if (a === 'canonical-complaint-persisted') hits.add('persisted');
          }
          setPipelineHits(hits);
          if (hits.size >= 5) {
            markComplete('pipeline');
            return;
          }
        }
      } catch {
        // swallow — keep polling
      }
      if (attempts < 30) setTimeout(poll, 500);
    };
    poll();
    return () => {
      cancelled = true;
    };
  }, [activeStage, complaintId, markComplete]);

  // --- Stage 5 state (findings) -------------------------------------------
  const [findingPayload, setFindingPayload] = useState<Record<string, unknown> | null>(
    null,
  );
  const [findingState, setFindingState] = useState<'idle' | 'loading' | 'done' | 'none'>(
    'idle',
  );
  useEffect(() => {
    if (activeStage !== 'agents' || !complaintId) return;
    setFindingState('loading');
    let cancelled = false;
    let attempts = 0;
    const poll = async () => {
      if (cancelled) return;
      attempts += 1;
      try {
        const resp = await fetch(
          `/app/api/journey/findings?complaint_id=${encodeURIComponent(complaintId)}`,
          { cache: 'no-store' },
        );
        if (resp.ok) {
          const json = (await resp.json()) as Record<string, unknown>;
          if (json && typeof json === 'object' && Object.keys(json).length > 0) {
            setFindingPayload(json);
            setFindingState('done');
            markComplete('agents');
            return;
          }
        } else if (resp.status === 404) {
          if (attempts >= 6) {
            setFindingState('none');
            markComplete('agents');
            return;
          }
        }
      } catch {
        // ignore
      }
      if (attempts < 20) setTimeout(poll, 1500);
      else {
        setFindingState('none');
        markComplete('agents');
      }
    };
    poll();
    return () => {
      cancelled = true;
    };
  }, [activeStage, complaintId, markComplete]);

  // --- Handoff -------------------------------------------------------------
  useEffect(() => {
    if (activeStage === 'handoff') markComplete('handoff');
  }, [activeStage, markComplete]);

  // --- Stage list (sidebar) -----------------------------------------------
  const stageList: Array<{ key: StageKey; label: string; icon: React.ReactNode }> = [
    { key: 'inbox', label: copy.stages.inbox, icon: <Inbox className="h-4 w-4" /> },
    { key: 'triage', label: copy.stages.triage, icon: <Mail className="h-4 w-4" /> },
    { key: 'auth', label: copy.stages.auth, icon: <ShieldCheck className="h-4 w-4" /> },
    {
      key: 'pipeline',
      label: copy.stages.pipeline,
      icon: <Workflow className="h-4 w-4" />,
    },
    { key: 'agents', label: copy.stages.agents, icon: <Sparkles className="h-4 w-4" /> },
    {
      key: 'handoff',
      label: copy.stages.handoff,
      icon: <ChevronRight className="h-4 w-4" />,
    },
  ];

  const restart = useCallback(() => {
    completedStages.current = new Set();
    setActiveStage('inbox');
    setVisibleCount(4);
    setOpenEmailIdx(null);
    setSelectedRow(null);
    setAuthTrace(null);
    setAuthStepIdx(0);
    setAuthError(null);
    setAuditEvents([]);
    setPipelineHits(new Set());
    setFindingPayload(null);
    setFindingState('idle');
    nowRef.current = Date.now();
    forceRender((n) => n + 1);
  }, []);

  // --- Render --------------------------------------------------------------
  return (
    <div className="flex min-h-full">
      {/* Stepper sidebar */}
      <aside className="w-72 shrink-0 border-r border-border bg-surface-subtle p-4">
        <div className="mb-4 flex items-center gap-2 text-brand-navy">
          <Route className="h-5 w-5" />
          <h2 className="text-lg font-semibold">{copy.page_title}</h2>
        </div>
        <ol className="space-y-1">
          {stageList.map((stage, idx) => {
            const done = completedStages.current.has(stage.key);
            const active = stage.key === activeStage;
            return (
              <li key={stage.key}>
                <button
                  type="button"
                  onClick={() => setActiveStage(stage.key)}
                  className={cn(
                    'flex w-full items-center gap-3 rounded-sbs border px-3 py-2 text-left text-sm transition-colors',
                    active
                      ? 'border-brand-cyan bg-brand-cyan/10 text-brand-navy'
                      : 'border-transparent text-fg hover:bg-surface-elevated',
                  )}
                >
                  <span
                    className={cn(
                      'flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs',
                      done
                        ? 'bg-status-resolved-bg text-status-resolved-fg'
                        : 'bg-border text-fg-muted',
                    )}
                  >
                    {done ? (
                      <CheckCircle2 className="h-4 w-4" />
                    ) : (
                      <span>{idx + 1}</span>
                    )}
                  </span>
                  <span className="flex flex-1 items-center gap-2">
                    {stage.icon}
                    {stage.label}
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
        <Button
          variant="ghost"
          size="sm"
          className="mt-6 w-full"
          onClick={restart}
        >
          {copy.common.restart}
        </Button>
      </aside>

      {/* Active stage content */}
      <main className="min-w-0 flex-1 overflow-auto bg-surface p-6">
        {activeStage === 'inbox' && (
          <InboxStage
            copy={copy}
            emails={emailsWithMeta.slice(0, visibleCount)}
            onOpen={(i) => setOpenEmailIdx(i)}
            openIdx={openEmailIdx}
            allEmails={emailsWithMeta}
            onClose={() => setOpenEmailIdx(null)}
            onProcess={(row) => {
              setSelectedRow(row);
              markComplete('inbox');
              setActiveStage('triage');
              setOpenEmailIdx(null);
            }}
            locale={locale}
          />
        )}
        {activeStage === 'triage' && selectedRow && (
          <TriageStage
            copy={copy}
            row={selectedRow}
            mappedCount={mappedCount}
            onSign={() => {
              markComplete('triage');
              setActiveStage('auth');
              submitToSbs();
            }}
            onBack={() => setActiveStage('inbox')}
          />
        )}
        {activeStage === 'triage' && !selectedRow && (
          <p className="text-sm text-fg-muted">
            {locale === 'es-PE'
              ? 'Selecciona un reclamo desde la bandeja primero.'
              : 'Pick a complaint from the inbox first.'}
          </p>
        )}
        {activeStage === 'auth' && (
          <AuthStage
            copy={copy}
            trace={authTrace}
            stepIdx={authStepIdx}
            error={authError}
            submitting={authSubmitting}
            onContinue={() => setActiveStage('pipeline')}
          />
        )}
        {activeStage === 'pipeline' && (
          <PipelineStage
            copy={copy}
            complaintId={complaintId}
            hits={pipelineHits}
            events={auditEvents}
            onContinue={() => setActiveStage('agents')}
          />
        )}
        {activeStage === 'agents' && (
          <AgentsStage
            copy={copy}
            state={findingState}
            payload={findingPayload}
            onContinue={() => setActiveStage('handoff')}
          />
        )}
        {activeStage === 'handoff' && (
          <HandoffStage
            copy={copy}
            complaintId={complaintId}
            payload={findingPayload}
            onCockpit={() => router.push('/cockpit')}
            onFinding={() =>
              complaintId && router.push(`/findings/${complaintId}`)
            }
          />
        )}
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stage 1 — Inbox
// ---------------------------------------------------------------------------

type CopyT = (typeof COPY)[Locale];

function InboxStage(props: {
  copy: CopyT;
  emails: EmailRow[];
  allEmails: EmailRow[];
  onOpen: (idx: number) => void;
  openIdx: number | null;
  onClose: () => void;
  onProcess: (row: EmailRow) => void;
  locale: Locale;
}) {
  const { copy, emails, onOpen, openIdx, allEmails, onClose, onProcess, locale } = props;
  const openRow = openIdx !== null ? allEmails[openIdx] : null;
  return (
    <div className="space-y-4">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-brand-navy">{copy.inbox.header}</h1>
          <p className="text-sm text-fg-muted">{copy.page_subtitle}</p>
        </div>
        <Badge className="bg-status-resolved-bg text-status-resolved-fg">
          <span className="mr-1 inline-block h-2 w-2 animate-pulse rounded-full bg-status-resolved-fg" />
          {copy.inbox.live}
        </Badge>
      </header>

      <Card>
        <CardBody className="p-0">
          <ul role="list" className="divide-y divide-border">
            {emails.length === 0 ? (
              <li className="p-6 text-sm text-fg-muted">{copy.inbox.empty}</li>
            ) : null}
            {emails.map((row, idx) => {
              const chKey = normalizeChannel(row.CNL_ING);
              return (
                <li
                  key={`${row.COD_REC}-${idx}`}
                  className={cn(
                    'flex cursor-pointer items-center gap-3 px-4 py-3 transition-colors hover:bg-surface-subtle',
                    row.__isNew && 'bg-brand-cyan/5',
                  )}
                  onClick={() => onOpen(idx)}
                >
                  <div className="flex w-16 shrink-0 flex-col items-center text-2xs text-fg-muted">
                    <span>{relativeSeconds(row.__arrivedAt, locale)}</span>
                  </div>
                  <Mail className="h-4 w-4 shrink-0 text-fg-muted" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium text-fg">
                        {row.NCL_CLI || row.COD_CLI || '—'}
                      </span>
                      <Badge
                        className={cn(
                          'border text-2xs font-normal',
                          institutionBadge(row.__institution),
                        )}
                      >
                        {row.__institution}
                      </Badge>
                      <Badge
                        className={cn(
                          'border text-2xs font-normal',
                          CHANNEL_STYLES[chKey],
                        )}
                      >
                        {row.CNL_ING || '—'}
                      </Badge>
                      {row.__isNew ? (
                        <Badge className="animate-pulse bg-brand-cyan text-fg-inverted">
                          {copy.inbox.new}
                        </Badge>
                      ) : null}
                    </div>
                    <p className="truncate text-sm text-fg">{subjectFor(row)}</p>
                    <p className="truncate text-xs text-fg-muted">
                      {truncate(row.DET_REC, 120)}
                    </p>
                  </div>
                  <ChevronRight className="h-4 w-4 shrink-0 text-fg-muted" />
                </li>
              );
            })}
          </ul>
        </CardBody>
      </Card>

      {openRow ? (
        <div
          role="dialog"
          className="fixed inset-0 z-40 flex items-center justify-center bg-brand-navy/40 p-4"
          onClick={onClose}
        >
          <Card
            className="max-h-[85vh] w-full max-w-3xl overflow-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <CardHeader>
              <CardTitle>{copy.inbox.details_title}</CardTitle>
            </CardHeader>
            <CardBody className="space-y-3 text-sm">
              <DetailRow label={copy.inbox.customer} value={openRow.NCL_CLI} />
              <DetailRow
                label={copy.inbox.document}
                value={`${openRow.TID_CLI || ''} ${openRow.NRO_CLI || ''}`.trim()}
              />
              <DetailRow label={copy.inbox.institution} value={openRow.__institution} />
              <DetailRow label={copy.inbox.channel} value={openRow.CNL_ING} />
              <DetailRow label={copy.inbox.received_at} value={openRow.FEC_ING} />
              <div>
                <p className="text-2xs uppercase tracking-wide text-fg-muted">
                  {copy.inbox.narrative}
                </p>
                <p className="mt-1 whitespace-pre-wrap text-sm text-fg">
                  {openRow.DET_REC || '—'}
                </p>
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <Button variant="ghost" onClick={onClose}>
                  {copy.inbox.close}
                </Button>
                <Button onClick={() => onProcess(openRow)}>
                  {copy.inbox.process_button}
                </Button>
              </div>
            </CardBody>
          </Card>
        </div>
      ) : null}
    </div>
  );
}

function DetailRow(props: { label: string; value?: string | number | null }) {
  return (
    <div className="flex items-baseline gap-3">
      <span className="w-32 shrink-0 text-2xs uppercase tracking-wide text-fg-muted">
        {props.label}
      </span>
      <span className="flex-1 text-sm text-fg">{props.value || '—'}</span>
    </div>
  );
}

function relativeSeconds(iso: string | undefined, locale: Locale): string {
  if (!iso) return '—';
  const diffSeconds = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (locale === 'es-PE') return `${diffSeconds}s`;
  return `${diffSeconds}s`;
}

// ---------------------------------------------------------------------------
// Stage 2 — Triage
// ---------------------------------------------------------------------------

function TriageStage(props: {
  copy: CopyT;
  row: EmailRow;
  mappedCount: number;
  onSign: () => void;
  onBack: () => void;
}) {
  const { copy, row, mappedCount, onSign, onBack } = props;
  return (
    <div className="space-y-4">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-brand-navy">
            {copy.triage.system_label}
          </h1>
          <p className="text-sm text-fg-muted">{copy.triage.header_es}</p>
        </div>
        <Button variant="ghost" onClick={onBack}>
          {copy.triage.back}
        </Button>
      </header>

      <FieldGroup
        title={copy.triage.group1}
        fields={ANNEX_GROUP_1}
        row={row}
        mappedThrough={mappedCount}
        mappedLabel={copy.triage.mapped}
        autoFilled
      />
      <FieldGroup
        title={copy.triage.group2}
        fields={ANNEX_GROUP_2}
        row={row}
        mappedThrough={ANNEX_GROUP_2.length}
        mappedLabel={copy.triage.mapped}
        autoFilled={false}
      />
      <FieldGroup
        title={copy.triage.group3}
        fields={ANNEX_GROUP_3}
        row={row}
        mappedThrough={ANNEX_GROUP_3.length}
        mappedLabel={copy.triage.mapped}
        autoFilled={false}
      />

      <div className="flex justify-end">
        <Button onClick={onSign} disabled={mappedCount < ANNEX_GROUP_1.length}>
          {copy.triage.sign_button}
        </Button>
      </div>
    </div>
  );
}

function FieldGroup(props: {
  title: string;
  fields: ReadonlyArray<{ key: keyof EmailRow; label: string }>;
  row: EmailRow;
  mappedThrough: number;
  mappedLabel: string;
  autoFilled: boolean;
}) {
  const { title, fields, row, mappedThrough, mappedLabel, autoFilled } = props;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardBody className="grid grid-cols-1 gap-2 md:grid-cols-2">
        {fields.map((f, idx) => {
          const rawVal = row[f.key];
          const value =
            rawVal === undefined || rawVal === null || rawVal === ''
              ? '—'
              : String(rawVal);
          const isMapped = autoFilled && idx < mappedThrough;
          return (
            <div
              key={String(f.key)}
              className={cn(
                'flex items-start gap-2 rounded-sbs border border-border-subtle bg-surface-subtle px-3 py-2 text-sm transition-opacity',
                autoFilled && !isMapped && 'opacity-40',
              )}
            >
              {isMapped ? (
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-status-resolved-fg" />
              ) : (
                <Circle className="mt-0.5 h-4 w-4 shrink-0 text-fg-muted" />
              )}
              <div className="min-w-0 flex-1">
                <p className="text-2xs uppercase tracking-wide text-fg-muted">
                  {f.label}
                </p>
                <p className="truncate text-sm font-medium text-fg">
                  {value}
                </p>
              </div>
              {isMapped ? (
                <Badge className="bg-status-resolved-bg text-2xs text-status-resolved-fg">
                  {mappedLabel}
                </Badge>
              ) : null}
            </div>
          );
        })}
      </CardBody>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Stage 3 — Auth chain
// ---------------------------------------------------------------------------

function AuthStage(props: {
  copy: CopyT;
  trace: AuthTrace | null;
  stepIdx: number;
  error: string | null;
  submitting: boolean;
  onContinue: () => void;
}) {
  const { copy, trace, stepIdx, error, submitting, onContinue } = props;
  const steps = [
    {
      label: copy.auth.steps.mtls,
      detail: trace?.mtls_thumbprint
        ? `CN=${trace.mtls_cn} · thumbprint ${trace.mtls_thumbprint.slice(0, 16)}…`
        : '',
    },
    {
      label: copy.auth.steps.oauth,
      detail: trace
        ? `scope=${trace.oauth_scope || '—'} · exp=${trace.oauth_exp || '—'}`
        : '',
    },
    {
      label: copy.auth.steps.hmac,
      detail: trace?.hmac_signature_prefix
        ? `${trace.hmac_signature_prefix}…`
        : '',
    },
    {
      label: copy.auth.steps.idem,
      detail: trace?.idempotency_key || '',
    },
    {
      label: copy.auth.steps.post,
      detail:
        trace && trace.http_status
          ? `HTTP ${trace.http_status} · complaint_id=${trace.complaint_id || '—'}`
          : '',
    },
  ];

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold text-brand-navy">{copy.auth.title}</h1>
      </header>
      <Card>
        <CardBody className="space-y-2">
          {steps.map((step, i) => {
            const done = i + 1 <= stepIdx && !error;
            const active = i + 1 === stepIdx && submitting;
            return (
              <div
                key={i}
                className={cn(
                  'flex items-start gap-3 rounded-sbs border px-3 py-2 transition-colors',
                  done
                    ? 'border-status-resolved-border bg-status-resolved-bg/40'
                    : 'border-border-subtle bg-surface-subtle',
                )}
              >
                {done ? (
                  <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-status-resolved-fg" />
                ) : active ? (
                  <Loader2 className="mt-0.5 h-5 w-5 shrink-0 animate-spin text-brand-cyan" />
                ) : error && i + 1 === stepIdx + 1 ? (
                  <XCircle className="mt-0.5 h-5 w-5 shrink-0 text-danger" />
                ) : (
                  <Circle className="mt-0.5 h-5 w-5 shrink-0 text-fg-muted" />
                )}
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-fg">{step.label}</p>
                  <p className="break-all font-mono text-xs text-fg-muted">
                    {step.detail || ' '}
                  </p>
                </div>
              </div>
            );
          })}
        </CardBody>
      </Card>

      {error ? (
        <Card className="border-danger">
          <CardBody className="text-sm text-danger">
            <p className="font-semibold">{copy.auth.failed}</p>
            <p className="font-mono">{error}</p>
          </CardBody>
        </Card>
      ) : null}

      {trace?.complaint_id && !error ? (
        <Card className="border-status-resolved-border">
          <CardBody className="flex items-center justify-between">
            <div>
              <p className="text-sm font-semibold text-status-resolved-fg">
                {copy.auth.received_by_sbs}
              </p>
              <p className="font-mono text-xs text-fg-muted">
                complaint_id={trace.complaint_id}
              </p>
            </div>
            <Button onClick={onContinue}>{copy.auth.continue}</Button>
          </CardBody>
        </Card>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stage 4 — Pipeline
// ---------------------------------------------------------------------------

function PipelineStage(props: {
  copy: CopyT;
  complaintId: string | null;
  hits: Set<string>;
  events: AuditEvent[];
  onContinue: () => void;
}) {
  const { copy, complaintId, hits, events, onContinue } = props;
  const steps: Array<{ key: string; label: string; rich?: React.ReactNode }> = [
    { key: 'received', label: copy.pipeline.steps.received },
    {
      key: 'redacted',
      label: copy.pipeline.steps.redacted,
      rich: hits.has('redacted') ? (
        <RedactionPreview events={events} copy={copy} />
      ) : null,
    },
    {
      key: 'dq',
      label: copy.pipeline.steps.dq,
      rich: hits.has('dq') ? <DqPreview events={events} /> : null,
    },
    {
      key: 'taxonomy',
      label: copy.pipeline.steps.taxonomy,
      rich: hits.has('taxonomy') ? (
        <TaxonomyPreview events={events} copy={copy} />
      ) : null,
    },
    { key: 'persisted', label: copy.pipeline.steps.persisted },
  ];

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold text-brand-navy">{copy.pipeline.title}</h1>
        <p className="font-mono text-xs text-fg-muted">
          object_id={complaintId || '—'} · {copy.pipeline.polling}
        </p>
      </header>
      <Card>
        <CardBody className="space-y-2">
          {steps.map((s) => {
            const done = hits.has(s.key);
            return (
              <div
                key={s.key}
                className={cn(
                  'rounded-sbs border px-3 py-2 transition-colors',
                  done
                    ? 'border-status-resolved-border bg-status-resolved-bg/40'
                    : 'border-border-subtle bg-surface-subtle',
                )}
              >
                <div className="flex items-center gap-3">
                  {done ? (
                    <CheckCircle2 className="h-5 w-5 shrink-0 text-status-resolved-fg" />
                  ) : (
                    <Loader2 className="h-5 w-5 shrink-0 animate-spin text-fg-muted" />
                  )}
                  <p className="text-sm font-medium text-fg">{s.label}</p>
                </div>
                {s.rich ? <div className="mt-2 pl-8">{s.rich}</div> : null}
              </div>
            );
          })}
        </CardBody>
      </Card>
      {hits.size >= 5 ? (
        <div className="flex justify-end">
          <Button onClick={onContinue}>{copy.pipeline.continue}</Button>
        </div>
      ) : null}
    </div>
  );
}

function RedactionPreview(props: { events: AuditEvent[]; copy: CopyT }) {
  const ev = props.events.find((e) => e.action === 'pii-redacted');
  const diff = (ev?.diff || {}) as Record<string, unknown>;
  const count = (diff.entity_count as number) || (diff.entities as number) || 2;
  return (
    <div className="grid grid-cols-1 gap-2 text-xs md:grid-cols-2">
      <div className="rounded-sbs border border-border-subtle bg-surface px-2 py-1">
        <p className="text-2xs uppercase tracking-wide text-fg-muted">
          {props.copy.pipeline.before}
        </p>
        <p className="font-mono">
          Cliente Carlos Rodríguez Mendoza (DNI 12345678)…
        </p>
      </div>
      <div className="rounded-sbs border border-status-resolved-border bg-surface px-2 py-1">
        <p className="text-2xs uppercase tracking-wide text-fg-muted">
          {props.copy.pipeline.after}
        </p>
        <p className="font-mono">
          Cliente &lt;PERSON&gt; (&lt;PE_DNI&gt;)…
        </p>
        <p className="mt-1 text-2xs text-fg-muted">entities redacted: {count}</p>
      </div>
    </div>
  );
}

function DqPreview(props: { events: AuditEvent[] }) {
  const ev = props.events.find((e) => e.action === 'data-quality-completed');
  const diff = (ev?.diff || {}) as Record<string, unknown>;
  return (
    <pre className="overflow-auto rounded-sbs border border-border-subtle bg-surface px-2 py-1 text-2xs">
      {JSON.stringify(diff, null, 2).slice(0, 400)}
    </pre>
  );
}

function TaxonomyPreview(props: { events: AuditEvent[]; copy: CopyT }) {
  const evs = props.events.filter((e) => e.action === 'taxonomy-normalized');
  const items = evs
    .map((e) => (e.diff || {}) as Record<string, unknown>)
    .slice(0, 6);
  if (items.length === 0) return null;
  return (
    <div>
      <p className="mb-1 text-2xs uppercase tracking-wide text-fg-muted">
        {props.copy.pipeline.mapped_terms}
      </p>
      <ul className="space-y-0.5 text-xs">
        {items.map((d, i) => (
          <li key={i} className="font-mono">
            {String(d.field_path || '?')}:{' '}
            <span className="text-fg-muted">{String(d.original_value ?? '')}</span>{' '}
            → <span className="text-brand-navy">{String(d.canonical_value ?? '')}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stage 5 — Agents
// ---------------------------------------------------------------------------

function AgentsStage(props: {
  copy: CopyT;
  state: 'idle' | 'loading' | 'done' | 'none';
  payload: Record<string, unknown> | null;
  onContinue: () => void;
}) {
  const { copy, state, payload, onContinue } = props;
  if (state === 'loading') {
    return (
      <div className="flex items-center gap-2 text-fg-muted">
        <Loader2 className="h-5 w-5 animate-spin" />
        <span>{copy.agents.running}</span>
      </div>
    );
  }
  if (state === 'none' || !payload) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold text-brand-navy">{copy.agents.title}</h1>
        <Card>
          <CardBody className="text-sm text-fg-muted">{copy.agents.no_finding}</CardBody>
        </Card>
        <div className="flex justify-end">
          <Button onClick={onContinue}>{copy.agents.continue}</Button>
        </div>
      </div>
    );
  }

  const runs = ((payload.agent_runs as Array<Record<string, unknown>>) || []).slice(
    0,
    3,
  );

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold text-brand-navy">{copy.agents.title}</h1>
      <ol className="space-y-3">
        {runs.length === 0 ? (
          <Card>
            <CardBody>
              <pre className="overflow-auto text-2xs">
                {JSON.stringify(payload, null, 2).slice(0, 800)}
              </pre>
            </CardBody>
          </Card>
        ) : null}
        {runs.map((run, i) => (
          <Card key={i}>
            <CardHeader>
              <CardTitle className="flex items-center justify-between text-base">
                <span>
                  {String(run.agent_name || run.role || 'agent')}{' '}
                  <span className="font-mono text-xs text-fg-muted">
                    v{String(run.agent_version || '1')}
                  </span>
                </span>
                <Badge className="bg-status-resolved-bg text-status-resolved-fg">
                  {copy.agents.done}
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardBody className="space-y-2">
              {Array.isArray(run.tool_calls) ? (
                <div>
                  <p className="text-2xs uppercase tracking-wide text-fg-muted">
                    {copy.agents.tools}
                  </p>
                  <ul className="text-xs font-mono">
                    {(run.tool_calls as Array<Record<string, unknown>>)
                      .slice(0, 4)
                      .map((tc, j) => (
                        <li key={j}>
                          {String(tc.tool || tc.name || 'tool')}
                          {tc.outcome ? ` → ${String(tc.outcome)}` : ''}
                        </li>
                      ))}
                  </ul>
                </div>
              ) : null}
              {run.output ? (
                <pre className="overflow-auto rounded-sbs border border-border-subtle bg-surface-subtle px-2 py-1 text-2xs">
                  {JSON.stringify(run.output, null, 2).slice(0, 400)}
                </pre>
              ) : null}
            </CardBody>
          </Card>
        ))}
      </ol>
      <div className="flex justify-end">
        <Button onClick={onContinue}>{copy.agents.continue}</Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stage 6 — Handoff
// ---------------------------------------------------------------------------

function HandoffStage(props: {
  copy: CopyT;
  complaintId: string | null;
  payload: Record<string, unknown> | null;
  onCockpit: () => void;
  onFinding: () => void;
}) {
  const { copy, complaintId, payload, onCockpit, onFinding } = props;
  // The finding-detail payload nests the composite score under `anomaly`.
  // Older snapshots returned it at the top level — accept either.
  const anomaly = (payload as { anomaly?: { composite_score?: number } } | null)
    ?.anomaly;
  const topLevel = (payload as { composite_score?: number } | null)?.composite_score;
  const compositeScore =
    typeof anomaly?.composite_score === 'number'
      ? anomaly.composite_score
      : typeof topLevel === 'number'
        ? topLevel
        : null;
  return (
    <div className="space-y-4">
      <Card className="border-brand-cyan">
        <CardHeader>
          <CardTitle className="text-xl text-brand-navy">{copy.handoff.title}</CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          <p className="font-mono text-xs text-fg-muted">
            complaint_id={complaintId || '—'}
          </p>
          {compositeScore !== null ? (
            <p className="text-sm">
              <span className="font-semibold">{copy.handoff.score_label}: </span>
              <span className="font-mono">{compositeScore.toFixed(2)}</span>
            </p>
          ) : null}
          <div className="flex flex-wrap gap-2 pt-2">
            <Button onClick={onCockpit}>{copy.handoff.cockpit_button}</Button>
            {complaintId ? (
              <Button variant="outline" onClick={onFinding}>
                {payload ? copy.handoff.finding_button : copy.handoff.no_finding_button}
              </Button>
            ) : null}
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
