// SPDX-License-Identifier: Apache-2.0
/* eslint-disable i18next/no-literal-string */
import { SandboxControl } from '@/components/sandbox/SandboxControl';
import { currentLocale } from '@/i18n/server';

// Bank-side send console for COOPAC_DEMO_002 (SBS-005678). Renders under the
// FI (bank) chrome — NOT the SBS portal. The coopac sends complaints INTO SBS
// over the real Tier-1 (granular) and Tier-2 (batch) channels.
export const dynamic = 'force-dynamic';

export default async function CoopacSendPage() {
  const locale = await currentLocale();
  const es = locale === 'es-PE';
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-[#1F4E47]">
          {es ? 'Envío de reclamos a la SBS' : 'Submit complaints to SBS'}
        </h1>
        <p className="mt-1 text-sm text-[#1F4E47]/70">
          {es
            ? 'Consola de la institución. Envía reclamos por los canales reales hacia la SBS: Tier 1 (granular, firmado OAuth + HMAC + mTLS) y Tier 2 (lote CSV). La SBS los recibe en su cabina de ingestión.'
            : 'Institution console. Send complaints to SBS over the real channels: Tier 1 (granular, signed OAuth + HMAC + mTLS) and Tier 2 (CSV batch). SBS receives them in its ingestion cockpit.'}
        </p>
      </div>
      <SandboxControl locale={locale} fixedProfile="coopac-tier2" />
    </div>
  );
}
