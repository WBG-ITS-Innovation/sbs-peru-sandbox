// CrossSourceStrip — five channel chips (complaints / social /
// INDECOPI / Plavia / internal). Per the WS3 directive, each chip
// renders a real sparkline + a delta indicator, not a generic
// up/down arrow. This is the visual language a regulator expects
// from a data-density tool.

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
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-fg">{labels.title}</h2>
          {strip.is_illustrative ? (
            <span className="text-2xs uppercase tracking-wider text-fg-muted">
              {labels.illustrative}
            </span>
          ) : null}
        </div>
      </CardHeader>
      <CardBody>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          {strip.channels.map(ch => {
            const delta = fmtDelta(ch.delta_24h, locale);
            return (
              <div
                key={ch.key}
                className="flex flex-col gap-1 rounded-sbs border border-border-subtle p-2"
              >
                <span className="text-2xs uppercase tracking-wider text-fg-muted">
                  {labels.channels[ch.key] ?? ch.key}
                </span>
                <div className="flex items-end justify-between gap-2">
                  <span className="tabular text-xl font-semibold text-fg">
                    {fmtValue(ch.value, locale)}
                  </span>
                  <Sparkline
                    values={ch.sparkline}
                    width={48}
                    height={18}
                    className="text-fg-muted"
                    ariaLabel={`${labels.channels[ch.key] ?? ch.key} trend`}
                  />
                </div>
                <span
                  className={cn(
                    'tabular text-2xs font-medium',
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
