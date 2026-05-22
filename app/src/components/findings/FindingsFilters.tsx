// URL-driven filter strip. State lives in query params so deep links
// to a filtered view work and the URL is shareable. The "Apply" /
// "Reset" buttons push to the URL via router.push; the server
// component above re-renders against the new searchParams.

'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { useTransition } from 'react';

import { Button, Input, Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui';

interface FindingsFiltersProps {
  labels: {
    label: string;
    institution: string;
    severity: string;
    source: string;
    confidence_band: string;
    any: string;
    apply: string;
    reset: string;
    source_tier1: string;
    source_tier2: string;
    band_low: string;
    band_medium: string;
    band_high: string;
  };
}

const SEVERITY_OPTIONS = ['low', 'medium', 'high', 'critical'] as const;

export function FindingsFilters({ labels }: FindingsFiltersProps) {
  const router = useRouter();
  const sp = useSearchParams();
  const [isPending, startTransition] = useTransition();

  function apply(form: FormData) {
    const params = new URLSearchParams();
    const institution = String(form.get('institution') ?? '').trim();
    const severity = String(form.get('severity') ?? '').trim();
    const source = String(form.get('source') ?? '').trim();
    const band = String(form.get('confidence_band') ?? '').trim();
    if (institution) params.set('institution', institution);
    if (severity && severity !== 'any') params.set('severity', severity);
    if (source && source !== 'any') params.set('source', source);
    if (band && band !== 'any') params.set('confidence_band', band);
    params.set('use_defaults', 'false');
    startTransition(() => {
      router.push(`/findings?${params.toString()}`);
    });
  }

  function reset() {
    startTransition(() => {
      router.push('/findings');
    });
  }

  return (
    <form
      action={apply}
      aria-label={labels.label}
      className="flex flex-wrap items-end gap-2 rounded-sbs border border-border-subtle bg-surface-subtle p-3"
    >
      <label className="flex flex-col gap-1 text-2xs uppercase tracking-wider text-fg-muted">
        <span>{labels.institution}</span>
        <Input
          name="institution"
          defaultValue={sp.get('institution') ?? ''}
          placeholder="SBS-001234"
          className="h-8 w-40"
        />
      </label>
      <label className="flex flex-col gap-1 text-2xs uppercase tracking-wider text-fg-muted">
        <span>{labels.severity}</span>
        <Select name="severity" defaultValue={sp.get('severity') ?? 'any'}>
          <SelectTrigger className="h-8 w-32">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="any">{labels.any}</SelectItem>
            {SEVERITY_OPTIONS.map(s => (
              <SelectItem key={s} value={s}>
                {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </label>
      <label className="flex flex-col gap-1 text-2xs uppercase tracking-wider text-fg-muted">
        <span>{labels.source}</span>
        <Select name="source" defaultValue={sp.get('source') ?? 'any'}>
          <SelectTrigger className="h-8 w-36">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="any">{labels.any}</SelectItem>
            <SelectItem value="api_realtime">{labels.source_tier1}</SelectItem>
            <SelectItem value="batch">{labels.source_tier2}</SelectItem>
          </SelectContent>
        </Select>
      </label>
      <label className="flex flex-col gap-1 text-2xs uppercase tracking-wider text-fg-muted">
        <span>{labels.confidence_band}</span>
        <Select name="confidence_band" defaultValue={sp.get('confidence_band') ?? 'any'}>
          <SelectTrigger className="h-8 w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="any">{labels.any}</SelectItem>
            <SelectItem value="low">{labels.band_low}</SelectItem>
            <SelectItem value="medium">{labels.band_medium}</SelectItem>
            <SelectItem value="high">{labels.band_high}</SelectItem>
          </SelectContent>
        </Select>
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
