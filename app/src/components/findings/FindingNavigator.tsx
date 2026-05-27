// Top-of-finding-detail navigator. Adds the cross-references the user
// asked for: link to the live processing view, link to audit filtered
// by this complaint, link to the similar-complaints search. Plus a
// glossary popover summarising the four key pieces of jargon a
// supervisor sees on this page.
/* eslint-disable i18next/no-literal-string */

'use client';

import Link from 'next/link';
import {
  Activity,
  AlertTriangle,
  CircleHelp,
  History,
  ListChecks,
  Sparkles,
} from 'lucide-react';

import {
  Card,
  CardBody,
  Tooltip as InfoTooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui';
import type { Locale } from '@/i18n';

interface Props {
  locale: Locale;
  complaintId: string;
  hasIssues?: boolean;
}

export function FindingNavigator({ locale, complaintId, hasIssues }: Props) {
  const es = locale === 'es-PE';
  const links = [
    {
      href: `/processing/${complaintId}`,
      icon: <Activity className="h-3.5 w-3.5" />,
      label: es ? 'Ver procesamiento en vivo' : 'Open live processing',
    },
    {
      href: `/audit?object_id=${encodeURIComponent(complaintId)}`,
      icon: <History className="h-3.5 w-3.5" />,
      label: es ? 'Ver auditoría completa' : 'Open full audit',
      highlight: hasIssues,
    },
    {
      href: `/audit?object_id=${encodeURIComponent(complaintId)}&action=dq-rule-violated`,
      icon: <AlertTriangle className="h-3.5 w-3.5" />,
      label: es ? 'Violaciones de DQ' : 'DQ violations',
    },
    {
      href: '/processing',
      icon: <ListChecks className="h-3.5 w-3.5" />,
      label: es ? 'Cola de procesamiento' : 'Processing queue',
    },
  ];

  return (
    <TooltipProvider delayDuration={150}>
      <Card className="border-brand-cyan/40">
        <CardBody className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            {links.map((l) => (
              <Link
                key={l.label}
                href={l.href}
                className={
                  'inline-flex h-8 items-center gap-1.5 rounded-sbs border px-2.5 text-xs font-medium transition-colors ' +
                  (l.highlight
                    ? 'border-severity-medium-border bg-severity-medium-bg text-severity-medium-fg'
                    : 'border-border-strong bg-surface text-fg hover:bg-surface-subtle')
                }
              >
                {l.icon}
                {l.label}
              </Link>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Glossary
              icon={<Sparkles className="h-3.5 w-3.5 text-brand-gold" />}
              label={es ? 'Composite score' : 'Composite score'}
              body={
                es
                  ? 'Suma ponderada 0-1 calculada por el agente de Investigación. Umbral 0.70; sobre eso se publica anomalía en la cabina. Seis contribuyentes: gap de divulgación, tasa-vs-pares, patrón textual, severidad, antigüedad, edad cliente.'
                  : 'Weighted 0-1 sum computed by the Investigation agent. Threshold 0.70; above that, anomaly is published to the cockpit. Six contributors: disclosure gap, rate-vs-peers, textual pattern, severity, recency, customer age.'
              }
            />
            <Glossary
              icon={<Sparkles className="h-3.5 w-3.5 text-brand-cyan" />}
              label={es ? 'SHAP' : 'SHAP'}
              body={
                es
                  ? 'SHapley Additive exPlanations: técnica de explicabilidad que asigna a cada feature su contribución signada a la predicción del modelo. Valores positivos empujan hacia la etiqueta; negativos la alejan.'
                  : 'SHapley Additive exPlanations: explainability technique that assigns each feature its signed contribution to the model\'s prediction. Positive values push toward the label; negative pull away.'
              }
            />
            <Glossary
              icon={<Sparkles className="h-3.5 w-3.5 text-brand-cyan" />}
              label={es ? 'Anexo 1-A' : 'Annex 1-A'}
              body={
                es
                  ? 'Resolución SBS N° 04036-2022 establece el formato de 27 campos para reportes de reclamos. Los enums (canal, producto, motivo) están codificados en los Anexos A/B/C/D del mismo reglamento.'
                  : 'SBS Resolution 04036-2022 sets the 27-field schema for complaint reports. The enums (channel, product, motive) are codified in Annexes A/B/C/D of the same regulation.'
              }
            />
            <Glossary
              icon={<Sparkles className="h-3.5 w-3.5 text-brand-cyan" />}
              label={es ? 'PII' : 'PII'}
              body={
                es
                  ? 'Personally Identifiable Information: nombres, DNI, teléfono, correo, números de cuenta. La SBS redacta el texto antes de persistir en complaints; el texto crudo solo se conserva en raw_complaints con acceso restringido.'
                  : 'Personally Identifiable Information: names, DNI, phone, email, account numbers. SBS redacts text before persisting to complaints; raw text is kept only in raw_complaints with restricted access.'
              }
            />
          </div>
        </CardBody>
      </Card>
    </TooltipProvider>
  );
}

function Glossary({ icon, label, body }: { icon: React.ReactNode; label: string; body: string }) {
  return (
    <InfoTooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className="inline-flex h-7 items-center gap-1 rounded-sbs border border-border-subtle bg-surface-subtle px-2 text-2xs text-fg hover:bg-surface"
        >
          {icon}
          {label}
          <CircleHelp className="h-2.5 w-2.5 text-fg-muted" />
        </button>
      </TooltipTrigger>
      <TooltipContent side="bottom" align="end">
        {body}
      </TooltipContent>
    </InfoTooltip>
  );
}
