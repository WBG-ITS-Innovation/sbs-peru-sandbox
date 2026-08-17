// SPDX-License-Identifier: Apache-2.0
/* eslint-disable i18next/no-literal-string */
// Separate FI app shell. Lives at /app/fi/banco-demo-001/* (the Next
// basePath is /app). Deliberately distinct chrome from the SBS shell —
// corporate gray-blue, "outside SBS perimeter" footer.

import type { ReactNode } from 'react';

export const dynamic = 'force-dynamic';

export default function FIBancoLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-[#F1F3F5] text-fg">
      <header className="border-b border-[#2C3E50]/20 bg-[#2C3E50] text-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-sm bg-white/10 font-mono text-xs font-bold tracking-wider">
              BD
            </div>
            <div>
              <p className="text-base font-semibold leading-tight">
                BANCO DEMO
              </p>
              <p className="text-xs text-white/70">
                BANCO_DEMO_001 — Sistema de Gestión de Reclamos
              </p>
            </div>
          </div>
          <span className="rounded-sm border border-white/20 bg-white/5 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-white/80">
            Sandbox interno
          </span>
        </div>
      </header>
      <main className="flex-1">
        <div className="mx-auto max-w-6xl px-6 py-6">{children}</div>
      </main>
      <footer className="border-t border-[#2C3E50]/15 bg-white/60 py-3">
        <p className="mx-auto max-w-6xl px-6 text-center text-xs text-[#2C3E50]/70">
          Sistema interno BANCO_DEMO_001 — fuera del perímetro SBS
        </p>
      </footer>
    </div>
  );
}
