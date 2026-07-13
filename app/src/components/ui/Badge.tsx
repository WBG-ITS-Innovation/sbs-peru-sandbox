// SPDX-License-Identifier: Apache-2.0
import { cva, type VariantProps } from 'class-variance-authority';
import { forwardRef, type HTMLAttributes } from 'react';

import { cn } from '@/lib/cn';

// ADR 0041 D2 — severity tokens are SEMANTIC; this component reads
// from CSS custom properties (bg-severity-<level>-bg etc.) rather than
// from literal hex. A palette tweak in globals.css propagates here
// without component edits.
const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded-sbs border px-2 py-0.5 text-2xs font-medium tabular',
  {
    variants: {
      variant: {
        default:
          'border-border bg-surface-subtle text-fg',
        low:
          'border-severity-low-border bg-severity-low-bg text-severity-low-fg',
        medium:
          'border-severity-medium-border bg-severity-medium-bg text-severity-medium-fg',
        high:
          'border-severity-high-border bg-severity-high-bg text-severity-high-fg',
        critical:
          'border-severity-critical-border bg-severity-critical-bg text-severity-critical-fg',
        // Status / source / role chips share the badge shape but read
        // from different semantic tokens. New chip kinds extend this
        // map rather than reaching for hex.
        pending:
          'border-border bg-status-pending-bg text-status-pending-fg',
        'in-review':
          'border-border bg-status-in-review-bg text-status-in-review-fg',
        resolved:
          'border-border bg-status-resolved-bg text-status-resolved-fg',
        escalated:
          'border-border bg-status-escalated-bg text-status-escalated-fg',
        // Source chips (Tier 1 / Tier 2 / Cross-source channels)
        source:
          'border-brand-cyan/40 bg-brand-cyan/10 text-brand-navy',
        // Role chips (Supervisor / Analyst / Head)
        role:
          'border-brand-gold/40 bg-brand-gold/10 text-brand-navy',
        // P11 demo-ui-polish — explicit tier badges. WBG palette:
        // Tier 1 (NRT) cyan #009FDA, Tier 2 (batch) gold #F5BD24.
        tier1:
          'border-brand-cyan bg-brand-cyan/15 text-brand-navy',
        tier2:
          'border-brand-gold bg-brand-gold/20 text-brand-navy',
        // P11 demo-ui-polish — unknown-taxonomy pill on cockpit cards.
        // Soft gold to draw the eye without screaming severity.
        warning:
          'border-brand-gold bg-brand-gold/15 text-brand-navy',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
);

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export const Badge = forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, variant, ...props }, ref) => (
    <span
      ref={ref}
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  ),
);
Badge.displayName = 'Badge';

export { badgeVariants };
