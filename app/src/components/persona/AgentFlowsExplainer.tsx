'use client';
// SPDX-License-Identifier: Apache-2.0

import {
  Brain,
  FileText,
  Inbox,
  Layers,
  MessageCircle,
  Radar,
  Search,
  ShieldCheck,
  type LucideIcon,
} from 'lucide-react';
import { useState } from 'react';

import { Card } from '@/components/ui';
import type { Locale } from '@/i18n';
import { bi } from '@/lib/bi';

function CodeBlock({ children }: { children: string }) {
  return (
    <pre className="mt-2 overflow-x-auto whitespace-pre-wrap rounded-sbs border border-brand-navy bg-brand-navy p-2.5 font-mono text-2xs leading-relaxed text-cyan-100">
      {children}
    </pre>
  );
}

function StepCircle({ n, tone }: { n: number; tone: 'blue' | 'amber' }) {
  return (
    <span
      className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-2xs font-bold text-white ${
        tone === 'blue' ? 'bg-brand-cyan' : 'bg-amber-500'
      }`}
      aria-hidden="true"
    >
      {n}
    </span>
  );
}

interface PerStage {
  n: number;
  icon: LucideIcon;
  title: string;
  what: string;
  json?: string;
  rule?: string;
  timing: string;
  subtitle?: string;
}

interface AggCard {
  n: number;
  icon: LucideIcon;
  title: string;
  badge: string;
  what: string;
  list?: string;
  walkthrough: string;
}

export function AgentFlowsExplainer({
  locale,
  poolSize,
  highCount,
}: {
  locale: Locale;
  poolSize: number;
  highCount: number;
}) {
  const [tab, setTab] = useState<'complaint' | 'aggregate'>('complaint');
  const high = Math.max(highCount, 3);

  const perStages: PerStage[] = [
    {
      n: 1,
      icon: Inbox,
      title: bi(locale, '1. Recepción', '1. Reception'),
      what: bi(locale, 'El reclamo llega vía Tier 1 API o Tier 2 batch.', 'The complaint arrives via Tier 1 API or Tier 2 batch.'),
      json: `POST /v1/complaints/banco-tier1
{
  "complaint_id": "BCO-2026-280339",
  "institution_id": "SBS-001234",
  "narrative": "El banco me cobró S/. 35 de comisión...",
  "amount_disputed": 35.00,
  "motivo_declared": null,
  "channel": "app_movil"
}`,
      timing: '~50ms',
    },
    {
      n: 2,
      icon: ShieldCheck,
      title: bi(locale, '2. DIValeVale · Validador', '2. DIValeVale · Validator'),
      what: bi(locale, 'Valida formato Annex 1-A, normaliza taxonomías, detecta campos faltantes.', 'Validates Annex 1-A format, normalizes taxonomies, detects missing fields.'),
      json: `{
  "status": "ACCEPTED",
  "validations_passed": ["RUC_format", "fecha_iso", "motivo_taxonomy"],
  "normalizations": [
    {"field": "channel_operation", "original": "APP_MOVIL", "normalized": "app_movil"}
  ],
  "data_quality_score": 0.94
}`,
      rule: bi(locale, 'Si data_quality_score < 0.5 → INSUFFICIENT → webhook a institución', 'If data_quality_score < 0.5 → INSUFFICIENT → webhook to institution'),
      timing: '~80ms',
    },
    {
      n: 3,
      icon: Brain,
      title: bi(locale, '3. Triage · Clasificador', '3. Triage · Classifier'),
      what: bi(locale, 'Lee la narrativa, asigna motivo (M-1 a M-9), confianza, y detecta system_signal.', 'Reads the narrative, assigns motivo (M-1 to M-9), confidence, and detects system_signal.'),
      json: `{
  "motivo_top3": [
    {"code": "M-3.2", "label": "cobros_indebidos", "confidence": 0.89},
    {"code": "M-3.1", "label": "comisiones_indebidas", "confidence": 0.42},
    {"code": "M-4.1", "label": "informacion_insuficiente", "confidence": 0.18}
  ],
  "system_signal": false,
  "model": "clasificador-basado-en-reglas (BERT en producción)"
}`,
      rule: bi(locale, 'Si confidence < 0.6 OR system_signal=true → marca para revisión humana', 'If confidence < 0.6 OR system_signal=true → flag for human review'),
      timing: '~120ms',
    },
    {
      n: 4,
      icon: Layers,
      title: bi(locale, '4. Pool agregado', '4. Aggregate pool'),
      what: bi(locale, 'El reclamo se une al pool. Aquí termina el procesamiento por reclamo.', 'The complaint joins the pool. Per-complaint processing ends here.'),
      subtitle: bi(locale, 'Los siguientes pasos son sobre agregados — ver pestaña Flujo agregado.', 'The next steps are on aggregates — see the Aggregate flow tab.'),
      timing: bi(locale, 'instantáneo', 'instant'),
    },
  ];

  const aggCards: AggCard[] = [
    {
      n: 1,
      icon: Search,
      title: bi(locale, '1. Investigation · Detector de patrones', '1. Investigation · Pattern detector'),
      badge: bi(locale, 'AGREGADO · cada 60s', 'AGGREGATE · every 60s'),
      what: bi(locale, 'Escanea el pool completo buscando concentraciones por motivo × institución que excedan el umbral. También se activa por system_signal=true en cualquier reclamo.', 'Scans the full pool for motivo × institution concentrations that exceed the threshold. Also triggers on system_signal=true in any complaint.'),
      list: 'Se activa si:\n  • Volumen: ≥5 reclamos del mismo motivo × institución en últimas 24h\n  • Señal: cualquier reclamo con system_signal=true\n  • Outlier: institución con z-score > 2.5 sobre su cohorte',
      walkthrough: `INPUT: pool de ${poolSize} reclamos en últimas 24h
  ↓
SCAN: agrupa por motivo × institución
Encuentra: BANCO_DEMO_001 × cobros_indebidos = 12 reclamos (umbral: 5) ✓
  ↓
GENERATE DOSSIER:
{
  "pattern_id": "pat-c3ac6545",
  "severity": 0.92,
  "motivo": "cobros_indebidos",
  "institution": "BANCO_DEMO_001",
  "contributing_complaints": 12,
  "narrative": "12 reclamos en últimos 7 días por comisiones no divulgadas. Cargo de S/.35 sin notificación previa. 2.3× la mediana del cohorte BANCO:TIER_1.",
  "peer_comparison": {"cohort": "BANCO:TIER_1", "percentile": 78},
  "suggested_controls": ["revisar política comunicación", "auditar 90 días cargos", "capacitar canal digital"]
}`,
    },
    {
      n: 2,
      icon: Radar,
      title: bi(locale, '2. Lupaman · Cross-source y fraude', '2. Lupaman · Cross-source & fraud'),
      badge: bi(locale, 'AGREGADO · cada 60s', 'AGGREGATE · every 60s'),
      what: bi(locale, 'Cruza el pool con señales externas (INDECOPI, redes sociales, market data) para detectar campañas de fraude que una sola institución no podría ver.', 'Cross-references the pool with external signals (INDECOPI, social media, market data) to detect fraud campaigns no single institution could see.'),
      list: 'Fuentes que combina:\n  • Reclamos del pool actual (peso 0.25)\n  • Casos INDECOPI activos (peso 0.30)\n  • Sentiment redes sociales (peso 0.20)\n  • Velocidad de reclamos (peso 0.15)\n  • Tamaño de mercado afectado (peso 0.10)',
      walkthrough: `INPUT: pool ${poolSize} reclamos + 23 casos INDECOPI + 147 menciones X/Twitter
  ↓
CROSS-SOURCE CORRELATION:
Detectado: 8 reclamos en 48h sobre "llamadas suplantando ejecutivos"
INDECOPI: 4 denuncias similares en mismo período
Redes sociales: 12 menciones de modus operandi idéntico
  ↓
SCORE COMPOSITE: 0.92 (umbral de difusión: 0.85)
  ↓
GENERATE BROADCAST (anonimiza origen):
{
  "broadcast_id": "bcs-22ae7e2f",
  "severity": 0.92,
  "cohort": "BANCO:TIER_1",
  "peer_count": 4,
  "threat_summary": "Llamadas suplantando ejecutivos solicitando códigos OTP",
  "indicators_of_compromise": [
    "Llamadas desde números aparentemente locales",
    "Referencia a transacciones específicas",
    "Presión temporal (10 minutos)",
    "Solicitud de código OTP o PIN"
  ],
  "suggested_controls": ["alertas proactivas SMS+app", "MFA reforzado", "capacitación call center"],
  "origin_institution": "[REDACTED - protegida por marco intercambio]"
}`,
    },
    {
      n: 3,
      icon: FileText,
      title: bi(locale, '3. Reclamito · Redactor de avisos', '3. Reclamito · Notice drafter'),
      badge: bi(locale, 'ON-DEMAND · tras aprobación supervisora', 'ON-DEMAND · after supervisor approval'),
      what: bi(locale, 'Cuando Investigation o Lupaman generan un patrón con severidad ≥ HIGH (0.85), Reclamito redacta automáticamente el aviso formal.', 'When Investigation or Lupaman produce a pattern with severity ≥ HIGH (0.85), Reclamito automatically drafts the formal notice.'),
      list: 'Avisos a IF:\n  INPUT: pattern_id + preferencias de la supervisora\n  ↓ DRAFT: template por motivo + LLM (Qwen 2.5) para narrativa\n  ↓ OUTPUT: brief de 4 párrafos con datos, peer comparison, controles\n  ↓ Respeta cooldown 30 días por motivo × institución\nDifusiones sectoriales: mismo flujo pero anonimiza la institución origen',
      walkthrough: `Aviso a institución — Cobros indebidos en BANCO_DEMO_001

Se ha detectado un patrón de 12 reclamos en los últimos 7 días
relacionados con cobros indebidos en cuentas de ahorro de
BANCO_DEMO_001, todos por comisiones no divulgadas...

[4 párrafos: contexto, peer comparison, controles, marco temporal]`,
    },
    {
      n: 4,
      icon: MessageCircle,
      title: bi(locale, '4. Insight Chatbot · Análisis ad-hoc', '4. Insight Chatbot · Ad-hoc analysis'),
      badge: bi(locale, 'ON-DEMAND · usuario consulta', 'ON-DEMAND · user query'),
      what: bi(locale, 'Permite preguntas en lenguaje natural sobre patrones, instituciones y motivos. Scope por persona — Superintendent solo agregados, Analyst/Supervisor detalle de su scope, ITOps solo ops.', 'Natural-language questions about patterns, institutions and motivos. Scoped per persona — Superintendent aggregates only, Analyst/Supervisor detail in scope, ITOps ops only.'),
      list: 'Tools que puede invocar:\n  • query_patterns(filters)\n  • query_broadcasts(cohort, period)\n  • query_institutions(name)\n  • get_aggregate_stats(dimension)\n  • compare_cohorts(a, b, metric)',
      walkthrough: `USER: "¿Qué patrones de fraude tenemos esta semana?"
  ↓
[tool_call] query_patterns(severity=HIGH, period=7d, type=fraud)
[tool_result] 3 patterns matching
  ↓
"Detecté 3 patrones de fraude HIGH severity esta semana, todos en
BANCO:TIER_1. El más crítico es 'llamadas suplantando ejecutivos del
banco' con 8 reclamos contribuyentes. Lupaman ya redactó una difusión
sectorial a los 4 bancos pares del cohorte. [Ver difusión →]"`,
    },
  ];

  const statTile = (value: string, label: string) => (
    <div className="rounded-sbs border border-border bg-surface px-2.5 py-1.5">
      <div className="font-mono text-sm font-semibold tabular-nums text-fg">{value}</div>
      <div className="text-2xs text-fg-muted">{label}</div>
    </div>
  );

  return (
    <Card className="p-3" id="agent-flows">
      <h2 className="text-sm font-semibold tracking-tight text-fg">
        {bi(locale, 'Cómo trabajan los agentes', 'How the agents work')}
      </h2>
      <p className="text-2xs italic text-fg-muted">
        {bi(locale, 'Dos flujos distintos: por reclamo (rápido) y sobre agregados (analítico)', 'Two distinct flows: per-complaint (fast) and aggregate (analytical)')}
      </p>

      <div className="mt-2 inline-flex rounded-sbs border border-border bg-surface-subtle p-0.5">
        <button
          type="button"
          onClick={() => setTab('complaint')}
          className={`rounded-sbs px-3 py-1 text-xs font-medium transition-colors ${
            tab === 'complaint' ? 'bg-brand-cyan text-white' : 'text-fg-muted hover:text-fg'
          }`}
        >
          {bi(locale, '📥 Flujo por reclamo', '📥 Per-complaint flow')}
        </button>
        <button
          type="button"
          onClick={() => setTab('aggregate')}
          className={`rounded-sbs px-3 py-1 text-xs font-medium transition-colors ${
            tab === 'aggregate' ? 'bg-amber-500 text-white' : 'text-fg-muted hover:text-fg'
          }`}
        >
          {bi(locale, '📊 Flujo agregado', '📊 Aggregate flow')}
        </button>
      </div>

      {tab === 'complaint' ? (
        <div className="mt-3">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-sbs border-l-4 border-l-brand-cyan border border-border bg-blue-50 p-3">
            <div>
              <div className="text-xs font-semibold text-brand-navy">
                {bi(locale, 'Procesamiento en tiempo real', 'Real-time processing')}
              </div>
              <div className="font-mono text-2xl font-bold tabular-nums text-brand-cyan">
                {bi(locale, '<5 segundos', '<5 seconds')}
              </div>
              <div className="text-2xs text-fg-muted">
                {bi(locale, 'tiempo promedio por reclamo · cada reclamo nuevo pasa por estos agentes al llegar', 'avg time per complaint · each new complaint flows through these agents on arrival')}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {statTile(`${poolSize}`, bi(locale, 'procesados última hora', 'processed last hour'))}
              {statTile('100%', bi(locale, 'éxito DIValeVale', 'DIValeVale success'))}
              {statTile('94%', bi(locale, 'confianza Triage', 'Triage confidence'))}
            </div>
          </div>

          <div className="mt-2 grid grid-cols-1 gap-2 lg:grid-cols-2">
            {perStages.map((s) => {
              const Icon = s.icon;
              return (
                <div key={s.n} className="rounded-sbs border border-l-4 border-l-brand-cyan border-border bg-surface p-2.5">
                  <div className="flex items-center gap-2">
                    <StepCircle n={s.n} tone="blue" />
                    <Icon className="h-4 w-4 text-brand-navy" aria-hidden="true" />
                    <span className="text-sm font-semibold text-fg">{s.title}</span>
                    <span className="ml-auto font-mono text-2xs text-fg-subtle">{s.timing}</span>
                  </div>
                  <p className="mt-1 text-2xs leading-relaxed text-fg">{s.what}</p>
                  {s.subtitle ? <p className="mt-1 text-2xs italic text-fg-muted">{s.subtitle}</p> : null}
                  {s.json ? <CodeBlock>{s.json}</CodeBlock> : null}
                  {s.rule ? (
                    <p className="mt-1.5 rounded-sbs bg-surface-subtle px-2 py-1 font-mono text-2xs text-fg-muted">{s.rule}</p>
                  ) : null}
                </div>
              );
            })}
          </div>

          <div className="mt-2 rounded-sbs border border-brand-cyan/40 bg-brand-cyan/5 px-3 py-1.5 text-2xs font-medium text-brand-navy">
            {bi(locale, 'Total ~250ms por reclamo · 50 reclamos en menos de 15 segundos', 'Total ~250ms per complaint · 50 complaints in under 15 seconds')}
          </div>
        </div>
      ) : (
        <div className="mt-3">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-sbs border-l-4 border-l-amber-500 border border-border bg-amber-50 p-3">
            <div className="max-w-xl">
              <div className="text-xs font-semibold text-amber-700">
                {bi(locale, 'Análisis agregado', 'Aggregate analysis')}
              </div>
              <div className="font-mono text-2xl font-bold tabular-nums text-amber-600">
                {bi(locale, 'cada 60 segundos', 'every 60 seconds')}
              </div>
              <div className="text-2xs text-fg-muted">
                {bi(locale, 'Investigation y Lupaman NO miran reclamos individuales — miran el pool entero para detectar patrones, tendencias y señales cruzadas', 'Investigation and Lupaman do NOT look at individual complaints — they scan the whole pool for patterns, trends and cross-source signals')}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {statTile(`${poolSize}`, bi(locale, 'reclamos en pool', 'complaints in pool'))}
              {statTile(`${high}`, bi(locale, 'patrones HIGH activos', 'active HIGH patterns'))}
              {statTile('1', bi(locale, 'broadcast en cola', 'broadcast in queue'))}
            </div>
          </div>

          <div className="mt-2 space-y-2">
            {aggCards.map((c) => {
              const Icon = c.icon;
              return (
                <div key={c.n} className="rounded-sbs border border-l-4 border-l-amber-500 border-border bg-surface p-2.5">
                  <div className="flex items-center gap-2">
                    <StepCircle n={c.n} tone="amber" />
                    <Icon className="h-4 w-4 text-brand-navy" aria-hidden="true" />
                    <span className="text-sm font-semibold text-fg">{c.title}</span>
                    <span className="ml-auto rounded-sbs border border-amber-300 bg-amber-50 px-1.5 py-0.5 text-2xs font-semibold uppercase text-amber-700">
                      {c.badge}
                    </span>
                  </div>
                  <p className="mt-1 text-2xs leading-relaxed text-fg">{c.what}</p>
                  {c.list ? (
                    <pre className="mt-1.5 whitespace-pre-wrap rounded-sbs bg-surface-subtle px-2 py-1 font-mono text-2xs leading-relaxed text-fg-muted">
                      {c.list}
                    </pre>
                  ) : null}
                  <CodeBlock>{c.walkthrough}</CodeBlock>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </Card>
  );
}
