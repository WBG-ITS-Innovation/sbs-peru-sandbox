// LiveIngestionPanel — UI-only preview of what a Tier 1 submission
// would look like once canonical anonymization is wired into the
// pipeline. The panel does NOT call the backend; the "Simular envío"
// button only fires a local toast. The disclaimer banner makes that
// explicit to any supervisor or regulator looking at the screen.
//
// Real cockpit data (KPIs, anomalies, Tier 1 / Tier 2 lists) remains
// DB/API/SSE-backed. This panel sits below them as a preview slot.

'use client';

import { useState } from 'react';
import { CheckCircle2, Circle, Info, Lock, Play, Send } from 'lucide-react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import {
  Toast,
  ToastClose,
  ToastDescription,
  ToastProvider,
  ToastTitle,
  ToastViewport,
} from '@/components/ui/Toast';

interface Labels {
  title: string;
  subtitle: string;
  preview_disclaimer: string;
  pilot_badge: string;
  live_toggle: string;
  paused_toggle: string;
  mtls_label: string;
  simulate_button: string;
  simulate_toast_title: string;
  simulate_toast_body: string;
  timeline_title: string;
  diff_title: string;
  diff_tag_before: string;
  diff_tag_after: string;
  diff_before_text: string;
  diff_after_text: string;
  policy_footer: string;
  events: {
    received: string;
    validated: string;
    redacted: string;
    persisted: string;
    broadcast: string;
  };
}

interface LiveIngestionPanelProps {
  labels: Labels;
}

interface SimEvent {
  id: string;
  ts: string;
  text: string;
  state: 'done' | 'live' | 'queued';
}

export function LiveIngestionPanel({ labels }: LiveIngestionPanelProps) {
  const [paused, setPaused] = useState(true);
  const [toastSeq, setToastSeq] = useState(0);

  // Deterministic illustrative timeline. The component never asks the
  // backend for these — they are display copy keyed to a fixed clock.
  const events: SimEvent[] = [
    { id: 'received', ts: '09:14:02', text: labels.events.received, state: 'done' },
    { id: 'validated', ts: '09:14:02', text: labels.events.validated, state: 'done' },
    { id: 'redacted', ts: '09:14:03', text: labels.events.redacted, state: 'live' },
    { id: 'persisted', ts: '09:14:03', text: labels.events.persisted, state: 'queued' },
    { id: 'broadcast', ts: '09:14:03', text: labels.events.broadcast, state: 'queued' },
  ];

  return (
    <ToastProvider duration={4000}>
      <section
        aria-label={labels.title}
        className="overflow-hidden rounded-sbs border border-border bg-surface shadow-sm"
        style={{ borderLeft: '3px solid var(--color-brand-navy)' }}
      >
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-3">
          <div className="flex min-w-0 flex-col">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-fg">{labels.title}</h2>
              <Badge variant="role" className="border-brand-gold/40 bg-brand-gold/10 text-brand-navy">
                {labels.pilot_badge}
              </Badge>
            </div>
            <p className="text-xs text-fg-muted">{labels.subtitle}</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <div
              role="group"
              aria-label={`${labels.live_toggle} / ${labels.paused_toggle}`}
              className="flex overflow-hidden rounded-sbs border border-border-strong"
            >
              <button
                type="button"
                onClick={() => setPaused(false)}
                className={
                  'px-2.5 py-1 text-xs ' +
                  (paused
                    ? 'bg-surface text-fg-muted hover:bg-surface-subtle'
                    : 'bg-brand-navy text-fg-inverted')
                }
              >
                {labels.live_toggle}
              </button>
              <button
                type="button"
                onClick={() => setPaused(true)}
                className={
                  'px-2.5 py-1 text-xs ' +
                  (paused
                    ? 'bg-brand-navy text-fg-inverted'
                    : 'bg-surface text-fg-muted hover:bg-surface-subtle')
                }
              >
                {labels.paused_toggle}
              </button>
            </div>
            <span className="flex items-center gap-1 font-mono text-2xs uppercase tracking-wider text-fg-subtle">
              <Lock className="h-3 w-3" aria-hidden="true" />
              {labels.mtls_label}
            </span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setToastSeq(n => n + 1)}
              aria-describedby="live-ingestion-preview-note"
            >
              <Send className="h-3.5 w-3.5" aria-hidden="true" />
              {labels.simulate_button}
            </Button>
          </div>
        </header>

        <div
          id="live-ingestion-preview-note"
          className="flex items-center gap-2 border-b border-border bg-surface-subtle px-4 py-2 text-xs text-fg-muted"
        >
          <Info className="h-3.5 w-3.5 text-brand-gold" aria-hidden="true" />
          <span>{labels.preview_disclaimer}</span>
        </div>

        <div className="grid gap-4 p-4 md:grid-cols-[1.4fr_1fr]">
          <div>
            <h3 className="mb-2 font-mono text-2xs uppercase tracking-wider text-fg-muted">
              {labels.timeline_title}
            </h3>
            <ol className="relative space-y-2 border-l border-border-strong pl-4">
              {events.map(ev => (
                <li key={ev.id} className="flex items-start gap-2 text-xs">
                  <span
                    className="-ml-[1.4rem] mt-0.5 inline-flex h-3 w-3 items-center justify-center rounded-full bg-surface"
                    aria-hidden="true"
                  >
                    {ev.state === 'done' ? (
                      <CheckCircle2 className="h-3 w-3 text-severity-low-fg" />
                    ) : ev.state === 'live' ? (
                      <Play
                        className="h-3 w-3 text-brand-gold"
                        style={{ animation: 'pulse 1.8s ease-in-out infinite' }}
                      />
                    ) : (
                      <Circle className="h-3 w-3 text-fg-subtle" />
                    )}
                  </span>
                  <span className="font-mono text-2xs tabular text-fg-subtle">{ev.ts}</span>
                  <span className="text-fg">{ev.text}</span>
                </li>
              ))}
            </ol>
          </div>

          <div>
            <h3 className="mb-2 font-mono text-2xs uppercase tracking-wider text-fg-muted">
              {labels.diff_title}
            </h3>
            <div className="space-y-2">
              <div className="rounded-sbs border border-severity-high-border bg-severity-high-bg/40 p-2 text-xs">
                <span className="block font-mono text-2xs font-semibold uppercase tracking-wider text-severity-high-fg">
                  {labels.diff_tag_before}
                </span>
                <span className="block font-mono text-xs leading-snug text-fg">
                  {labels.diff_before_text}
                </span>
              </div>
              <div className="rounded-sbs border border-severity-low-border bg-severity-low-bg/40 p-2 text-xs">
                <span className="block font-mono text-2xs font-semibold uppercase tracking-wider text-severity-low-fg">
                  {labels.diff_tag_after}
                </span>
                <span className="block font-mono text-xs leading-snug text-fg">
                  {labels.diff_after_text}
                </span>
              </div>
              <p className="font-mono text-2xs text-fg-muted">{labels.policy_footer}</p>
            </div>
          </div>
        </div>

        {toastSeq > 0 ? (
          <Toast key={toastSeq} variant="default">
            <div className="flex flex-col gap-1">
              <ToastTitle>{labels.simulate_toast_title}</ToastTitle>
              <ToastDescription>{labels.simulate_toast_body}</ToastDescription>
            </div>
            <ToastClose closeLabel="Close" />
          </Toast>
        ) : null}
        <ToastViewport />
      </section>
    </ToastProvider>
  );
}
