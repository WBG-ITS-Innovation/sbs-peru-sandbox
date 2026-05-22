// Audit filters — URL-driven, same shape as FindingsFilters.

'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { useTransition } from 'react';

import { Button, Input } from '@/components/ui';

interface AuditFiltersProps {
  labels: {
    label: string;
    actor: string;
    action: string;
    object_type: string;
    object_id: string;
    apply: string;
    reset: string;
  };
}

export function AuditFilters({ labels }: AuditFiltersProps) {
  const router = useRouter();
  const sp = useSearchParams();
  const [isPending, startTransition] = useTransition();

  function apply(form: FormData) {
    const params = new URLSearchParams();
    for (const key of ['actor_id', 'action', 'object_type', 'object_id']) {
      const v = String(form.get(key) ?? '').trim();
      if (v) params.set(key, v);
    }
    startTransition(() => router.push(`/audit?${params.toString()}`));
  }

  function reset() {
    startTransition(() => router.push('/audit'));
  }

  return (
    <form
      action={apply}
      aria-label={labels.label}
      className="flex flex-wrap items-end gap-2 rounded-sbs border border-border-subtle bg-surface-subtle p-3"
    >
      <label className="flex flex-col gap-1 text-2xs uppercase tracking-wider text-fg-muted">
        <span>{labels.actor}</span>
        <Input name="actor_id" defaultValue={sp.get('actor_id') ?? ''} className="h-8 w-44" />
      </label>
      <label className="flex flex-col gap-1 text-2xs uppercase tracking-wider text-fg-muted">
        <span>{labels.action}</span>
        <Input name="action" defaultValue={sp.get('action') ?? ''} className="h-8 w-44" />
      </label>
      <label className="flex flex-col gap-1 text-2xs uppercase tracking-wider text-fg-muted">
        <span>{labels.object_type}</span>
        <Input name="object_type" defaultValue={sp.get('object_type') ?? ''} className="h-8 w-32" />
      </label>
      <label className="flex flex-col gap-1 text-2xs uppercase tracking-wider text-fg-muted">
        <span>{labels.object_id}</span>
        <Input name="object_id" defaultValue={sp.get('object_id') ?? ''} className="h-8 w-44" />
      </label>
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={isPending}>
          {labels.apply}
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={reset} disabled={isPending}>
          {labels.reset}
        </Button>
      </div>
    </form>
  );
}
