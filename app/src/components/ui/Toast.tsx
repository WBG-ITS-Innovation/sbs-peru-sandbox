'use client';

import * as ToastPrimitive from '@radix-ui/react-toast';
import { cva, type VariantProps } from 'class-variance-authority';
import { X } from 'lucide-react';
import { forwardRef } from 'react';

import { cn } from '@/lib/cn';

export const ToastProvider = ToastPrimitive.Provider;

export const ToastViewport = forwardRef<
  React.ElementRef<typeof ToastPrimitive.Viewport>,
  React.ComponentPropsWithoutRef<typeof ToastPrimitive.Viewport>
>(({ className, ...props }, ref) => (
  <ToastPrimitive.Viewport
    ref={ref}
    className={cn(
      'fixed bottom-0 right-0 z-[100] flex max-h-screen w-full flex-col-reverse gap-2 p-4 sm:max-w-md',
      className,
    )}
    {...props}
  />
));
ToastViewport.displayName = ToastPrimitive.Viewport.displayName;

// Severity-coded variants read from the same tokens Badge uses, so a
// "critical" toast matches a "critical" badge by construction.
const toastVariants = cva(
  'group pointer-events-auto relative flex w-full items-center justify-between gap-2 rounded-sbs border p-4 shadow-lg animate-slide-up',
  {
    variants: {
      variant: {
        default: 'border-border bg-surface-elevated text-fg',
        low:
          'border-severity-low-border bg-severity-low-bg text-severity-low-fg',
        medium:
          'border-severity-medium-border bg-severity-medium-bg text-severity-medium-fg',
        high:
          'border-severity-high-border bg-severity-high-bg text-severity-high-fg',
        critical:
          'border-severity-critical-border bg-severity-critical-bg text-severity-critical-fg',
      },
    },
    defaultVariants: { variant: 'default' },
  },
);

export interface ToastProps
  extends React.ComponentPropsWithoutRef<typeof ToastPrimitive.Root>,
    VariantProps<typeof toastVariants> {}

export const Toast = forwardRef<
  React.ElementRef<typeof ToastPrimitive.Root>,
  ToastProps
>(({ className, variant, ...props }, ref) => (
  <ToastPrimitive.Root
    ref={ref}
    className={cn(toastVariants({ variant }), className)}
    {...props}
  />
));
Toast.displayName = ToastPrimitive.Root.displayName;

export const ToastTitle = forwardRef<
  React.ElementRef<typeof ToastPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof ToastPrimitive.Title>
>(({ className, ...props }, ref) => (
  <ToastPrimitive.Title
    ref={ref}
    className={cn('text-sm font-semibold', className)}
    {...props}
  />
));
ToastTitle.displayName = ToastPrimitive.Title.displayName;

export const ToastDescription = forwardRef<
  React.ElementRef<typeof ToastPrimitive.Description>,
  React.ComponentPropsWithoutRef<typeof ToastPrimitive.Description>
>(({ className, ...props }, ref) => (
  <ToastPrimitive.Description
    ref={ref}
    className={cn('text-xs opacity-90', className)}
    {...props}
  />
));
ToastDescription.displayName = ToastPrimitive.Description.displayName;

export const ToastClose = forwardRef<
  React.ElementRef<typeof ToastPrimitive.Close>,
  React.ComponentPropsWithoutRef<typeof ToastPrimitive.Close> & { closeLabel?: string }
>(({ className, closeLabel = 'Close', ...props }, ref) => (
  <ToastPrimitive.Close
    ref={ref}
    aria-label={closeLabel}
    className={cn(
      'rounded-sbs p-1 opacity-60 hover:opacity-100',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2',
      className,
    )}
    {...props}
  >
    <X className="h-3.5 w-3.5" aria-hidden="true" />
  </ToastPrimitive.Close>
));
ToastClose.displayName = ToastPrimitive.Close.displayName;
