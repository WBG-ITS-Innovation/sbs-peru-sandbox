// SPDX-License-Identifier: Apache-2.0
// Demo-mode persona switcher in the top bar. Feature-flagged by
// SBS_DEMO_MODE — the parent shell renders nothing when off.

'use client';

import { useState, useTransition } from 'react';
import { ChevronDown } from 'lucide-react';

import {
  Button,
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui';
import { cn } from '@/lib/cn';

const PERSONA_KEYS = ['supervisor', 'analyst', 'head'] as const;
type PersonaKey = (typeof PERSONA_KEYS)[number];

interface PersonaSwitcherProps {
  activePersonaKey: PersonaKey;
  labels: {
    switch_persona: string;
    active_persona: string;
    supervisor: string;
    analyst: string;
    head: string;
    cancel: string;
  };
  csrfToken: string;
}

export function PersonaSwitcher({
  activePersonaKey,
  labels,
  csrfToken,
}: PersonaSwitcherProps) {
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  const switchTo = (target: PersonaKey) => {
    if (target === activePersonaKey || isPending) return;
    startTransition(async () => {
      setError(null);
      const response = await fetch('/app/api/persona/switch', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-SBS-CSRF': csrfToken,
        },
        credentials: 'include',
        body: JSON.stringify({ to: target }),
      });
      if (!response.ok) {
        setError(`HTTP ${response.status}`);
        return;
      }
      setOpen(false);
      // The session changed on the server; revalidate by hard refresh
      // so server components re-render under the new identity.
      window.location.reload();
    });
  };

  const labelFor = (key: PersonaKey): string =>
    ({ supervisor: labels.supervisor, analyst: labels.analyst, head: labels.head })[key];

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="gap-1.5">
          <span className="text-fg-muted">{labels.active_persona}:</span>
          <span>{labelFor(activePersonaKey)}</span>
          <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{labels.switch_persona}</DialogTitle>
          <DialogDescription>{labels.active_persona}: {labelFor(activePersonaKey)}</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-2">
          {PERSONA_KEYS.map(key => (
            <Button
              key={key}
              variant={key === activePersonaKey ? 'default' : 'outline'}
              disabled={key === activePersonaKey || isPending}
              onClick={() => switchTo(key)}
              className={cn('justify-start', key === activePersonaKey && 'cursor-default')}
            >
              {labelFor(key)}
            </Button>
          ))}
        </div>
        {error ? (
          <p role="alert" className="text-xs text-severity-high-fg">
            {error}
          </p>
        ) : null}
        <DialogClose asChild>
          <Button variant="ghost" size="sm">
            {labels.cancel}
          </Button>
        </DialogClose>
      </DialogContent>
    </Dialog>
  );
}
