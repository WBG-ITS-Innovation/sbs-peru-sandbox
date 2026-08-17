// SPDX-License-Identifier: Apache-2.0
// Re-export every shipped primitive. Importers consume from
// '@/components/ui' rather than reaching into individual files; this
// makes refactors (renaming files, splitting a component) one diff.

export { Badge, badgeVariants, type BadgeProps } from './Badge';
export { Button, buttonVariants, type ButtonProps } from './Button';
export {
  Card,
  CardBody,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from './Card';
export { Checkbox } from './Checkbox';
export {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
  DialogTrigger,
  type DialogContentProps,
} from './Dialog';
export { EmptyState, type EmptyStateAction, type EmptyStateProps } from './EmptyState';
export { ErrorBoundary, type ErrorBoundaryProps } from './ErrorBoundary';
export { Input, type InputProps } from './Input';
export {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from './Select';
export {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetOverlay,
  SheetPortal,
  SheetTitle,
  SheetTrigger,
  type SheetContentProps,
} from './Sheet';
export { Skeleton } from './Skeleton';
export {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from './Table';
export {
  Toast,
  ToastClose,
  ToastDescription,
  ToastProvider,
  ToastTitle,
  ToastViewport,
  type ToastProps,
} from './Toast';
export {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from './Tooltip';
