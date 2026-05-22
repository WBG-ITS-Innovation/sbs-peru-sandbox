// Class-merging utility — the standard shadcn / Tailwind pattern.
// Combines clsx's conditional inputs with tailwind-merge's
// conflict-resolution so `cn('px-2', cond && 'px-4')` returns `px-4`
// rather than both classes.

import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
