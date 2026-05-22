import { t } from '@/i18n';
import { currentLocale } from '@/i18n/server';

// Placeholder. WS4 lands the findings drilldown: BERT confidence,
// XGBoost SHAP features, agent reasoning chain, editable draft narrative.
export default function FindingDetailPage({ params }: { params: { id: string } }) {
  const locale = currentLocale();
  return (
    <main>
      <h1>
        {t(locale, 'findings.title')} · {params.id}
      </h1>
      <p>{t(locale, 'findings.placeholder.detail_body')}</p>
    </main>
  );
}
