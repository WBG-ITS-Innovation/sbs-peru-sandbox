/* eslint-disable i18next/no-literal-string */
'use client';

import { useState } from 'react';

import {
  Button,
  Toast,
  ToastClose,
  ToastDescription,
  ToastProvider,
  ToastTitle,
  ToastViewport,
} from '@/components/ui';

type Variant = 'default' | 'low' | 'medium' | 'high' | 'critical';

interface Entry {
  id: number;
  variant: Variant;
  title: string;
  description: string;
}

const SAMPLES: Record<Variant, Omit<Entry, 'id' | 'variant'>> = {
  default: { title: 'Saved', description: 'Draft narrative saved.' },
  low: { title: 'Routine', description: 'Tier 2 batch processed without rejections.' },
  medium: { title: 'Watch', description: 'INDECOPI velocity nudged upward.' },
  high: { title: 'Attention', description: 'BANCO_DEMO_001 anomaly composite > 0.7.' },
  critical: { title: 'Critical', description: 'Composite signal crossed threshold.' },
};

export function ToastsDemo() {
  const [entries, setEntries] = useState<Entry[]>([]);
  let next = entries.length + 1;

  const fire = (variant: Variant) => {
    setEntries(prev => [
      ...prev,
      { id: next++, variant, ...SAMPLES[variant] },
    ]);
  };

  return (
    <ToastProvider>
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" onClick={() => fire('default')}>
          Default
        </Button>
        <Button variant="outline" size="sm" onClick={() => fire('low')}>
          Low
        </Button>
        <Button variant="outline" size="sm" onClick={() => fire('medium')}>
          Medium
        </Button>
        <Button variant="outline" size="sm" onClick={() => fire('high')}>
          High
        </Button>
        <Button variant="outline" size="sm" onClick={() => fire('critical')}>
          Critical
        </Button>
      </div>
      {entries.map(e => (
        <Toast key={e.id} variant={e.variant}>
          <div className="flex flex-col gap-1">
            <ToastTitle>{e.title}</ToastTitle>
            <ToastDescription>{e.description}</ToastDescription>
          </div>
          <ToastClose />
        </Toast>
      ))}
      <ToastViewport />
    </ToastProvider>
  );
}
