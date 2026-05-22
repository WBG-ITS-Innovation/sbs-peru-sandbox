'use client';

import { Component, type ErrorInfo, type ReactNode } from 'react';

import { cn } from '@/lib/cn';

// Class-based ErrorBoundary — React's contract requires a class
// component for componentDidCatch. Wraps every screen at the route
// boundary so a render crash on one panel doesn't take down the whole
// app. The retry button remounts the children to give the consuming
// page a clean re-render attempt.

export interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: (args: { error: Error; retry: () => void }) => ReactNode;
  retryLabel?: string;
  className?: string;
}

interface ErrorBoundaryState {
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    // Keep this loud — silent failures in production are the worst
    // outcome. A future workstream may pipe this to the audit chain;
    // for now console.error is the floor.
    // eslint-disable-next-line no-console
    console.error('ErrorBoundary caught render error', { error, errorInfo });
  }

  retry = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    if (this.state.error) {
      if (this.props.fallback) {
        return this.props.fallback({ error: this.state.error, retry: this.retry });
      }
      return (
        <div
          role="alert"
          className={cn(
            'flex flex-col items-start gap-2 rounded-sbs border border-severity-high-border bg-severity-high-bg p-4 text-sm text-severity-high-fg',
            this.props.className,
          )}
        >
          <strong>{this.state.error.name || 'Error'}</strong>
          <span className="text-xs opacity-80">{this.state.error.message}</span>
          <button
            type="button"
            onClick={this.retry}
            className="mt-2 inline-flex h-8 items-center justify-center rounded-sbs bg-surface px-3 text-xs font-medium text-fg hover:bg-surface-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2"
          >
            {this.props.retryLabel ?? 'Retry'}
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
