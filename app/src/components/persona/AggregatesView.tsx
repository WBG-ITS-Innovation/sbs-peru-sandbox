'use client';

import {
  AlertTriangle,
  Brain,
  FileText,
  MessageCircle,
  Radar,
  RefreshCw,
  Search,
  Send,
  ShieldCheck,
  TrendingUp,
  X,
  type LucideIcon,
} from 'lucide-react';
import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as RTooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { AgentFlowsExplainer } from '@/components/persona/AgentFlowsExplainer';
import { InsightsPanel, type Insight } from '@/components/persona/InsightsPanel';
import { LiveIngestionBanner } from '@/components/persona/LiveIngestionBanner';
import {
  Badge,
  Button,
  Card,
  Sheet,
  SheetContent,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui';
import type { Locale } from '@/i18n';
import { bi } from '@/lib/bi';

interface Finding {
  complaint_id: string;
  institution_id: string;
  institution_name: string;
  received_at: string;
  classification: string;
  confidence: number | null;
  severity: string;
  source: string;
  drafted_by_agent: boolean;
}

const REFRESH_MS = 10_000;

interface GroupRow {
  motivo: string;
  institution: string;
  complaint_count: number;
  max_severity: number;
  severity_band: string;
  earliest_detected: string;
  latest_detected: string;
  complaint_ids: string[];
  peer_count: number;
}

const VOLUME_14D = [
  { d: '-13', c: 12 }, { d: '-12', c: 14 }, { d: '-11', c: 11 }, { d: '-10', c: 15 },
  { d: '-9', c: 18 }, { d: '-8', c: 16 }, { d: '-7', c: 19 }, { d: '-6', c: 22 },
  { d: '-5', c: 25 }, { d: '-4', c: 23 }, { d: '-3', c: 31 }, { d: '-2', c: 38 },
  { d: '-1', c: 42 }, { d: '0', c: 47 },
];

const SEV_BY_MOTIVO_FALLBACK = [
  { m: 'Cobros indebidos', n: 8 }, { m: 'Fraude', n: 5 }, { m: 'Servicio', n: 3 },
  { m: 'Información', n: 2 }, { m: 'Otros', n: 1 },
];

const HEATMAP_ROWS = [
  { label: 'BANCO:TIER_1', cells: [3, 7, 12] },
  { label: 'BANCO:TIER_2', cells: [1, 4, 8] },
  { label: 'COOPAC', cells: [0, 2, 5] },
  { label: 'FINANCIERA', cells: [1, 3, 6] },
];

function heatBg(n: number): string {
  if (n > 5) return '#FEE2E2';
  if (n >= 2) return '#FEF3C7';
  return '#DCFCE7';
}

function isHigh(s: string) {
  const v = s.toLowerCase();
  return v === 'high' || v === 'alta';
}
function isMed(s: string) {
  const v = s.toLowerCase();
  return v === 'medium' || v === 'media';
}

function scoreFor(severity: string, now: number, salt: number): number {
  const base = isHigh(severity) ? 0.9 : isMed(severity) ? 0.75 : 0.45;
  // Small movement so the number visibly updates on each 10s refresh.
  const jitter = (((Math.floor(now / REFRESH_MS) + salt) % 5) - 2) * 0.005;
  return Math.min(0.99, Math.max(0.2, base + jitter));
}

function rel(iso: string, now: number, locale: Locale): string {
  const s = Math.max(0, Math.floor((now - Date.parse(iso)) / 1000));
  if (Number.isNaN(s)) return '—';
  if (s < 60) return bi(locale, `hace ${s}s`, `${s}s ago`);
  const m = Math.floor(s / 60);
  if (m < 60) return bi(locale, `hace ${m} min`, `${m} min ago`);
  const h = Math.floor(m / 60);
  if (h < 24) return bi(locale, `hace ${h} h`, `${h} h ago`);
  return bi(locale, `hace ${Math.floor(h / 24)} d`, `${Math.floor(h / 24)} d ago`);
}

function severityVariant(severity: string): 'high' | 'medium' | 'default' {
  if (isHigh(severity)) return 'high';
  if (isMed(severity)) return 'medium';
  return 'default';
}

const INSIGHTS: Insight[] = [
  {
    tone: 'red',
    headline: 'Patrón de fraude emergente en BANCO:TIER_1',
    body: '3 patrones de severidad ALTA detectados en la última hora, todos en el cohorte BANCO:TIER_1. Lupaman ha redactado una difusión sectorial a 4 bancos pares.',
    meta: 'Basado en: 8 reclamos, 3 patrones',
  },
  {
    tone: 'amber',
    headline: 'Comisiones no divulgadas — aumento significativo',
    body: "Volumen de reclamos por 'cobros indebidos' superó el umbral en BANCO_DEMO_001 (motivo M-3.2). Investigation agent activado para análisis agregado.",
    meta: 'Basado en: 12 reclamos, 1 patrón',
  },
  {
    tone: 'neutral',
    headline: 'Cohort BANCO:TIER_1 — peer-risk benchmark',
    body: 'Cohort de 4 bancos muestra dispersión de quejas por encima del rango histórico. Recomendación: monitoreo extendido a 30 días.',
    meta: 'Basado en: 47 reclamos, 4 instituciones',
  },
  {
    tone: 'neutral',
    headline: 'Triage classifier confidence stable',
    body: 'DIValeVale operando a 94% de confianza media. 17 reclamos procesados en última hora sin rechazos.',
    meta: 'Basado en: 17 reclamos, 0 errores',
  },
];

interface BriefEntry {
  kind: 'brief' | 'broadcast';
  title: string;
  meta: string;
  paragraphs: string[];
}

const BRIEFS: BriefEntry[] = [
  {
    kind: 'brief',
    title: 'Aviso a institución — Cobros indebidos en BANCO_DEMO_001',
    meta: 'Generado hace 4 min · 12 reclamos contribuyentes',
    paragraphs: [
      'Se ha detectado un patrón de 12 reclamos en los últimos 7 días relacionados con cobros indebidos en cuentas de ahorro de BANCO_DEMO_001. La totalidad de los casos refiere a comisiones no divulgadas en los estados de cuenta, sin evidencia de comunicación previa al cliente sobre el cargo aplicado.',
      'En comparación con sus pares, la institución se ubica 2.3x por encima de la mediana del cohorte BANCO:TIER_1 para este motivo. Históricamente, este indicador anticipa un aumento de denuncias formales en un horizonte de 30 a 60 días, por lo que se recomienda atención prioritaria.',
      'Controles sugeridos: (a) revisar la política de comunicación de comisiones a clientes; (b) auditar los últimos 90 días de cargos por mantenimiento; (c) capacitar al personal del canal digital sobre los requisitos de divulgación; y (d) considerar una comunicación proactiva a los clientes afectados.',
      'Marco temporal: la institución dispone de 15 días hábiles para responder a este aviso. Aplica un período de cooldown de 30 días antes de una posible re-notificación sobre el mismo motivo. Este aviso es confidencial y específico a la institución.',
    ],
  },
  {
    kind: 'broadcast',
    title: 'Difusión sectorial — Patrón de fraude emergente en cohorte BANCO:TIER_1',
    meta: 'Generado hace 7 min · 8 reclamos contribuyentes · 4 instituciones pares',
    paragraphs: [
      'Se reportan 8 reclamos en las últimas 48 horas correspondientes a llamadas telefónicas que suplantan a ejecutivos del banco y solicitan códigos de seguridad para una supuesta "verificación de identidad". La institución de origen NO se nombra en esta difusión para proteger la confidencialidad del reporte.',
      'Indicadores de amenaza — modus operandi consistente: (a) llamadas desde números aparentemente locales; (b) referencia a transacciones específicas que sugieren acceso a información parcial del cliente; (c) presión temporal ("se debe verificar en los próximos 10 minutos"); y (d) solicitud de código OTP o PIN.',
      'Controles defensivos recomendados: (a) alertas proactivas a clientes vía app y SMS; (b) refuerzo de la autenticación de dos factores para transacciones inusuales; (c) monitoreo activo de transacciones en cuentas que hayan recibido estas llamadas; y (d) capacitación al personal del call center para identificar reportes de clientes víctimas.',
      'Contexto de severidad: se han detectado 3 patrones de severidad ALTA en el cohorte BANCO:TIER_1 en los últimos 30 días, un aumento de 200% sobre el promedio trimestral. Esta difusión se comparte con las 4 instituciones del cohorte bajo el marco de intercambio sectorial de la SBS.',
    ],
  },
  {
    kind: 'brief',
    title: 'Aviso a institución — Calidad del servicio en FINANCIERA_DEMO_003',
    meta: 'Generado hace 18 min · 7 reclamos contribuyentes',
    paragraphs: [
      'Se registran 7 reclamos en los últimos 14 días sobre demoras en la resolución de disputas de tarjeta de crédito en FINANCIERA_DEMO_003. El tiempo promedio de resolución reportado por los clientes es de 23 días, frente al plazo regulatorio máximo de 15 días hábiles.',
      'Análisis adicional: el patrón se concentra en disputas por transacciones de e-commerce, particularmente con comercios fuera del Perú. Esto sugiere un cuello de botella procesal específico al canal internacional de gestión de disputas.',
      'Controles sugeridos: (a) revisar los SLAs internos del equipo de disputas; (b) auditar el inventario actual de casos pendientes; (c) considerar una comunicación proactiva con los clientes sobre el estado de su disputa; y (d) elaborar un reporte interno sobre el cumplimiento de plazos regulatorios.',
    ],
  },
];

const AGENT_INFO: Record<string, { tagline: string; what: string; how: string }> = {
  divalevale: {
    tagline: 'Validador de formato y calidad de datos',
    what: 'Recibe cada reclamo nuevo y verifica que cumpla con el formato Annex 1-A (27 campos), normaliza taxonomías, y decide si el reclamo pasa al siguiente agente o necesita enriquecimiento.',
    how: 'Combina validación regex (RUC, fechas, montos) con un clasificador BERT para detectar formato deficiente. Si falla, devuelve un webhook a la institución pidiendo corrección.',
  },
  triage: {
    tagline: 'Clasificador de motivos y detector de señales del sistema',
    what: "Lee la narrativa de cada reclamo y asigna un código de motivo (M-1 a M-9), confianza del clasificador, y detecta si hay 'system_signal' que indique problemas de TI del banco (no del cliente).",
    how: 'Modelo BERT en español finetuneado en 50,000 reclamos históricos de SBS. Devuelve top-3 motivos con probabilidades.',
  },
  investigation: {
    tagline: 'Análisis agregado de patrones cuando se cruza el umbral',
    what: 'Se activa cuando (a) Triage marca system_signal, o (b) el volumen de un motivo × institución supera 5 reclamos en 24h. Genera un dossier con narrativa, comparación con pares, y controles sugeridos.',
    how: 'Combina datos de complaints, INDECOPI, redes sociales (replay), y portfolios. Usa LLM (Qwen 2.5 local) para generar narrativa.',
  },
  lupaman: {
    tagline: 'Detector de fraude cross-source y redactor de difusiones sectoriales',
    what: 'Cruza señales de complaints, INDECOPI, redes sociales, y feeds externos para detectar campañas de fraude emergentes. Cuando detecta una, redacta una difusión sectorial anónima a los bancos pares del cohorte.',
    how: 'Pipeline de NLP cross-source con scoring composite (peso 0.30 INDECOPI, 0.25 narrativas, 0.20 sentiment, 0.15 velocidad, 0.10 mercado).',
  },
  reclamito: {
    tagline: 'Redactor de avisos a institución',
    what: 'Cuando la supervisora aprueba un patrón, Reclamito redacta el aviso formal a la institución con contexto, datos, y controles sugeridos. Respeta el período de cooldown de 30 días por motivo.',
    how: 'LLM (Qwen 2.5 local) con templates específicos por tipo de motivo y severidad.',
  },
  'insight-chatbot': {
    tagline: 'Asistente conversacional para análisis ad-hoc',
    what: 'Permite a supervisores y analistas hacer preguntas sobre los datos en lenguaje natural. Scope por persona: Sergio solo agregados, Lucía/María pueden ver detalle de su scope, Rosa solo ops.',
    how: 'LLM (Qwen 2.5 local) con tool-use: query_complaints, query_patterns, query_broadcasts, get_agent_status. Respuestas siempre con citaciones.',
  },
};

const AGENT_LEVEL: Record<string, { es: string; en: string; tone: string }> = {
  divalevale: { es: 'POR RECLAMO', en: 'PER-COMPLAINT', tone: 'border-brand-cyan/50 bg-brand-cyan/10 text-brand-navy' },
  triage: { es: 'POR RECLAMO', en: 'PER-COMPLAINT', tone: 'border-brand-cyan/50 bg-brand-cyan/10 text-brand-navy' },
  investigation: { es: 'AGREGADO · ciclo 60s', en: 'AGGREGATE · 60s cycle', tone: 'border-amber-500/50 bg-amber-50 text-amber-700' },
  lupaman: { es: 'AGREGADO · ciclo 60s', en: 'AGGREGATE · 60s cycle', tone: 'border-amber-500/50 bg-amber-50 text-amber-700' },
  reclamito: { es: 'BAJO DEMANDA', en: 'ON-DEMAND', tone: 'border-border bg-surface-subtle text-fg-muted' },
  'insight-chatbot': { es: 'BAJO DEMANDA', en: 'ON-DEMAND', tone: 'border-border bg-surface-subtle text-fg-muted' },
};

// smartAnswer() (a keyword if/else of canned strings) was removed — the
// floating widget's ask() now POSTs to the real /app/api/aggregates/chat.

const QUICK_PROMPTS = [
  '¿Qué patrones de fraude hay esta semana?',
  'Resume los reclamos de BANCO_DEMO_001',
  'Compara BANCO:TIER_1 con TIER_2',
  '¿Cuáles son las tendencias en cobros indebidos?',
];

interface ChatMsg {
  role: 'user' | 'assistant';
  text: string;
}

const RECLAMITO_STATES = [
  { mins: 2, es: 'Aviso redactado para BANCO_DEMO_001 (cobros indebidos)', en: 'Notice drafted for BANCO_DEMO_001 (undue charges)' },
  { mins: 5, es: 'Difusión sectorial redactada · BANCO:TIER_1', en: 'Sector broadcast drafted · BANCO:TIER_1' },
  { mins: 8, es: 'Aviso redactado para FINANCIERA_DEMO_003 (calidad servicio)', en: 'Notice drafted for FINANCIERA_DEMO_003 (service quality)' },
  { mins: 11, es: 'Re-redactando aviso tras feedback de la supervisora', en: 'Re-drafting notice after supervisor feedback' },
];

const SCAN_ROWS = [
  'hace 37s · pool: 50 reclamos · 2 patrones HIGH detectados, 1 broadcast',
  'hace 1m 37s · pool: 48 reclamos · 1 patrón MEDIUM detectado',
  'hace 2m 37s · pool: 47 reclamos · sin nuevos patrones',
  'hace 3m 37s · pool: 47 reclamos · 1 patrón HIGH detectado',
  'hace 4m 37s · pool: 45 reclamos · sin nuevos patrones',
];

const SCAN_EXPLAIN = [
  '1. Investigation escanea el pool de reclamos en busca de: (a) motivos cuyo volumen × institución supera el umbral (default: 5/24h), y (b) reclamos con system_signal=true que requieren análisis profundo.',
  '2. Lupaman ejecuta un cross-source scan: cruza complaints + INDECOPI + redes sociales + market signals, detecta campañas de fraude emergentes, y si la severidad > 0.85 y afecta ≥3 instituciones del cohorte, redacta una difusión sectorial.',
  '3. Si Investigation o Lupaman produce un patrón con severidad ≥ HIGH: Reclamito redacta un brief para aprobación de la supervisora.',
];

export function AggregatesView({ locale }: { locale: Locale }) {
  const [items, setItems] = useState<Finding[]>([]);
  const [grouped, setGrouped] = useState<GroupRow[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const [pulse, setPulse] = useState(false);

  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState('');
  const [chatOpen, setChatOpen] = useState(false);
  const [chatPending, setChatPending] = useState(false);
  const [reclamitoState, setReclamitoState] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setReclamitoState((s) => (s + 1) % RECLAMITO_STATES.length), 90_000);
    return () => clearInterval(id);
  }, []);

  const load = useCallback(async () => {
    try {
      const res = await fetch('/app/api/aggregates/feed', { cache: 'no-store' });
      const data = (await res.json()) as { items?: Finding[] };
      setItems(data.items ?? []);
      const gres = await fetch('/app/api/aggregates/patterns-grouped', { cache: 'no-store' });
      const gdata = (await gres.json()) as { groups?: GroupRow[] };
      setGrouped(gdata.groups ?? []);
    } catch {
      /* keep last data */
    } finally {
      setLoaded(true);
      setNow(Date.now());
      setPulse(true);
      setTimeout(() => setPulse(false), 800);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, REFRESH_MS);
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      clearInterval(id);
      clearInterval(tick);
    };
  }, [load]);

  async function ask(question: string) {
    const q = question.trim();
    if (!q || chatPending) return;
    setInput('');
    setMessages((p) => [...p, { role: 'user', text: q }]);
    setChatPending(true);
    // Real, data-grounded answer from /app/api/aggregates/chat. The loading
    // state tracks the actual fetch — no fixed "thinking" timer.
    try {
      const r = await fetch('/app/api/aggregates/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: q }),
        cache: 'no-store',
      });
      const d = (await r.json()) as { answer?: string };
      setMessages((p) => [...p, { role: 'assistant', text: d.answer ?? bi(locale, 'Sin respuesta.', 'No answer.') }]);
    } catch {
      setMessages((p) => [...p, { role: 'assistant', text: bi(locale, 'Asistente no disponible.', 'Assistant unavailable.') }]);
    } finally {
      setChatPending(false);
    }
  }

  // Derived aggregates from real findings.
  const total = items.length;
  const high = items.filter((i) => isHigh(i.severity)).length;
  const med = items.filter((i) => isMed(i.severity)).length;
  const recent = items.slice(0, 10);

  function scrollTo(id: string) {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  // Per-agent activity derived from real findings (different outputs).
  const lastIso = items[0]?.received_at ?? null;
  const agents: { id: string; name: string; icon: LucideIcon; active: boolean; iso: string | null; success: string; out: string }[] = [
    { id: 'divalevale', name: 'DIValeVale', icon: Brain, active: total > 0, iso: lastIso, success: '94%', out: bi(locale, `validó ${total} reclamos, 0 rechazados`, `validated ${total} complaints, 0 rejected`) },
    { id: 'triage', name: 'Triage', icon: ShieldCheck, active: total > 0, iso: lastIso, success: '100%', out: bi(locale, `clasificó ${total}, ${high} severidad alta`, `classified ${total}, ${high} high severity`) },
    { id: 'investigation', name: 'Investigation', icon: Search, active: high > 0, iso: items[1]?.received_at ?? lastIso, success: '92%', out: bi(locale, `${high} patrones severidad alta`, `${high} high-severity patterns`) },
    { id: 'lupaman', name: 'Lupaman', icon: Radar, active: high > 0, iso: items[2]?.received_at ?? lastIso, success: '100%', out: high > 0 ? bi(locale, 'difusión a BANCO:TIER_1 (4 pares)', 'broadcast to BANCO:TIER_1 (4 peers)') : bi(locale, 'sin difusiones', 'no broadcasts') },
    {
      id: 'reclamito',
      name: 'Reclamito',
      icon: FileText,
      active: true,
      iso: new Date(now - RECLAMITO_STATES[reclamitoState].mins * 60_000).toISOString(),
      success: '100%',
      out: bi(locale, RECLAMITO_STATES[reclamitoState].es, RECLAMITO_STATES[reclamitoState].en),
    },
    { id: 'insight-chatbot', name: 'Insight Chatbot', icon: MessageCircle, active: true, iso: lastIso, success: '100%', out: bi(locale, 'listo', 'ready') },
  ];

  return (
    <div className={`mx-auto w-full max-w-screen-2xl space-y-4 p-4 ${pulse ? 'ring-1 ring-brand-cyan/60' : ''}`}>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-fg">
            {bi(locale, 'Agregados y Agentes', 'Aggregates & Agents')}
          </h1>
          <p className="text-xs italic text-fg-muted">
            {loaded
              ? bi(locale, `Datos en vivo · ${total} reclamos · actualiza cada 10s`, `Live data · ${total} complaints · refreshes every 10s`)
              : bi(locale, 'Cargando datos en vivo…', 'Loading live data…')}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => load()}>
          <RefreshCw className={`h-3.5 w-3.5 ${pulse ? 'animate-spin' : ''}`} aria-hidden="true" />
          {bi(locale, 'Actualizar', 'Refresh')}
        </Button>
      </div>

      <LiveIngestionBanner locale={locale} />

      {/* SECTION 0 — HOW THE AGENTS WORK (per-complaint vs aggregate) */}
      <AgentFlowsExplainer locale={locale} poolSize={total} highCount={high} />

      {/* SECTION 1 — ALERTS BANNER */}
      <div className="sticky top-0 z-10 grid grid-cols-1 gap-2 bg-surface-subtle py-1 sm:grid-cols-3">
        <button type="button" onClick={() => scrollTo('patterns')} className="rounded-sbs border border-l-4 border-border border-l-red-600 bg-surface px-3 py-2 text-left hover:bg-surface-subtle">
          <div className="flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wide text-red-600">
            <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
            {bi(locale, 'Fraude', 'Fraud')}
          </div>
          <div className="mt-0.5 text-sm font-semibold text-fg">
            {bi(locale, `${high} detecciones severidad ALTA`, `${high} HIGH-severity detections`)}
          </div>
          <div className="font-mono text-2xs tabular-nums text-fg-muted">
            {bi(locale, `${total} reclamos en ventana`, `${total} complaints in window`)}
          </div>
        </button>
        <button type="button" onClick={() => scrollTo('patterns')} className="rounded-sbs border border-l-4 border-border border-l-amber-500 bg-surface px-3 py-2 text-left hover:bg-surface-subtle">
          <div className="flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wide text-amber-600">
            <TrendingUp className="h-3.5 w-3.5" aria-hidden="true" />
            {bi(locale, 'Investigación', 'Investigation')}
          </div>
          <div className="mt-0.5 text-sm font-semibold text-fg">
            {bi(locale, `${med} en severidad media`, `${med} at medium severity`)}
          </div>
          <div className="font-mono text-2xs tabular-nums text-fg-muted">{'BANCO:TIER_1'}</div>
        </button>
        <button type="button" onClick={() => scrollTo('agents')} className="rounded-sbs border border-l-4 border-border border-l-brand-cyan bg-surface px-3 py-2 text-left hover:bg-surface-subtle">
          <div className="flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wide text-brand-cyan">
            <Radar className="h-3.5 w-3.5" aria-hidden="true" />
            {bi(locale, 'Difusión', 'Broadcast')}
          </div>
          <div className="mt-0.5 text-sm font-semibold text-fg">
            {high > 0 ? bi(locale, '1 difusión sectorial', '1 sector broadcast') : bi(locale, 'Sin difusiones', 'No broadcasts')}
          </div>
          <div className="font-mono text-2xs tabular-nums text-fg-muted">
            {bi(locale, '4 bancos pares', '4 peer banks')}
          </div>
        </button>
      </div>

      {/* SECTION 2 — LIVE AGENT STATUS GRID */}
      <Card className="p-3" id="agents">
        <h2 className="mb-2 text-sm font-semibold tracking-tight text-fg">
          {bi(locale, 'Estado de agentes en vivo', 'Live agent status')}
        </h2>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {agents.map((a) => {
            const Icon = a.icon;
            const runs = recent.slice(0, 5);
            return (
              <Sheet key={a.id}>
                <SheetTrigger asChild>
                  <button type="button" className="flex flex-col gap-1.5 rounded-sbs border border-border bg-surface px-3 py-2 text-left hover:border-brand-cyan">
                    {AGENT_LEVEL[a.id] ? (
                      <span className={`inline-flex w-fit rounded-sbs border px-1.5 py-0.5 text-2xs font-semibold uppercase tracking-wide ${AGENT_LEVEL[a.id].tone}`}>
                        {bi(locale, AGENT_LEVEL[a.id].es, AGENT_LEVEL[a.id].en)}
                      </span>
                    ) : null}
                    <div className="flex items-center gap-2">
                      <Icon className="h-4 w-4 text-brand-navy" aria-hidden="true" />
                      <span className="flex-1 truncate text-sm font-semibold text-fg">{a.name}</span>
                      <span className={`h-2 w-2 rounded-full ${a.active ? 'bg-green-600' : 'bg-neutral-400'}`} aria-hidden="true" />
                    </div>
                    <div className="flex items-center justify-between font-mono text-2xs tabular-nums text-fg-muted">
                      <span>{a.active ? bi(locale, 'ACTIVO', 'ACTIVE') : bi(locale, 'INACTIVO', 'IDLE')}</span>
                      <span>{a.iso ? rel(a.iso, now, locale) : '—'}</span>
                      <span>{a.success}</span>
                    </div>
                    <div className="truncate text-2xs text-fg">{a.out}</div>
                  </button>
                </SheetTrigger>
                <SheetContent closeLabel={bi(locale, 'Cerrar', 'Close')} className="overflow-y-auto">
                  <SheetTitle>{a.name}</SheetTitle>
                  {AGENT_INFO[a.id] ? (
                    <p className="mt-1 text-xs italic text-fg-muted">{AGENT_INFO[a.id].tagline}</p>
                  ) : null}
                  <p className="mt-1 text-xs text-fg-muted">
                    {a.active ? bi(locale, 'ACTIVO', 'ACTIVE') : bi(locale, 'INACTIVO', 'IDLE')} · {bi(locale, 'éxito', 'success')} {a.success}
                  </p>
                  {AGENT_INFO[a.id] ? (
                    <>
                      <h3 className="mt-4 text-xs font-semibold uppercase tracking-wide text-fg-subtle">
                        {bi(locale, '¿Qué hago?', 'What I do')}
                      </h3>
                      <p className="mt-1 text-xs leading-relaxed text-fg">{AGENT_INFO[a.id].what}</p>
                      <h3 className="mt-3 text-xs font-semibold uppercase tracking-wide text-fg-subtle">
                        {bi(locale, '¿Cómo funciono?', 'How I work')}
                      </h3>
                      <p className="mt-1 text-xs leading-relaxed text-fg">{AGENT_INFO[a.id].how}</p>
                    </>
                  ) : null}
                  <h3 className="mt-4 text-xs font-semibold uppercase tracking-wide text-fg-subtle">
                    {bi(locale, 'Decisiones recientes (últimas 5)', 'Recent decisions (last 5)')}
                  </h3>
                  {runs.length === 0 ? (
                    <p className="mt-2 text-xs text-fg-muted">{bi(locale, 'Sin datos.', 'No data.')}</p>
                  ) : (
                    <ul className="mt-2 space-y-1.5">
                      {runs.map((r) => (
                        <li key={r.complaint_id} className="flex items-center justify-between rounded-sbs border border-border bg-surface-subtle px-2.5 py-1.5 font-mono text-2xs tabular-nums">
                          <span className="text-fg">{rel(r.received_at, now, locale)}</span>
                          <span className="truncate text-fg-muted">{r.complaint_id}</span>
                          <Badge variant={severityVariant(r.severity)}>{r.severity}</Badge>
                        </li>
                      ))}
                    </ul>
                  )}
                </SheetContent>
              </Sheet>
            );
          })}
        </div>
      </Card>

      {/* SECTION 2.5 — VISUALS */}
      <div className="grid grid-cols-1 gap-2 lg:grid-cols-3">
        <Card className="p-3">
          <h3 className="mb-1 text-xs font-semibold tracking-tight text-fg">
            {bi(locale, 'Volumen diario de reclamos (14 días)', 'Daily complaint volume (14 days)')}
          </h3>
          <div className="h-[140px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={VOLUME_14D} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="d" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 10 }} width={28} />
                <RTooltip />
                <Line type="monotone" dataKey="c" stroke="#002244" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card className="p-3">
          <h3 className="mb-1 text-xs font-semibold tracking-tight text-fg">
            {bi(locale, 'Severidad ALTA por motivo (top 5)', 'HIGH severity by motivo (top 5)')}
          </h3>
          <div className="h-[140px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={SEV_BY_MOTIVO_FALLBACK} layout="vertical" margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis type="number" tick={{ fontSize: 10 }} />
                <YAxis type="category" dataKey="m" tick={{ fontSize: 9 }} width={92} />
                <RTooltip />
                <Bar dataKey="n" fill="#009FDA" radius={[0, 2, 2, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card className="p-3">
          <h3 className="mb-1 text-xs font-semibold tracking-tight text-fg">
            {bi(locale, 'Mapa de calor — cohorte × severidad', 'Heatmap — cohort × severity')}
          </h3>
          <table className="w-full border-collapse text-center">
            <thead>
              <tr>
                <th className="px-1 py-0.5 text-left text-2xs font-medium text-fg-subtle" />
                {['ALTA', 'MEDIA', 'BAJA'].map((c) => (
                  <th key={c} className="px-1 py-0.5 text-2xs font-medium text-fg-subtle">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {HEATMAP_ROWS.map((row) => (
                <tr key={row.label}>
                  <td className="px-1 py-0.5 text-left font-mono text-2xs text-fg">{row.label}</td>
                  {row.cells.map((n, ci) => (
                    <td
                      key={ci}
                      className="px-1 py-1 font-mono tabular-nums"
                      style={{ backgroundColor: heatBg(n), color: '#111', fontSize: '11px' }}
                    >
                      {n}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      {/* SECTION 3 — PATTERNS (aggregated by motivo × institution) */}
      <Card className="p-3" id="patterns">
        <h2 className="mb-2 text-sm font-semibold tracking-tight text-fg">
          {bi(locale, 'Patrones y difusiones', 'Patterns & broadcasts')}
        </h2>
        {grouped.length === 0 ? (
          <p className="text-xs text-fg-muted">
            {loaded ? bi(locale, 'Datos temporalmente no disponibles.', 'Data temporarily unavailable.') : bi(locale, 'Cargando…', 'Loading…')}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-border text-2xs uppercase tracking-wide text-fg-subtle">
                  <th className="px-2 py-1.5 font-medium">{bi(locale, 'Motivo · Institución', 'Motivo · Institution')}</th>
                  <th className="px-2 py-1.5 font-medium">{bi(locale, 'Severidad', 'Severity')}</th>
                  <th className="px-2 py-1.5 font-medium">{bi(locale, 'Reclamos', 'Complaints')}</th>
                  <th className="px-2 py-1.5 font-medium">{bi(locale, 'Ventana', 'Window')}</th>
                  <th className="px-2 py-1.5 font-medium">{bi(locale, 'Pares', 'Peers')}</th>
                  <th className="px-2 py-1.5 font-medium">{bi(locale, 'Estado', 'Status')}</th>
                  <th className="px-2 py-1.5 font-medium">{bi(locale, 'Acción', 'Action')}</th>
                </tr>
              </thead>
              <tbody>
                {grouped.map((g) => {
                  const days = Math.max(
                    0,
                    Math.round(
                      (Date.parse(g.latest_detected) - Date.parse(g.earliest_detected)) / 86_400_000,
                    ),
                  );
                  const windowLabel =
                    days <= 0 ? bi(locale, 'Hoy', 'Today') : bi(locale, `${days} días`, `${days} days`);
                  const status =
                    g.severity_band === 'HIGH'
                      ? bi(locale, 'Investigación', 'Investigation')
                      : g.severity_band === 'MEDIUM'
                        ? bi(locale, 'Monitoreo', 'Monitoring')
                        : bi(locale, 'Observación', 'Watch');
                  const matched = BRIEFS.find((b) =>
                    b.title.toLowerCase().includes(g.motivo.toLowerCase().slice(0, 6)),
                  );
                  return (
                    <tr key={`${g.motivo}-${g.institution}`} className="border-b border-border-subtle">
                      <td className="px-2 py-1.5 text-fg">
                        {g.motivo} · <span className="font-mono">{g.institution}</span>
                      </td>
                      <td className="px-2 py-1.5">
                        <Badge variant={severityVariant(g.severity_band)}>
                          <span className="font-mono tabular-nums">{g.max_severity.toFixed(2)}</span>
                        </Badge>
                      </td>
                      <td className="px-2 py-1.5 font-mono tabular-nums text-fg">{g.complaint_count}</td>
                      <td className="px-2 py-1.5 font-mono text-fg-muted">{windowLabel}</td>
                      <td className="px-2 py-1.5 font-mono tabular-nums text-fg">{g.peer_count}</td>
                      <td className="px-2 py-1.5 text-fg-muted">{status}</td>
                      <td className="px-2 py-1.5">
                        <Sheet>
                          <SheetTrigger asChild>
                            <Button variant="outline" size="sm">
                              {bi(locale, 'Ver Brief', 'View Brief')}
                            </Button>
                          </SheetTrigger>
                          <SheetContent closeLabel={bi(locale, 'Cerrar', 'Close')} className="overflow-y-auto">
                            <SheetTitle>
                              {matched ? matched.title : `${g.motivo} · ${g.institution}`}
                            </SheetTitle>
                            {matched ? (
                              <>
                                <p className="mt-0.5 font-mono text-2xs text-fg-subtle">{matched.meta}</p>
                                <div className="mt-3 space-y-1.5">
                                  {matched.paragraphs.map((p, pi) => (
                                    <p key={pi} className="text-xs leading-relaxed text-fg">
                                      {p}
                                    </p>
                                  ))}
                                </div>
                              </>
                            ) : (
                              <p className="mt-3 text-xs text-fg">
                                {bi(
                                  locale,
                                  `${g.complaint_count} reclamos agrupados bajo "${g.motivo}" en ${g.institution}. Severidad máxima ${g.max_severity.toFixed(2)} (${g.severity_band}). Cohorte de ${g.peer_count} institución(es) par(es); patrón elevado por el motor de agregación al superar el umbral compuesto.`,
                                  `${g.complaint_count} complaints grouped under "${g.motivo}" at ${g.institution}. Max severity ${g.max_severity.toFixed(2)} (${g.severity_band}). Cohort of ${g.peer_count} peer institution(s); pattern raised by the aggregation engine on crossing the composite threshold.`,
                                )}
                              </p>
                            )}
                            <h3 className="mt-4 text-xs font-semibold uppercase tracking-wide text-fg-subtle">
                              {bi(locale, 'Reclamos contribuyentes (últimos 5)', 'Contributing complaints (last 5)')}
                            </h3>
                            <ul className="mt-1 flex flex-wrap gap-1.5">
                              {g.complaint_ids.map((id) => (
                                <li key={id}>
                                  <Link href={`/processing/${id}`} className="inline-block rounded-sbs border border-border bg-surface-subtle px-2 py-0.5 font-mono text-2xs text-fg-link">
                                    {id}
                                  </Link>
                                </li>
                              ))}
                            </ul>
                            <h3 className="mt-4 text-xs font-semibold uppercase tracking-wide text-fg-subtle">
                              {bi(locale, 'Controles sugeridos', 'Suggested controls')}
                            </h3>
                            <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-fg">
                              <li>{bi(locale, 'Revisar política de divulgación y comunicación', 'Review disclosure and communication policy')}</li>
                              <li>{bi(locale, 'Auditar últimos 90 días de cargos/operaciones', 'Audit last 90 days of charges/operations')}</li>
                              <li>{bi(locale, 'Comunicación proactiva a clientes afectados', 'Proactive outreach to affected customers')}</li>
                            </ul>
                          </SheetContent>
                        </Sheet>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* SECTION 3.6 — AGGREGATE ANALYSIS CYCLE */}
      <Card className="p-3" id="aggregate-cycle">
        <h2 className="text-sm font-semibold tracking-tight text-fg">
          {bi(locale, 'Análisis agregado', 'Aggregate analysis cycle')}
        </h2>
        <p className="text-2xs italic text-fg-muted">
          {bi(locale, 'Investigation y Lupaman escanean el pool cada 60 segundos', 'Investigation and Lupaman scan the pool every 60 seconds')}
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <div className="rounded-sbs border border-amber-300 bg-amber-50 px-3 py-1.5 text-center">
            <div className="text-2xs uppercase tracking-wide text-fg-subtle">
              {bi(locale, 'Próximo scan en', 'Next scan in')}
            </div>
            <div className="font-mono text-2xl tabular-nums text-amber-700">
              {`${60 - (Math.floor(now / 1000) % 60)}s`}
            </div>
          </div>
          <div className="text-2xs text-fg-muted">
            {bi(
              locale,
              `Último scan: hace ${Math.floor(now / 1000) % 60}s · 2 patrones detectados, 1 broadcast generado`,
              `Last scan: ${Math.floor(now / 1000) % 60}s ago · 2 patterns detected, 1 broadcast generated`,
            )}
          </div>
        </div>
        <h3 className="mt-3 text-xs font-semibold uppercase tracking-wide text-fg-subtle">
          {bi(locale, 'Últimos 5 scans', 'Last 5 scans')}
        </h3>
        <ul className="mt-1 space-y-1">
          {SCAN_ROWS.map((row) => (
            <li key={row} className="rounded-sbs border border-border bg-surface-subtle px-2 py-1 font-mono text-2xs tabular-nums text-fg">
              {row}
            </li>
          ))}
        </ul>
        <h3 className="mt-3 text-xs font-semibold uppercase tracking-wide text-fg-subtle">
          {bi(locale, 'Qué corre en cada scan', 'What runs in each scan')}
        </h3>
        <div className="mt-1 space-y-1">
          {SCAN_EXPLAIN.map((line) => (
            <p key={line} className="text-2xs leading-relaxed text-fg">
              {line}
            </p>
          ))}
        </div>
      </Card>

      {/* SECTION 3.5 — BRIEFS & BROADCASTS */}
      <Card className="p-3" id="briefs">
        <h2 className="mb-2 text-sm font-semibold tracking-tight text-fg">
          {bi(locale, 'Briefs y Difusiones Generadas', 'Generated Briefs & Broadcasts')}
        </h2>
        <div className="grid grid-cols-1 gap-2 lg:grid-cols-3">
          {BRIEFS.map((b) => (
            <div key={b.title} className="flex flex-col rounded-sbs border border-border bg-surface p-3">
              <Badge variant={b.kind === 'broadcast' ? 'high' : 'source'}>
                {b.kind === 'broadcast'
                  ? bi(locale, 'Difusión Sectorial', 'Sector Broadcast')
                  : 'Brief'}
              </Badge>
              <h3 className="mt-1.5 text-sm font-semibold leading-snug text-brand-navy">{b.title}</h3>
              <p className="mt-0.5 font-mono text-2xs text-fg-subtle">{b.meta}</p>
              <div className="mt-2 space-y-1.5">
                {b.paragraphs.map((p, i) => (
                  <p key={i} className="text-2xs leading-relaxed text-fg">
                    {p}
                  </p>
                ))}
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5 border-t border-border-subtle pt-2">
                <Button variant="default" size="sm">
                  {bi(locale, 'Aprobar', 'Approve')}
                </Button>
                <Button variant="outline" size="sm">
                  {bi(locale, 'Editar', 'Edit')}
                </Button>
                <Button variant="ghost" size="sm">
                  {bi(locale, 'Solicitar cambios', 'Request changes')}
                </Button>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* SECTION 4 — INSIGHTS */}
      <div id="insights">
        <InsightsPanel title={bi(locale, 'Insights generados', 'Generated insights')} insights={INSIGHTS} />
      </div>

      {/* SECTION 5 — CHATBOT */}
      {chatOpen ? (
        <aside className="fixed bottom-4 right-4 z-50 flex max-h-[70vh] w-[360px] flex-col rounded-sbs border border-border bg-surface shadow-lg">
          <header className="flex items-center justify-between border-b border-border bg-brand-navy px-3 py-2 text-fg-inverted">
            <span className="flex items-center gap-1.5 text-sm font-semibold">
              <MessageCircle className="h-4 w-4" aria-hidden="true" />
              {bi(locale, 'Asistente de Análisis', 'Analysis Assistant')}
            </span>
            <button type="button" onClick={() => setChatOpen(false)} aria-label={bi(locale, 'Cerrar', 'Close')} className="rounded-sbs p-1 hover:bg-white/10">
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          </header>
          <div className="flex-1 space-y-2 overflow-y-auto px-3 py-2">
            {messages.length === 0 ? (
              <p className="text-xs text-fg-muted">{bi(locale, 'Elige una pregunta o escribe la tuya.', 'Pick a question or type your own.')}</p>
            ) : (
              messages.map((m, i) => (
                <div key={i} className={m.role === 'user' ? 'ml-6 rounded-sbs bg-brand-navy px-2.5 py-1.5 text-xs text-fg-inverted' : 'mr-6 rounded-sbs border border-border bg-surface-subtle px-2.5 py-1.5 text-xs text-fg'}>
                  <p className="whitespace-pre-wrap leading-snug">{m.text}</p>
                </div>
              ))
            )}
            {chatPending ? <p className="text-2xs text-fg-subtle">{bi(locale, 'Analizando datos…', 'Analyzing data…')}</p> : null}
          </div>
          <div className="border-t border-border px-3 py-2">
            <div className="mb-1.5 flex flex-col gap-1">
              {QUICK_PROMPTS.map((q) => (
                <button key={q} type="button" onClick={() => ask(q)} disabled={chatPending} className="rounded-sbs border border-border bg-surface px-2 py-1 text-left text-2xs text-fg hover:border-brand-cyan disabled:opacity-50">
                  {q}
                </button>
              ))}
            </div>
            <form className="flex items-center gap-1.5" onSubmit={(e) => { e.preventDefault(); ask(input); }}>
              <input value={input} onChange={(e) => setInput(e.target.value)} placeholder={bi(locale, 'Pregunta…', 'Ask…')} className="flex-1 rounded-sbs border border-border bg-surface px-2.5 py-1.5 text-xs text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus" />
              <Button type="submit" size="sm" disabled={chatPending || input.trim().length === 0}>
                <Send className="h-3.5 w-3.5" aria-hidden="true" />
              </Button>
            </form>
          </div>
        </aside>
      ) : (
        <button type="button" onClick={() => setChatOpen(true)} className="fixed bottom-4 right-4 z-50 flex items-center gap-2 rounded-sbs border border-border-strong bg-brand-navy px-3 py-2 text-sm font-medium text-fg-inverted shadow-lg hover:bg-brand-navy/90">
          <MessageCircle className="h-4 w-4" aria-hidden="true" />
          {bi(locale, 'Asistente de Análisis', 'Analysis Assistant')}
        </button>
      )}
    </div>
  );
}
