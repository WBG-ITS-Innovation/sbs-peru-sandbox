import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { forwardRef, type ButtonHTMLAttributes } from 'react';

import { cn } from '@/lib/cn';

const buttonVariants = cva(
  // Base. Tokens, not literal hex. 2px radius per ADR 0041 D5.
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-sbs font-medium ' +
    'transition-colors focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        default:
          'bg-brand-navy text-fg-inverted hover:bg-brand-navy/90 focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2',
        secondary:
          'bg-surface-subtle text-fg border border-border hover:bg-neutral-100',
        outline:
          'border border-border-strong bg-transparent text-fg hover:bg-surface-subtle',
        ghost: 'bg-transparent text-fg hover:bg-surface-subtle',
        link: 'bg-transparent text-fg-link underline-offset-4 hover:underline',
        destructive:
          'bg-danger text-danger-fg hover:bg-danger/90',
      },
      size: {
        sm: 'h-7 px-2.5 text-xs',
        md: 'h-9 px-3 text-sm',
        lg: 'h-10 px-4 text-base',
        icon: 'h-9 w-9 p-0',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'md',
    },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button';
    return (
      <Comp
        className={cn(buttonVariants({ variant, size }), className)}
        ref={ref}
        {...props}
      />
    );
  },
);
Button.displayName = 'Button';

export { buttonVariants };
