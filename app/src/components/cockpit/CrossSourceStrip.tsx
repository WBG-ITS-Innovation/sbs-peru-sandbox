// SPDX-License-Identifier: Apache-2.0
// CrossSourceStrip — five channel chips (complaints / social /
// INDECOPI / Plavia / internal). Per the WS3 directive, each chip
// renders a real sparkline + a delta indicator, not a generic up/down
// arrow. This is the visual language a regulator expects from a
// data-density tool. The Claude Design artifact tightens the layout
// to a five-column strip with mono micro-caps for the channel label
// and tabular numerics for value + delta.

import { Card, CardBody, CardHeader } from '@/components/ui';
import { cn } from '@/lib/cn';
import type { CrossSourceStrip as Strip } from '@/types/cockpit';

import { Sparkline } from './Sparkline';

interface CrossSourceStripProps {
  strip: Strip;
  locale: string;
  labels: {
    title: string;
    illustrative: string;
    channels: Record<string, string>;
  };
}

function fmtDelta(d: number, locale: string): { text: string; positive: boolean } {
  const formatted = new Intl.NumberFormat(locale, {
    signDisplay: 'exceptZero',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(d);
  return { text: formatted, positive: d > 0 };
}

function fmtValue(v: number, locale: string): string {
  return new Intl.NumberFormat(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(v);
}

export function CrossSourceStrip({ strip, locale, labels }: CrossSourceStripProps) {
  return (
    <Card className="border-border">
      <CardHeader className="border-b border-border px-4 py-2.5">
        <div className="flex items-center justify-between gap-2">
          <h2 className="font-mono text-2xs font-semibold uppercase tracking-wider text-brand-navy">
            {labels.title}
          </h2>
          {strip.is_illustrative ? (
            <span className="font-mono text-2xs uppercase tracking-wider text-fg-muted">
              {labels.illustrative}
            </span>
          ) : null}
        </div>
      </CardHeader>
      <CardBody className="p-0">
        <div className="grid grid-cols-2 divide-x divide-border-subtle sm:grid-cols-5">
          {strip.channels.map(ch => {
            const delta = fmtDelta(ch.delta_24h, locale);
            return (
              <div
                key={ch.key}
                className="flex flex-col gap-1 border-t border-border-subtle px-3 py-2.5 first:border-t-0 sm:border-t-0"
              >
                <span className="font-mono text-2xs uppercase tracking-wider text-fg-muted">
                  {labels.channels[ch.key] ?? ch.key}
                </span>
                <div className="flex items-end justify-between gap-2">
                  <span className="font-mono text-2xl font-semibold leading-none tabular text-brand-navy">
                    {fmtValue(ch.value, locale)}
                  </span>
                  <Sparkline
                    values={ch.sparkline}
                    width={56}
                    height={20}
                    className="text-brand-cyan"
                    ariaLabel={`${labels.channels[ch.key] ?? ch.key} trend`}
                  />
                </div>
                <span
                  className={cn(
                    'font-mono text-2xs font-medium tabular',
                    delta.positive ? 'text-severity-high-fg' : 'text-fg-muted',
                  )}
                >
                  {delta.text}
                </span>
              </div>
            );
          })}
        </div>
      </CardBody>
    </Card>
  );
}
