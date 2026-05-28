'use client';

import { Info } from 'lucide-react';
import { useState } from 'react';

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui';
import type { Locale } from '@/i18n';
import { bi } from '@/lib/bi';
import type { ExplainEntry } from '@/types/persona-dashboards';

interface ExplanationProps {
  explanationKey: string;
  locale: Locale;
  /** Values substituted into {token} placeholders and shown as context. */
  contextData?: Record<string, string | number>;
}

// Renders a small info icon. On hover/focus it fetches the explanation
// registry entry for `explanationKey` and shows the bilingual text with
// any {token} placeholders replaced from contextData. This is the
// surface that lets a reviewer click any number/severity/verdict and see
// what it means in plain language.
export function Explanation({ explanationKey, locale, contextData }: ExplanationProps) {
  const [entry, setEntry] = useState<ExplainEntry | null>(null);
  const [state, setState] = useState<'idle' | 'loading' | 'error'>('idle');

  async function load() {
    if (entry || state === 'loading') return;
    setState('loading');
    try {
      const res = await fetch(`/app/api/explain/${encodeURIComponent(explanationKey)}`, {
        cache: 'no-store',
      });
      if (!res.ok) throw new Error(String(res.status));
      setEntry((await res.json()) as ExplainEntry);
      setState('idle');
    } catch {
      setState('error');
    }
  }

  function substitute(text: string): string {
    if (!contextData) return text;
    return text.replace(/\{(\w+)\}/g, (match, token) =>
      token in contextData ? String(contextData[token]) : match,
    );
  }

  const raw = entry ? bi(locale, entry.es, entry.en) : '';
  const body =
    state === 'loading'
      ? bi(locale, 'Cargando…', 'Loading…')
      : state === 'error'
        ? bi(locale, 'Sin explicación disponible.', 'No explanation available.')
        : substitute(raw);

  const contextLine =
    contextData && Object.keys(contextData).length > 0
      ? Object.entries(contextData)
          .map(([k, v]) => `${k}: ${v}`)
          .join(' · ')
      : null;

  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip onOpenChange={(open) => open && load()}>
        <TooltipTrigger asChild>
          <button
            type="button"
            onMouseEnter={load}
            onFocus={load}
            aria-label={bi(locale, 'Ver explicación', 'View explanation')}
            className="inline-flex h-4 w-4 items-center justify-center rounded-full text-brand-cyan hover:text-brand-navy focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
          >
            <Info className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        </TooltipTrigger>
        <TooltipContent>
          <p className="leading-snug">{body}</p>
          {contextLine ? (
            <p className="mt-1 font-mono text-2xs text-fg-muted">{contextLine}</p>
          ) : null}
          {entry?.source_rule ? (
            <p className="mt-1 font-mono text-2xs text-fg-subtle">
              {bi(locale, 'Regla', 'Rule')}: {entry.source_rule}
            </p>
          ) : null}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
