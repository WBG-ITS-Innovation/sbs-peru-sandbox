'use client';

import { useState, useTransition } from 'react';

import { runActionAction, type ActionResult } from '@/app/dashboard/actions';
import {
  Button,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  Input,
} from '@/components/ui';
import type { Locale } from '@/i18n';
import { bi } from '@/lib/bi';
import type { ActionDef } from '@/types/persona-dashboards';

interface ActionButtonProps {
  action: ActionDef;
  locale: Locale;
}

// Generic action button: opens a modal that enforces the registry's
// minimum-rationale length, collects a target id when the endpoint is
// parameterised, then POSTs through the server action. The backend
// response (success or problem+json detail) is shown inline.
export function ActionButton({ action, locale }: ActionButtonProps) {
  const [open, setOpen] = useState(false);
  const [rationale, setRationale] = useState('');
  const [summary, setSummary] = useState('');
  const [targetId, setTargetId] = useState('');
  const [result, setResult] = useState<ActionResult | null>(null);
  const [pending, startTransition] = useTransition();

  const label = bi(locale, action.label_es, action.label_en);
  const description = action.description_es
    ? bi(locale, action.description_es, action.description_en ?? '')
    : '';
  const minChars = action.requires_rationale_chars ?? 0;
  const needsTarget = action.endpoint.includes('{');
  const isPropose = action.action_id === 'propose_pattern';

  const rationaleOk = rationale.trim().length >= minChars;
  const targetOk = !needsTarget || targetId.trim().length > 0;
  const canSubmit = rationaleOk && targetOk && !pending;

  function reset() {
    setRationale('');
    setSummary('');
    setTargetId('');
    setResult(null);
  }

  function submit() {
    setResult(null);
    startTransition(async () => {
      const res = await runActionAction(action.action_id, {
        rationale: rationale.trim(),
        summary: summary.trim() || undefined,
        targetId: targetId.trim() || undefined,
      });
      setResult(res);
      if (res.ok) {
        setRationale('');
        setSummary('');
        setTargetId('');
      }
    });
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) reset();
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          {label}
        </Button>
      </DialogTrigger>
      <DialogContent closeLabel={bi(locale, 'Cerrar', 'Close')}>
        <DialogHeader>
          <DialogTitle>{label}</DialogTitle>
          {description ? (
            <p className="text-sm text-fg-muted">{description}</p>
          ) : null}
        </DialogHeader>

        <div className="space-y-3">
          {needsTarget ? (
            <label className="block text-xs font-medium text-fg">
              {bi(locale, 'Identificador objetivo', 'Target identifier')}
              <Input
                value={targetId}
                onChange={(e) => setTargetId(e.target.value)}
                placeholder={bi(locale, 'p. ej. SBS-001234 / ID', 'e.g. SBS-001234 / ID')}
                className="mt-1"
              />
            </label>
          ) : null}

          {isPropose ? (
            <label className="block text-xs font-medium text-fg">
              {bi(locale, 'Resumen del patrón', 'Pattern summary')}
              <Input
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
                placeholder={bi(locale, 'Breve resumen', 'Short summary')}
                className="mt-1"
              />
            </label>
          ) : null}

          {minChars > 0 ? (
            <label className="block text-xs font-medium text-fg">
              {bi(locale, 'Justificación', 'Rationale')}
              <textarea
                value={rationale}
                onChange={(e) => setRationale(e.target.value)}
                rows={3}
                className="mt-1 w-full rounded-sbs border border-border bg-surface px-2.5 py-1.5 text-sm text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
              />
              <span
                className={`mt-1 block font-mono text-2xs ${
                  rationaleOk ? 'text-fg-subtle' : 'text-severity-high-fg'
                }`}
              >
                {rationale.trim().length}/{minChars} {bi(locale, 'mín. caracteres', 'min chars')}
              </span>
            </label>
          ) : null}

          {result ? (
            <p
              role="status"
              className={`rounded-sbs border px-2.5 py-1.5 text-xs ${
                result.ok
                  ? 'border-severity-low-border bg-severity-low-bg text-severity-low-fg'
                  : 'border-severity-high-border bg-severity-high-bg text-severity-high-fg'
              }`}
            >
              {result.ok
                ? `${bi(locale, 'Enviado', 'Submitted')} (${result.status}) — ${result.message}`
                : `${bi(locale, 'Error', 'Error')} (${result.status}) — ${result.message}`}
            </p>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
            {bi(locale, 'Cancelar', 'Cancel')}
          </Button>
          <Button size="sm" disabled={!canSubmit} onClick={submit}>
            {pending ? bi(locale, 'Enviando…', 'Submitting…') : bi(locale, 'Enviar', 'Submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
