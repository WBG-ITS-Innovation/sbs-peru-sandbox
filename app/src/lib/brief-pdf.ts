// Client-side PDF brief generator (Reclamito). Builds a thorough brief from
// the REAL computed pattern data already in the aggregate row — institution,
// motivo/submotivo/topic, counts, favour/pending percentages, contributing
// complaint IDs, and a computed narrative. jsPDF is lazy-imported so it only
// loads when a brief is actually generated. The footer marks the data as
// synthetic. No hardcoded figures — everything comes from the passed row.

export interface BriefRow {
  institution_name?: string;
  cohort_id?: string;
  institution_id?: string;
  motivo_code: string;
  submotivo?: string | null;
  submotivo_2?: string | null;
  topic?: string | null;
  n_complaints: number;
  n_resolved: number;
  n_pending: number;
  n_favor_user: number;
  n_favor_bank: number;
  n_favor_partial: number;
  pct_favor_user: number | null;
  pct_favor_bank: number | null;
  pct_partial: number | null;
  complaint_ids?: string[];
  flags?: string[];
}

const FLAG_LABEL: Record<string, string> = {
  pending: 'backlog (alto % pendiente)',
  bank: 'sesgo a favor de la entidad',
  corr: 'correlación social + INDECOPI',
};

function pct(n: number, d: number): string {
  return d > 0 ? `${((100 * n) / d).toFixed(1)}%` : '—';
}

export async function generateBriefPdf(
  row: BriefRow,
  opts: { period?: { start: string | null; end: string | null } | null } = {},
): Promise<void> {
  const { jsPDF } = await import('jspdf');
  const doc = new jsPDF({ unit: 'pt', format: 'a4' });
  const entity = row.institution_name ?? row.cohort_id ?? row.institution_id ?? '—';
  const pendingPct = pct(row.n_pending, row.n_complaints);
  const now = new Date().toISOString().slice(0, 16).replace('T', ' ');
  const margin = 48;
  const W = doc.internal.pageSize.getWidth();
  let y = margin;

  const line = (text: string, size = 10, bold = false, color = 30) => {
    doc.setFont('helvetica', bold ? 'bold' : 'normal');
    doc.setFontSize(size);
    doc.setTextColor(color);
    const wrapped = doc.splitTextToSize(text, W - margin * 2) as string[];
    for (const w of wrapped) {
      if (y > 770) { doc.addPage(); y = margin; }
      doc.text(w, margin, y);
      y += size + 4;
    }
  };
  const gap = (h = 6) => { y += h; };
  const heading = (t: string) => { gap(8); line(t, 11, true, 0); };

  // Title bar
  doc.setFillColor(0, 34, 68); // brand navy
  doc.rect(0, 0, W, 64, 'F');
  doc.setTextColor(255);
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(15);
  doc.text('SBS SupTech — Brief de patrón', margin, 30);
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(9);
  doc.text(`Reclamito · generado ${now} UTC`, margin, 46);
  y = 88;

  heading('1. Identificación');
  line(`Institución / cohorte: ${entity}`);
  line(`Motivo: ${row.motivo_code}`);
  line(`Submotivo: ${row.submotivo ?? '—'}`);
  if (row.submotivo_2) line(`Submotivo (detalle): ${row.submotivo_2}`);
  line(`Topic / tendencia: ${row.topic ?? '—'}`);

  heading('2. Métricas (datos reales computados)');
  line(`N° de reclamos: ${row.n_complaints}`);
  line(`Resueltos: ${row.n_resolved}   ·   Pendientes: ${row.n_pending}   (${pendingPct} pendiente)`);
  line(`% a favor del usuario: ${row.pct_favor_user == null ? '—' : `${row.pct_favor_user.toFixed(1)}%`}  (${row.n_favor_user})`);
  line(`% a favor de la entidad: ${row.pct_favor_bank == null ? '—' : `${row.pct_favor_bank.toFixed(1)}%`}  (${row.n_favor_bank})`);
  line(`% resolución parcial: ${row.pct_partial == null ? '—' : `${row.pct_partial.toFixed(1)}%`}  (${row.n_favor_partial})`);

  if (row.flags?.length) {
    heading('3. Alertas detectadas');
    for (const f of row.flags) line(`• ${FLAG_LABEL[f] ?? f}`);
  }

  heading(`${row.flags?.length ? '4' : '3'}. Resumen`);
  const resolved = row.n_resolved;
  const narrative =
    `Se identificaron ${row.n_complaints} reclamos asociados a "${row.motivo_code}"` +
    (row.submotivo ? ` (${row.submotivo})` : '') +
    ` en ${entity}. ${pendingPct} permanecen pendientes de resolución. ` +
    (resolved > 0
      ? `De los ${resolved} resueltos, ${row.pct_favor_user?.toFixed(1) ?? '—'}% se resolvieron a favor del usuario y ${row.pct_favor_bank?.toFixed(1) ?? '—'}% a favor de la entidad.`
      : `Aún no hay casos resueltos en este grupo.`) +
    (row.flags?.includes('bank') ? ' El sesgo hacia la entidad supera el umbral de alerta y amerita revisión supervisora.' : '') +
    (row.flags?.includes('corr') ? ' Existe corroboración cross-source (redes sociales + INDECOPI) para esta institución.' : '');
  line(narrative);

  if (row.complaint_ids?.length) {
    heading(`${row.flags?.length ? '5' : '4'}. Reclamos contribuyentes (${row.complaint_ids.length})`);
    line(row.complaint_ids.join('   '), 9, false, 80);
  }

  // Footer on every page
  const pages = doc.getNumberOfPages();
  const periodStr = opts.period?.start && opts.period?.end ? `${opts.period.start} a ${opts.period.end}` : 'n/d';
  for (let i = 1; i <= pages; i += 1) {
    doc.setPage(i);
    doc.setDrawColor(200);
    doc.line(margin, 808, W - margin, 808);
    doc.setFont('helvetica', 'italic');
    doc.setFontSize(8);
    doc.setTextColor(150);
    doc.text(`DATOS SINTÉTICOS DE DEMOSTRACIÓN — no representan datos reales de instituciones. Periodo de datos: ${periodStr}.`, margin, 822);
    doc.text(`pág. ${i}/${pages}`, W - margin - 30, 822);
  }

  const safe = `${row.motivo_code}-${entity}`.replace(/[^a-z0-9]+/gi, '_').slice(0, 60);
  doc.save(`brief-${safe}.pdf`);
}
