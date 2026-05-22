import { forwardRef, type HTMLAttributes, type TableHTMLAttributes } from 'react';

import { cn } from '@/lib/cn';

// ADR 0041 D5 — table calibration:
// - 2px border radius (rounded-sbs), not the default rounded-md
// - Thin 1px borders, not gridlines
// - Zebra striping on subtle (neutral-50), not a saturated tint
// - Tabular numerals applied via `.tabular` on numeric cells

export const Table = forwardRef<HTMLTableElement, TableHTMLAttributes<HTMLTableElement>>(
  ({ className, ...props }, ref) => (
    <div className="w-full overflow-auto rounded-sbs border border-border">
      <table
        ref={ref}
        className={cn('w-full caption-bottom text-sm text-fg', className)}
        {...props}
      />
    </div>
  ),
);
Table.displayName = 'Table';

export const TableHeader = forwardRef<HTMLTableSectionElement, HTMLAttributes<HTMLTableSectionElement>>(
  ({ className, ...props }, ref) => (
    <thead
      ref={ref}
      className={cn(
        'border-b border-border bg-surface-subtle text-2xs font-medium uppercase tracking-wider text-fg-muted',
        className,
      )}
      {...props}
    />
  ),
);
TableHeader.displayName = 'TableHeader';

export const TableBody = forwardRef<HTMLTableSectionElement, HTMLAttributes<HTMLTableSectionElement>>(
  ({ className, ...props }, ref) => (
    // Zebra striping via :nth-child — subtle, not saturated.
    <tbody
      ref={ref}
      className={cn('[&_tr:nth-child(odd)]:bg-surface-subtle/40', className)}
      {...props}
    />
  ),
);
TableBody.displayName = 'TableBody';

export const TableRow = forwardRef<HTMLTableRowElement, HTMLAttributes<HTMLTableRowElement>>(
  ({ className, ...props }, ref) => (
    <tr
      ref={ref}
      className={cn('border-b border-border-subtle transition-colors hover:bg-surface-subtle/70', className)}
      {...props}
    />
  ),
);
TableRow.displayName = 'TableRow';

export const TableHead = forwardRef<HTMLTableCellElement, HTMLAttributes<HTMLTableCellElement>>(
  ({ className, ...props }, ref) => (
    <th
      ref={ref}
      className={cn('h-9 px-3 text-left align-middle', className)}
      {...props}
    />
  ),
);
TableHead.displayName = 'TableHead';

export const TableCell = forwardRef<HTMLTableCellElement, HTMLAttributes<HTMLTableCellElement>>(
  ({ className, ...props }, ref) => (
    <td
      ref={ref}
      className={cn('px-3 py-2 align-middle', className)}
      {...props}
    />
  ),
);
TableCell.displayName = 'TableCell';

export const TableCaption = forwardRef<HTMLTableCaptionElement, HTMLAttributes<HTMLTableCaptionElement>>(
  ({ className, ...props }, ref) => (
    <caption ref={ref} className={cn('mt-2 text-xs text-fg-muted', className)} {...props} />
  ),
);
TableCaption.displayName = 'TableCaption';
