/* eslint-disable i18next/no-literal-string */
'use client';

import { useState } from 'react';

import { Button, ErrorBoundary } from '@/components/ui';

function CrashOnRender(): React.JSX.Element {
  throw new Error('Intentional crash from the design-system index page.');
}

export function ErrorBoundaryDemo() {
  const [crash, setCrash] = useState(false);

  return (
    <div className="space-y-2">
      <Button
        variant="outline"
        size="sm"
        onClick={() => setCrash(c => !c)}
      >
        {crash ? 'Reset' : 'Trigger render crash'}
      </Button>
      <ErrorBoundary>
        {crash ? <CrashOnRender /> : (
          <p className="rounded-sbs border border-border-subtle bg-surface-subtle p-3 text-sm text-fg-muted">
            Wrapped panel — click the button above to trigger a render crash.
          </p>
        )}
      </ErrorBoundary>
    </div>
  );
}
